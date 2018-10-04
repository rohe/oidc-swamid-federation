#!/usr/bin/env python3
import cherrypy
import importlib
import logging
import os
import sys
from urllib.parse import urlparse

import requests
from cryptojwt.key_jar import init_key_jar

from fedoidcendpoint.endpoint_context import EndpointContext
from oidcop.cookie import CookieDealer

logger = logging.getLogger("")
LOGFILE_NAME = 'op.log'
hdlr = logging.FileHandler(LOGFILE_NAME)
base_formatter = logging.Formatter(
    "%(asctime)s %(name)s:%(levelname)s %(message)s")

hdlr.setFormatter(base_formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.DEBUG)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-t', dest='tls', action='store_true')
    parser.add_argument('-k', dest='insecure', action='store_true')
    parser.add_argument(dest="config")
    args = parser.parse_args()

    folder = os.path.abspath(os.curdir)
    sys.path.insert(0, ".")
    config = importlib.import_module(args.config)
    _webserver_config = config.CONFIG['webserver']

    from op import OpenIDProvider

    try:
        _port = int(_webserver_config['port'])
    except KeyError:
        if args.tls:
            _port = 443
        else:
            _port = 80

    cherrypy.config.update(
        {'environment': 'production',
         'log.error_file': 'error.log',
         'log.access_file': 'access.log',
         'tools.trailing_slash.on': False,
         'server.socket_host': '0.0.0.0',
         'log.screen': True,
         'tools.sessions.on': True,
         'tools.encode.on': True,
         'tools.encode.encoding': 'utf-8',
         'server.socket_port': _port
         })

    provider_config = {
        '/': {
            'root_path': 'localhost',
            'log.screen': True
        },
        '/public': {
            'tools.staticdir.dir': os.path.join(folder, 'public'),
            'tools.staticdir.debug': True,
            'tools.staticdir.on': True,
            'tools.staticdir.content_types': {
                'json': 'application/json',
                'jwks': 'application/json',
                'jose': 'application/jose'
            },
            'log.screen': True,
            'cors.expose_public.on': True
        }}

    _server_info_config = config.CONFIG['server_info']
    _jwks_config = _server_info_config['jwks']

    _kj = init_key_jar(owner=_server_info_config['issuer'], **_jwks_config)

    if args.insecure:
        verify_ssl = False
    else:
        verify_ssl = True

    cookie_dealer = CookieDealer(**_server_info_config['cookie_dealer'])

    endpoint_context = EndpointContext(_server_info_config, keyjar=_kj,
                                       cwd=folder, httpcli=requests.request,
                                       verify_ssl=verify_ssl,
                                       cookie_dealer=cookie_dealer)


    for endp in endpoint_context.endpoint.values():
        p = urlparse(endp.endpoint_path)
        _vpath = p.path.split('/')
        if _vpath[0] == '':
            endp.vpath = _vpath[1:]
        else:
            endp.vpath = _vpath

    cherrypy.tree.mount(
        OpenIDProvider(config, endpoint_context),
        '/', provider_config)


    _webserver_config = config.CONFIG['webserver']

    # If HTTPS
    if args.tls:
        cherrypy.server.ssl_certificate = _webserver_config['cert']
        cherrypy.server.ssl_private_key = _webserver_config['key']
        try:
            _cert_chain = _webserver_config['cert_chain']
        except KeyError:
            pass
        else:
            if _cert_chain:
                cherrypy.server.ssl_certificate_chain = _cert_chain

    cherrypy.engine.start()
    cherrypy.engine.block()
