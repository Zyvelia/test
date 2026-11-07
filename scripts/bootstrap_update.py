"""One-time updater bootstrap for old ZIP installs; run from Vivi's folder with its venv."""
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.request import Request,urlopen

REPO='Zyvelia/test'
def read(url):
    with urlopen(Request(url,headers={'User-Agent':'Vivi-Updater-Bootstrap'}),timeout=60) as response:
        data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise ValueError('Unexpected bootstrap download size.')
        return data

def main():
    root=Path.cwd().resolve()
    if not (root/'vivi/bot.py').is_file() or Path(sys.prefix).resolve()!=(root/'.venv').resolve():raise ValueError('Open a terminal in your Vivi folder and run with its .venv Python. Stop Vivi first.')
    sha=json.loads(read(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('Invalid GitHub revision.')
    with tempfile.TemporaryDirectory(prefix='vivi-bootstrap-') as temporary:
        folder=Path(temporary)/'vivi_bootstrap';folder.mkdir();(folder/'__init__.py').write_text('')
        for name in ('host_lock.py','updater.py'):(folder/name).write_bytes(read(f'https://raw.githubusercontent.com/{REPO}/{sha}/vivi/{name}'))
        sys.path.insert(0,temporary)
        from vivi_bootstrap.host_lock import host_lock
        from vivi_bootstrap.updater import update
        with host_lock(root):update(root)

if __name__=='__main__':
    try:main()
    except (Exception,KeyboardInterrupt) as error:raise SystemExit(f'Updater bootstrap stopped: {error}')
