#
#
#

import hashlib
import hmac
import logging
import re
from collections import defaultdict
from time import gmtime, sleep, strftime

from requests import Session

from octodns import __VERSION__ as octodns_version
from octodns.provider import ProviderException
from octodns.provider.base import BaseProvider
from octodns.record import Record

# TODO: remove __VERSION__ with the next major version release
__version__ = __VERSION__ = '1.0.0'


class DnsMadeEasyClientException(ProviderException):
    pass


class DnsMadeEasyClientBadRequest(DnsMadeEasyClientException):
    def __init__(self, resp):
        errors = '\n  - '.join(resp.json()['error'])
        super().__init__(f'\n  - {errors}')


class DnsMadeEasyClientUnauthorized(DnsMadeEasyClientException):
    def __init__(self):
        super().__init__('Unauthorized')


class DnsMadeEasyClientNotFound(DnsMadeEasyClientException):
    def __init__(self):
        super().__init__('Not Found')


class DnsMadeEasyClient(object):
    PRODUCTION = 'https://api.dnsmadeeasy.com/V2.0/dns/managed'
    SANDBOX = 'https://api.sandbox.dnsmadeeasy.com/V2.0/dns/managed'

    def __init__(
        self,
        api_key,
        secret_key,
        sandbox=False,
        ratelimit_delay=0.0,
        batch_size=200,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self._base = self.SANDBOX if sandbox else self.PRODUCTION
        self.ratelimit_delay = ratelimit_delay
        self.batch_size = batch_size
        self._sess = Session()
        self._sess.headers.update(
            {
                'x-dnsme-apiKey': self.api_key,
                'User-Agent': f'octodns/{octodns_version} octodns-dnsmadeasy/{__VERSION__}',
            }
        )
        self._domains = None

    def _current_time(self):
        return strftime("%a, %d %b %Y %H:%M:%S +0000", gmtime())

    def _hmac_hash(self, now):
        return hmac.new(
            self.secret_key.encode(), now.encode(), hashlib.sha1
        ).hexdigest()

    def _request(self, method, path, params=None, data=None):
        now = self._current_time()
        hmac_hash = self._hmac_hash(now)

        headers = {'x-dnsme-hmac': hmac_hash, 'x-dnsme-requestDate': now}

        url = f'{self._base}{path}'
        resp = self._sess.request(
            method, url, headers=headers, params=params, json=data
        )
        if resp.status_code == 400:
            raise DnsMadeEasyClientBadRequest(resp)
        if resp.status_code in [401, 403]:
            raise DnsMadeEasyClientUnauthorized()
        if resp.status_code == 404:
            raise DnsMadeEasyClientNotFound()
        resp.raise_for_status()
        sleep(self.ratelimit_delay)
        return resp

    @property
    def domains(self):
        if self._domains is None:
            zones = []

            # has pages in resp, do we need paging?
            resp = self._request('GET', '/').json()
            zones += resp['data']

            self._domains = {f'{z["name"]}.': z['id'] for z in zones}

        return self._domains

    def domain(self, name):
        path = f'/id/{name}'
        return self._request('GET', path).json()

    def domain_create(self, name):
        response = self._request('POST', '/', data={'name': name}).json()
        # Add our newly created domain to the cache
        self.domains[f'{name}.'] = response['id']

    def records(self, zone_name):
        zone_id = self.domains.get(zone_name, False)
        if not zone_id:
            return []
        path = f'/{zone_id}/records'
        ret = []

        # has pages in resp, do we need paging?
        resp = self._request('GET', path).json()
        ret += resp['data']

        for record in ret:
            # change ANAME records to ALIAS
            if record['type'] == 'ANAME':
                record['type'] = 'ALIAS'

            # change relative values to absolute
            value = record['value']
            if record['type'] in ['ALIAS', 'CNAME', 'MX', 'NS', 'SRV']:
                if value == '':
                    record['value'] = zone_name
                elif not value.endswith('.'):
                    record['value'] = f'{value}.{zone_name}'

        return ret

    def record_multi_delete(self, zone_name, record_ids):
        zone_id = self.domains.get(zone_name, False)
        path = f'/{zone_id}/records'

        # there is a maximum batch size for bulk actions, batch the records based on our batch size
        for batch in self._batch_records(record_ids):
            self._request('DELETE', path, params={'ids': batch})

    def record_multi_create(self, zone_name, records):
        zone_id = self.domains.get(zone_name, False)
        path = f'/{zone_id}/records/createMulti'

        # change ALIAS records to ANAME
        for record in records:
            if record['type'] == 'ALIAS':
                record['type'] = 'ANAME'
            record['gtdLocation'] = 'DEFAULT'

        # there is a maximum batch size for bulk actions, batch the records based on our batch size
        for batch in self._batch_records(records):
            self._request('POST', path, data=batch)

    def _batch_records(self, records):
        for i in range(0, len(records), self.batch_size):
            yield records[i : i + self.batch_size]


class DnsMadeEasyProvider(BaseProvider):
    SUPPORTS_GEO = False
    SUPPORTS_DYNAMIC = False
    SUPPORTS_ROOT_NS = True
    SUPPORTS = set(
        ('A', 'AAAA', 'ALIAS', 'CAA', 'CNAME', 'MX', 'NS', 'PTR', 'SRV', 'TXT')
    )
    # Regex to replace any pair of double quotes that aren't escaped with a backslash. Used as a delimiter in long TXT
    # records.
    #
    #  Will match: Alpha""Bravo
    #  Will not match: Alpha\""Bravo
    TXT_RECORD_VALUE_DELIMITER_PATTERN = re.compile(r'(?<!\\)\"\"')

    def __init__(
        self,
        id,
        api_key,
        secret_key,
        sandbox=False,
        ratelimit_delay=0.0,
        batch_size=200,
        *args,
        **kwargs,
    ):
        self.log = logging.getLogger(f'DnsMadeEasyProvider[{id}]')
        self.log.debug(
            '__init__: id=%s, api_key=***, secret_key=***, sandbox=%s, batch_size=%s',
            id,
            sandbox,
            batch_size,
        )
        super().__init__(id, *args, **kwargs)
        self._client = DnsMadeEasyClient(
            api_key, secret_key, sandbox, ratelimit_delay, batch_size
        )

        self._zone_records = {}

    def _data_for_multiple(self, _type, records):
        return {
            'ttl': records[0]['ttl'],
            'type': _type,
            'values': [r['value'] for r in records],
        }

    _data_for_A = _data_for_multiple
    _data_for_AAAA = _data_for_multiple
    _data_for_NS = _data_for_multiple

    def _data_for_CAA(self, _type, records):
        values = []
        for record in records:
            values.append(
                {
                    'flags': record['issuerCritical'],
                    'tag': record['caaType'],
                    'value': record['value'][1:-1],
                }
            )
        return {'ttl': records[0]['ttl'], 'type': _type, 'values': values}

    def _data_for_TXT(self, _type, records):
        # Long TXT records in DNS Mady Easy have their value split into 255 character chunks, delimited by "".
        values = [
            self.TXT_RECORD_VALUE_DELIMITER_PATTERN.sub(
                '', value['value'].replace(';', '\\;')
            )
            for value in records
        ]
        return {'ttl': records[0]['ttl'], 'type': _type, 'values': values}

    def _data_for_MX(self, _type, records):
        values = []
        for record in records:
            values.append(
                {'preference': record['mxLevel'], 'exchange': record['value']}
            )
        return {'ttl': records[0]['ttl'], 'type': _type, 'values': values}

    def _data_for_single(self, _type, records):
        record = records[0]
        return {'ttl': record['ttl'], 'type': _type, 'value': record['value']}

    _data_for_CNAME = _data_for_single
    _data_for_PTR = _data_for_single
    _data_for_ALIAS = _data_for_single

    def _data_for_SRV(self, _type, records):
        values = []
        for record in records:
            values.append(
                {
                    'port': record['port'],
                    'priority': record['priority'],
                    'target': record['value'],
                    'weight': record['weight'],
                }
            )
        return {'type': _type, 'ttl': records[0]['ttl'], 'values': values}

    def zone_records(self, zone):
        if zone.name not in self._zone_records:
            self._zone_records[zone.name] = self._client.records(zone.name)

        return self._zone_records[zone.name]

    def populate(self, zone, target=False, lenient=False):
        self.log.debug(
            'populate: name=%s, target=%s, lenient=%s',
            zone.name,
            target,
            lenient,
        )

        values = defaultdict(lambda: defaultdict(list))
        for record in self.zone_records(zone):
            _type = record['type']
            if _type not in self.SUPPORTS:
                self.log.warning(
                    'populate: skipping unsupported %s record', _type
                )
                continue
            values[record['name']][record['type']].append(record)

        before = len(zone.records)
        for name, types in values.items():
            for _type, records in types.items():
                data_for = getattr(self, f'_data_for_{_type}')
                record = Record.new(
                    zone,
                    name,
                    data_for(_type, records),
                    source=self,
                    lenient=lenient,
                )
                zone.add_record(record, lenient=lenient)

        exists = zone.name in self._zone_records
        self.log.info(
            'populate:   found %s records, exists=%s',
            len(zone.records) - before,
            exists,
        )
        return exists

    def supports(self, record):
        # DNS Made Easy does not support empty/NULL SRV records
        #
        # Attempting to sync such a record would generate the following error
        #
        # octodns.provider.dnsmadeeasy.DnsMadeEasyClientBadRequest:
        #      - Record value may not be a standalone dot.
        #
        # Skip the record and continue
        if record._type == "SRV":
            if 'value' in record.data:
                targets = (record.data['value']['target'],)
            else:
                targets = [value['target'] for value in record.data['values']]

            if "." in targets:
                self.log.warning(
                    'supports: unsupported %s record with target (%s)',
                    record._type,
                    targets,
                )
                return False

        return super().supports(record)

    def _process_desired_zone(self, desired):
        for record in desired.records:
            if record._type == 'TXT' and any('"' in v for v in record.values):
                msg = 'Quotes not supported in TXT values'
                fallback = 'removing them'
                self.supports_warn_or_except(msg, fallback)
                record = record.copy()
                record.values = [v.replace('"', '') for v in record.values]
                desired.add_record(record, replace=True)

        return desired

    def _params_for_multiple(self, record):
        for value in record.values:
            yield {
                'value': value,
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    _params_for_A = _params_for_multiple
    _params_for_AAAA = _params_for_multiple

    # An A record with this name must exist in this domain for
    # this NS record to be valid. Need to handle checking if
    # there is an A record before creating NS
    _params_for_NS = _params_for_multiple

    def _params_for_single(self, record):
        yield {
            'value': record.value,
            'name': record.name,
            'ttl': record.ttl,
            'type': record._type,
        }

    _params_for_CNAME = _params_for_single
    _params_for_PTR = _params_for_single
    _params_for_ALIAS = _params_for_single

    def _params_for_MX(self, record):
        for value in record.values:
            yield {
                'value': value.exchange,
                'name': record.name,
                'mxLevel': value.preference,
                'ttl': record.ttl,
                'type': record._type,
            }

    def _params_for_SRV(self, record):
        for value in record.values:
            yield {
                'value': value.target,
                'name': record.name,
                'port': value.port,
                'priority': value.priority,
                'ttl': record.ttl,
                'type': record._type,
                'weight': value.weight,
            }

    def _params_for_TXT(self, record):
        # DNSMadeEasy doesn't need chunking, it accepts the record and will chunk it itself
        # DNSMadeEasy does not want values escaped
        for value in record.values:
            value = value.replace('\\;', ';')
            yield {
                'value': f'"{value}"',
                'name': record.name,
                'ttl': record.ttl,
                'type': record._type,
            }

    def _params_for_CAA(self, record):
        for value in record.values:
            yield {
                'value': value.value,
                'issuerCritical': value.flags,
                'name': record.name,
                'caaType': value.tag,
                'ttl': record.ttl,
                'type': record._type,
            }

    def _mod_Create(self, change):
        creations = []
        new = change.new
        params_for = getattr(self, f'_params_for_{new._type}')
        for params in params_for(new):
            creations.append(params)
        return new.zone, [], creations

    def _mod_Delete(self, change):
        deletions = []
        existing = change.existing
        zone = existing.zone
        for record in self.zone_records(zone):
            if (
                existing.name == record['name']
                and existing._type == record['type']
            ):
                deletions.append(record['id'])
        return zone, deletions, []

    def _mod_Update(self, change):
        _, deletions, _ = self._mod_Delete(change)
        zone, _, creations = self._mod_Create(change)
        return zone, deletions, creations

    def _apply(self, plan):
        desired = plan.desired
        changes = plan.changes
        self.log.debug(
            '_apply: zone=%s, len(changes)=%d', desired.name, len(changes)
        )

        domain_name = desired.name[:-1]
        try:
            self._client.domain(domain_name)
        except DnsMadeEasyClientNotFound:
            self.log.debug('_apply:   no matching zone, creating domain')
            self._client.domain_create(domain_name)

        zone_operations = {}

        # Optimise our changes into a single set of creates/delete operations for each zone
        for change in changes:
            class_name = change.__class__.__name__
            zone, mod_del, mod_create = getattr(self, f'_mod_{class_name}')(
                change
            )
            if zone.name in zone_operations:
                zone_operations[zone.name]['deletions'].extend(mod_del)
                zone_operations[zone.name]['creations'].extend(mod_create)
            else:
                zone_operations[zone.name] = {
                    'zone': zone,
                    'deletions': mod_del,
                    'creations': mod_create,
                }

        # Perform our operations
        for zone_name, operation in zone_operations.items():
            if operation['deletions']:
                self._client.record_multi_delete(
                    zone_name, operation['deletions']
                )
            if operation['creations']:
                self._client.record_multi_create(
                    zone_name, operation['creations']
                )

        # Clear out the cache if any
        self._zone_records.pop(desired.name, None)
