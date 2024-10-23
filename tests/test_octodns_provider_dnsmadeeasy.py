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

from octodns.provider import SupportsException
from octodns.provider.yaml import YamlProvider
from octodns.record import Record
from octodns.zone import Zone

from octodns_dnsmadeeasy import DnsMadeEasyClientNotFound, DnsMadeEasyProvider


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
            expected.remove_record(record)
            break

    def test_populate(self):
        provider = DnsMadeEasyProvider('test', 'api', 'secret')

        # not found
        with requests_mock() as mock:
            mock.get(ANY, status_code=404, text='{"error": ["Not Found"]}')

            with self.assertRaises(Exception) as ctx:
                zone = Zone('unit.tests.', [])
                provider.populate(zone)
            self.assertEqual('Not Found', str(ctx.exception))

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

        # No diffs == no changes
        with requests_mock() as mock:
            base = 'https://api.dnsmadeeasy.com/V2.0/dns/managed'
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

    def test_populate_empty(self):
        provider = DnsMadeEasyProvider('test', 'api', 'secret')

        # Non-existent zone doesn't populate anything
        with requests_mock() as mock:
            with open('tests/fixtures/dnsmadeeasy-no-domains.json') as fh:
                mock.get(ANY, text=fh.read())

            zone = Zone('unit.tests.', [])
            provider.populate(zone)
            self.assertEqual(set(), zone.records)

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

        with open('tests/fixtures/dnsmadeeasy-domains.json') as fh:
            domains = json.load(fh)

        with open('tests/fixtures/dnsmadeeasy-domain-create.json') as fh:
            created_domain = json.load(fh)

        # non-existent domain, create everything
        resp.json.side_effect = [
            no_domains,  # no zone in populate
            DnsMadeEasyClientNotFound,  # no domain during apply
            created_domain,  # our created domain response
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
                # attempt to find the domain based on the name
                call('GET', '/id/unit.tests'),
                # create the domain
                call('POST', '/', data={'name': 'unit.tests'}),
                # created all the non-existent records in a single request
                call(
                    'POST',
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '1.2.3.4',
                            'name': '',
                            'ttl': 300,
                            'type': 'A',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '1.2.3.5',
                            'name': '',
                            'ttl': 300,
                            'type': 'A',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'aname.unit.tests.',
                            'name': '',
                            'ttl': 1800,
                            'type': 'ANAME',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'ca.unit.tests',
                            'issuerCritical': 0,
                            'name': '',
                            'caaType': 'issue',
                            'ttl': 3600,
                            'type': 'CAA',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'foo-1.unit.tests.',
                            'name': '_srv._tcp',
                            'port': 30,
                            'priority': 10,
                            'ttl': 600,
                            'type': 'SRV',
                            'weight': 20,
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'foo-2.unit.tests.',
                            'name': '_srv._tcp',
                            'port': 30,
                            'priority': 12,
                            'ttl': 600,
                            'type': 'SRV',
                            'weight': 20,
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '2601:644:500:e210:62f8:1dff:feb8:947a',
                            'name': 'aaaa',
                            'ttl': 600,
                            'type': 'AAAA',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'unit.tests.',
                            'name': 'cname',
                            'ttl': 300,
                            'type': 'CNAME',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'unit.tests.',
                            'name': 'included',
                            'ttl': 3600,
                            'type': 'CNAME',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'smtp-4.unit.tests.',
                            'name': 'mx',
                            'mxLevel': 10,
                            'ttl': 300,
                            'type': 'MX',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'smtp-2.unit.tests.',
                            'name': 'mx',
                            'mxLevel': 20,
                            'ttl': 300,
                            'type': 'MX',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'smtp-3.unit.tests.',
                            'name': 'mx',
                            'mxLevel': 30,
                            'ttl': 300,
                            'type': 'MX',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'smtp-1.unit.tests.',
                            'name': 'mx',
                            'mxLevel': 40,
                            'ttl': 300,
                            'type': 'MX',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'foo.bar.com.',
                            'name': 'ptr',
                            'ttl': 300,
                            'type': 'PTR',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '"Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nunc porttitor, odio eleifend ullamcorper ultricies, lectus lorem iaculis erat, ut porttitor erat orci eget est. Nunc tortor odio, suscipit non maximus in, euismod nec dolor. Nullam quis ultricies orci. Donec malesuada tempor accumsan. Vivamus erat eros, condimentum et urna vitae, aliquam congue quam. Phasellus nibh mauris, congue quis euismod vel, porta sed dui. Fusce massa dui, feugiat dapibus condimentum nec, vulputate eget ex. Sed vitae augue et ex facilisis placerat id sit amet tortor. Morbi pellentesque velit arcu, ut suscipit quam consectetur in. Quisque pulvinar ante sit amet egestas gravida. Etiam accumsan urna et suscipit pulvinar. Fusce ultricies congue sapien non semper. Morbi eleifend molestie blandit. Suspendisse potenti. Fusce vestibulum commodo leo. Nulla cursus turpis sit amet tincidunt bibendum."',
                            'name': 'split',
                            'ttl': 600,
                            'type': 'TXT',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '"Bah bah black sheep"',
                            'name': 'txt',
                            'ttl': 600,
                            'type': 'TXT',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '"have you any wool."',
                            'name': 'txt',
                            'ttl': 600,
                            'type': 'TXT',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '"v=DKIM1;k=rsa;s=email;h=sha256;p=A/kinda+of/long/string+with+numb3rs"',
                            'name': 'txt',
                            'ttl': 600,
                            'type': 'TXT',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'ns1.unit.tests.',
                            'name': 'under',
                            'ttl': 3600,
                            'type': 'NS',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': 'ns2.unit.tests.',
                            'name': 'under',
                            'ttl': 3600,
                            'type': 'NS',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '2.2.3.6',
                            'name': 'www',
                            'ttl': 300,
                            'type': 'A',
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '2.2.3.6',
                            'name': 'www.sub',
                            'ttl': 300,
                            'type': 'A',
                            'gtdLocation': 'DEFAULT',
                        },
                    ],
                ),
            ]
        )
        self.assertEqual(4, provider._client._request.call_count)

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
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '3.2.3.4',
                            'type': 'A',
                            'name': 'ttl',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        }
                    ],
                ),
                call(
                    'DELETE',
                    '/123123/records',
                    params={'ids': [11189897, 11189898, 11189899]},
                ),
            ],
            any_order=True,
        )
        self.assertEqual(3, provider._client._request.call_count)

        # test for just deleting a record, no additions

        provider._client._request.reset_mock()
        provider._client.records = Mock(
            return_value=[
                {
                    'id': 11189897,
                    'name': 'www',
                    'value': '1.2.3.4',
                    'ttl': 300,
                    'type': 'A',
                }
            ]
        )

        # Domain exists, we don't care about return
        resp.json.side_effect = ['{}']

        wanted = Zone('unit.tests.', [])

        plan = provider.plan(wanted)
        self.assertEqual(1, len(plan.changes))
        self.assertEqual(1, provider.apply(plan))

        # recreate for update, and deletes for the 2 parts of the other
        provider._client._request.assert_has_calls(
            [call('DELETE', '/123123/records', params={'ids': [11189897]})],
            any_order=True,
        )
        self.assertEqual(2, provider._client._request.call_count)

    def test_batching_requests(self):
        # Create our provider with a batch size of 2
        provider = DnsMadeEasyProvider(
            'test', 'api', 'secret', True, batch_size=2, strict_supports=False
        )

        resp = Mock()
        resp.json = Mock()
        provider._client._request = Mock(return_value=resp)

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

        with open('tests/fixtures/dnsmadeeasy-domains.json') as fh:
            domains = json.load(fh)

        with open('tests/fixtures/dnsmadeeasy-domain-create.json') as fh:
            created_domain = json.load(fh)

        # non-existent domain, create everything
        resp.json.side_effect = [
            created_domain,  # GET /id/unit.tests during plan
            domains,  # domains during plan
            domains,  # domains during apply
        ]

        wanted = Zone('unit.tests.', [])
        for i in range(1, 10):
            wanted.add_record(
                Record.new(
                    wanted,
                    f'www{i}',
                    {'ttl': 300, 'type': 'A', 'value': f'3.2.3.{i}'},
                )
            )

        plan = provider.plan(wanted)
        self.assertEqual(11, len(plan.changes))
        self.assertEqual(11, provider.apply(plan))

        # recreate for update, and deletes for the 2 parts of the other
        provider._client._request.assert_has_calls(
            [
                call(
                    'DELETE',
                    '/123123/records',
                    params={'ids': [11189899, 11189897]},
                ),
                call('DELETE', '/123123/records', params={'ids': [11189898]}),
                call(
                    'POST',
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '3.2.3.1',
                            'type': 'A',
                            'name': 'www1',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '3.2.3.2',
                            'type': 'A',
                            'name': 'www2',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                    ],
                ),
                call(
                    'POST',
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '3.2.3.3',
                            'type': 'A',
                            'name': 'www3',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '3.2.3.4',
                            'type': 'A',
                            'name': 'www4',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                    ],
                ),
                call(
                    'POST',
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '3.2.3.5',
                            'type': 'A',
                            'name': 'www5',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '3.2.3.6',
                            'type': 'A',
                            'name': 'www6',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                    ],
                ),
                call(
                    'POST',
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '3.2.3.7',
                            'type': 'A',
                            'name': 'www7',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                        {
                            'value': '3.2.3.8',
                            'type': 'A',
                            'name': 'www8',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        },
                    ],
                ),
                call(
                    'POST',
                    '/123123/records/createMulti',
                    data=[
                        {
                            'value': '3.2.3.9',
                            'type': 'A',
                            'name': 'www9',
                            'ttl': 300,
                            'gtdLocation': 'DEFAULT',
                        }
                    ],
                ),
            ],
            any_order=True,
        )
        self.assertEqual(9, provider._client._request.call_count)

    def test_quotes_in_TXT(self):
        provider = DnsMadeEasyProvider('test', 'api', 'secret')
        desired = Zone('unit.tests.', [])
        value = 'This has "quote" chars in it'
        txt = Record.new(
            desired, 'txt', {'ttl': 42, 'type': 'TXT', 'value': value}
        )
        desired.add_record(txt)

        with self.assertRaises(SupportsException) as ctx:
            provider._process_desired_zone(desired)
        self.assertEqual(
            'test: Quotes not supported in TXT values', str(ctx.exception)
        )

        provider.strict_supports = False
        got = provider._process_desired_zone(desired.copy())
        self.assertEqual(
            [value.replace('"', '')], next(iter(got.records)).values
        )
