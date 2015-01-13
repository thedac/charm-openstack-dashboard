# vim: set ts=4:et
from charmhelpers.core.hookenv import (
    config,
    relation_ids,
    related_units,
    relation_get,
    local_unit,
    unit_get,
    log
)
from charmhelpers.contrib.openstack.context import (
    OSContextGenerator,
    HAProxyContext,
    context_complete
)
from charmhelpers.contrib.hahelpers.apache import (
    get_cert
)
from charmhelpers.contrib.network.ip import (
    get_ipv6_addr,
    format_ipv6_addr,
)

from charmhelpers.core.host import pwgen

from base64 import b64decode
import os


class HorizonHAProxyContext(HAProxyContext):
    def __call__(self):
        '''
        Horizon specific HAProxy context; haproxy is used all the time
        in the openstack dashboard charm so a single instance just
        self refers
        '''
        cluster_hosts = {}
        l_unit = local_unit().replace('/', '-')
        if config('prefer-ipv6'):
            cluster_hosts[l_unit] = get_ipv6_addr(exc_list=[config('vip')])[0]
        else:
            cluster_hosts[l_unit] = unit_get('private-address')

        for rid in relation_ids('cluster'):
            for unit in related_units(rid):
                _unit = unit.replace('/', '-')
                addr = relation_get('private-address', rid=rid, unit=unit)
                cluster_hosts[_unit] = addr

        log('Ensuring haproxy enabled in /etc/default/haproxy.')
        with open('/etc/default/haproxy', 'w') as out:
            out.write('ENABLED=1\n')

        ctxt = {
            'units': cluster_hosts,
            'service_ports': {
                'dash_insecure': [80, 70],
                'dash_secure': [443, 433]
            }
        }
        return ctxt


# NOTE: this is a stripped-down version of
# contrib.openstack.IdentityServiceContext
class IdentityServiceContext(OSContextGenerator):
    interfaces = ['identity-service']

    def __call__(self):
        log('Generating template context for identity-service')
        ctxt = {}
        regions = set()

        for rid in relation_ids('identity-service'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                serv_host = rdata.get('service_host')
                serv_host = format_ipv6_addr(serv_host) or serv_host
                region = rdata.get('region')

                local_ctxt = {
                    'service_port': rdata.get('service_port'),
                    'service_host': serv_host,
                    'service_protocol':
                    rdata.get('service_protocol') or 'http'
                }

                if not context_complete(local_ctxt):
                    continue

                # Update the service endpoint and title for each available
                # region in order to support multi-region deployments
                if region is not None:
                    endpoint = ("%(service_protocol)s://%(service_host)s"
                                ":%(service_port)s/v2.0") % local_ctxt
                    for reg in region.split():
                        regions.add((endpoint, reg))

                if len(ctxt) == 0:
                    ctxt = local_ctxt

        if len(regions) > 1:
            avail_regions = map(lambda r: {'endpoint': r[0], 'title': r[1]},
                                regions)
            ctxt['regions'] = sorted(avail_regions)
        return ctxt


class HorizonContext(OSContextGenerator):
    def __call__(self):
        ''' Provide all configuration for Horizon '''
        ctxt = {
            'compress_offline': config('offline-compression') in ['yes', True],
            'debug': config('debug') in ['yes', True],
            'default_role': config('default-role'),
            "webroot": config('webroot'),
            "ubuntu_theme": config('ubuntu-theme') in ['yes', True],
            "secret": config('secret') or pwgen(),
            'support_profile': config('profile')
            if config('profile') in ['cisco'] else None,
            "neutron_network_lb": config("neutron-network-lb"),
            "neutron_network_firewall": config("neutron-network-firewall"),
            "neutron_network_vpn": config("neutron-network-vpn"),
        }

        return ctxt


class ApacheContext(OSContextGenerator):
    def __call__(self):
        ''' Grab cert and key from configuraton for SSL config '''
        ctxt = {
            'http_port': 70,
            'https_port': 433
        }
        return ctxt


class ApacheSSLContext(OSContextGenerator):
    def __call__(self):
        ''' Grab cert and key from configuration for SSL config '''
        (ssl_cert, ssl_key) = get_cert()
        if None not in [ssl_cert, ssl_key]:
            with open('/etc/ssl/certs/dashboard.cert', 'w') as cert_out:
                cert_out.write(b64decode(ssl_cert))
            with open('/etc/ssl/private/dashboard.key', 'w') as key_out:
                key_out.write(b64decode(ssl_key))
            os.chmod('/etc/ssl/private/dashboard.key', 0600)
            ctxt = {
                'ssl_configured': True,
                'ssl_cert': '/etc/ssl/certs/dashboard.cert',
                'ssl_key': '/etc/ssl/private/dashboard.key',
            }
        else:
            # Use snakeoil ones by default
            ctxt = {
                'ssl_configured': False,
            }
        return ctxt


class RouterSettingContext(OSContextGenerator):
    def __call__(self):
        ''' Enable/Disable Router Tab on horizon '''
        ctxt = {
            'disable_router': False if config('profile') in ['cisco'] else True
        }
        return ctxt
