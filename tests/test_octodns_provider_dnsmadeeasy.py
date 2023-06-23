#
#
#

import json
from os.path import dirname, join
from unittest import TestCase
from unittest.mock import Mock, call

from requests import HTTPError
from requests_mock import ANY
from requests_mock import mock as requests_mock

from octodns.provider.yaml import YamlProvider
from octodns.record import Record
from octodns.zone import Zone

from octodns_dnsmadeeasy import (
    DnsMadeEasyClient,
    DnsMadeEasyClientNotFound,
    DnsMadeEasyProvider,
)


class TestDnsMadeEasyProvider(TestCase):
    expected = Zone('unit.tests.', [])
    source = YamlProvider('test', join(dirname(__file__), 'config'))
    source.populate(expected)

    # Our test suite differs a bit, add our NS and remove the simple one
    expected.add_record(
        Record.new(
            expected,
            'under',
            {
                'ttl': 3600,
                'type': 'NS',
                'values': ['ns1.unit.tests.', 'ns2.unit.tests.'],
            },
        )
    )

    # Add some ALIAS records
    expected.add_record(
        Record.new(
            expected,
            '',
            {'ttl': 1800, 'type': 'ALIAS', 'value': 'aname.unit.tests.'},
        )
    )

    for record in list(expected.records):
        if record.name == 'sub' and record._type == 'NS':
            expected._remove_record(record)
            break

    def test_populate(self):
        provider = DnsMadeEasyProvider('test', 'api', 'secret')

        # Bad auth
        with requests_mock() as mock:
            mock.get(
                ANY, status_code=401, text='{"error": ["API key not found"]}'
            )

            with self.assertRaises(Exception) as ctx:
                zone = Zone('unit.tests.', [])
                provider.populate(zone)
            self.assertEqual('Unauthorized', str(ctx.exception))

        # Bad request
        with requests_mock() as mock:
            mock.get(
                ANY, status_code=400, text='{"error": ["Rate limit exceeded"]}'
            )

            with self.assertRaises(Exception) as ctx:
                zone = Zone('unit.tests.', [])
                provider.populate(zone)
            self.assertEqual('\n  - Rate limit exceeded', str(ctx.exception))

        # General error
        with requests_mock() as mock:
            mock.get(ANY, status_code=502, text='Things caught fire')

            with self.assertRaises(HTTPError) as ctx:
                zone = Zone('unit.tests.', [])
                provider.populate(zone)
            self.assertEqual(502, ctx.exception.response.status_code)

        # Non-existent zone doesn't populate anything
        with requests_mock() as mock:
            with open('tests/fixtures/dnsmadeeasy-no-domains.json') as fh:
                mock.get(ANY, text=fh.read())

            zone = Zone('unit.tests.', [])
            provider.populate(zone)
            self.assertEqual(0, len(zone.records))

        # No diffs == no changes
        with requests_mock() as mock:
            base = DnsMadeEasyClient.PRODUCTION
            with open('tests/fixtures/dnsmadeeasy-domains.json') as fh:
                mock.get(f'{base}/', text=fh.read())
            with open('tests/fixtures/dnsmadeeasy-records.json') as fh:
                mock.get(f'{base}/123123/records', text=fh.read())

                zone = Zone('unit.tests.', [])
                provider.populate(zone)
                self.assertEqual(14, len(zone.records))
                changes = self.expected.changes(zone, provider)
                self.assertEqual(0, len(changes))

        # 2nd populate makes no network calls/all from cache
        again = Zone('unit.tests.', [])
        provider.populate(again)
        self.assertEqual(14, len(again.records))

        # bust the cache
        del provider._zone_records[zone.name]

    def test_apply(self):
        # Create provider with sandbox enabled
        provider = DnsMadeEasyProvider(
            'test', 'api', 'secret', True, strict_supports=False
        )

        resp = Mock()
        resp.json = Mock()
        provider._client._request = Mock(return_value=resp)

        with open('tests/fixtures/dnsmadeeasy-no-domains.json') as fh:
            no_domains = json.load(fh)

        with open('tests/fixtures/dnsmadeeasy-domain-create.json') as fh:
            domain_create = json.load(fh)

        with open('tests/fixtures/dnsmadeeasy-domains.json') as fh:
            domains = json.load(fh)

        # non-existent domain, create everything
        resp.json.side_effect = [
            no_domains,
            DnsMadeEasyClientNotFound,  # no domain during apply
            domain_create,
            domains,
            domains,
        ]
        plan = provider.plan(self.expected)

        # No ignored, no excluded, no unsupported
        n = len(self.expected.records) - 9
        self.assertEqual(n, len(plan.changes))
        self.assertEqual(n, provider.apply(plan))

        provider._client._request.assert_has_calls(
            [
                # get all domains to build the cache
                call('GET', '/'),
                # checked if domain exists
                call('GET', '/id/unit.tests'),
                # created the domain
                call('POST', '/', data={'name': 'unit.tests'}),
                # created at least some of the record with expected data
                call(
                    'POST',
                    '/123123/records',
                    data={
                        'type': 'A',
                        'name': '',
                        'value': '1.2.3.4',
                        'ttl': 300,
                    },
                ),
                call(
                    'POST',
                    '/123123/records',
                    data={
                        'type': 'A',
                        'name': '',
                        'value': '1.2.3.5',
                        'ttl': 300,
                    },
                ),
                call(
                    'POST',
                    '/123123/records',
                    data={
                        'type': 'ANAME',
                        'name': '',
                        'value': 'aname.unit.tests.',
                        'ttl': 1800,
                    },
                ),
                call(
                    'POST',
                    '/123123/records',
                    data={
                        'name': '',
                        'value': 'ca.unit.tests',
                        'issuerCritical': 0,
                        'caaType': 'issue',
                        'ttl': 3600,
                        'type': 'CAA',
                    },
                ),
                call(
                    'POST',
                    '/123123/records',
                    data={
                        'name': '_srv._tcp',
                        'weight': 20,
                        'value': 'foo-1.unit.tests.',
                        'priority': 10,
                        'ttl': 600,
                        'type': 'SRV',
                        'port': 30,
                    },
                ),
            ]
        )
        self.assertEqual(25, provider._client._request.call_count)

        provider._client._request.reset_mock()

        # delete 1 and update 1
        provider._client.records = Mock(
            return_value=[
                {
                    'id': 11189897,
                    'name': 'www',
                    'value': '1.2.3.4',
                    'ttl': 300,
                    'type': 'A',
                },
                {
                    'id': 11189898,
                    'name': 'www',
                    'value': '2.2.3.4',
                    'ttl': 300,
                    'type': 'A',
                },
                {
                    'id': 11189899,
                    'name': 'ttl',
                    'value': '3.2.3.4',
                    'ttl': 600,
                    'type': 'A',
                },
            ]
        )

        # Domain exists, we don't care about return
        resp.json.side_effect = ['{}']

        wanted = Zone('unit.tests.', [])
        wanted.add_record(
            Record.new(
                wanted, 'ttl', {'ttl': 300, 'type': 'A', 'value': '3.2.3.4'}
            )
        )

        plan = provider.plan(wanted)
        self.assertEqual(2, len(plan.changes))
        self.assertEqual(2, provider.apply(plan))

        # recreate for update, and deletes for the 2 parts of the other
        provider._client._request.assert_has_calls(
            [
                call(
                    'POST',
                    '/123123/records',
                    data={
                        'value': '3.2.3.4',
                        'type': 'A',
                        'name': 'ttl',
                        'ttl': 300,
                    },
                ),
                call('DELETE', '/123123/records/11189899'),
                call('DELETE', '/123123/records/11189897'),
                call('DELETE', '/123123/records/11189898'),
            ],
            any_order=True,
        )
