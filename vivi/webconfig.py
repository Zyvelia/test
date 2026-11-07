"""Validate explicit dashboard origins; native listeners stay on loopback or container networks."""
import os
import re
from urllib.parse import urlsplit

def dashboard_endpoint(redirect):
    if any(ord(c)<32 for c in redirect):raise ValueError('Invalid control character in dashboard redirect.')
    parsed=urlsplit(redirect)
    if parsed.path!='/callback' or parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:raise ValueError('Dashboard redirect must use /callback with no credentials, query or fragment.')
    host=parsed.hostname;scheme=parsed.scheme
    if not host or len(host)>253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host) or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.')):raise ValueError('Choose a valid dashboard hostname.')
    if scheme=='http' and host not in {'localhost','127.0.0.1'}:raise ValueError('HTTP dashboard redirects are allowed only on localhost or 127.0.0.1. Use HTTPS for a public domain.')
    if scheme not in {'http','https'}:raise ValueError('Dashboard redirect must use loopback HTTP or HTTPS.')
    public_port=parsed.port if parsed.port is not None else (443 if scheme=='https' else 80)
    if not 1<=public_port<=65535:raise ValueError('Invalid dashboard port.')
    local_port=int(os.getenv('DASHBOARD_LISTEN_PORT','').strip() or (8765 if scheme=='https' else public_port))
    if not 1<=local_port<=65535:raise ValueError('Invalid dashboard listener port.')
    if scheme=='http' and local_port!=public_port:raise ValueError('For loopback HTTP, the listener port must match the redirect port.')
    bind=os.getenv('DASHBOARD_BIND_HOST','127.0.0.1' if scheme=='https' else host)
    if bind not in {'localhost','127.0.0.1'} and not (bind=='0.0.0.0' and os.getenv('VIVI_CONTAINER')=='1'):raise ValueError('An external dashboard bind is allowed only in explicit container mode. Put a trusted HTTPS reverse proxy in front of the loopback listener.')
    return dict(host=host,scheme=scheme,public_port=public_port,port=local_port,bind_host=bind,secure_cookies=scheme=='https')
