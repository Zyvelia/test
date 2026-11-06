#!/usr/bin/env python3
"""Run Gradle through the cloud's inherited HTTPS proxy without logging secrets."""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

root = Path(__file__).resolve().parents[1]
proxy = urlparse(os.environ.get('HTTPS_PROXY', os.environ.get('https_proxy', '')))
args = [str(root / 'gradlew')]
if proxy.hostname:
    for protocol in ('https', 'http'):
        args.extend([f'-D{protocol}.proxyHost={proxy.hostname}',
                     f'-D{protocol}.proxyPort={proxy.port or 80}'])
args.extend(sys.argv[1:] or ['build', '--no-daemon', '--console=plain'])
sys.exit(subprocess.call(args, cwd=root))
