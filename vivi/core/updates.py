"""Read-only release checks; installation is always a separate host action."""
import os
import re
import time
from vivi import __version__

def version(value):
    m=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',value)
    return tuple(map(int,m.groups())) if m else None

async def check_updates(service,force=False):
    cached=getattr(service,'release_cache',None)
    if cached and not force and cached[0]>time.time(): return cached[1]
    repo=os.getenv('UPDATE_REPOSITORY','Zyvelia/test')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,39}/[A-Za-z0-9_.-]{1,100}',repo) or repo.split('/')[-1] in {'.','..'}: raise ValueError('Invalid host UPDATE_REPOSITORY.')
    headers={'Accept':'application/vnd.github+json'}
    token=os.getenv('UPDATE_GITHUB_TOKEN','')
    if token: headers['Authorization']='Bearer '+token
    async with service.session.get(f'https://api.github.com/repos/{repo}/releases/latest',headers=headers,allow_redirects=False) as response:
        if response.status==404: result=f'Vivi {__version__}: no published release was found (or the release repository is private).'
        elif response.status!=200: raise ValueError(f'Release check returned HTTP {response.status}. Check host access or retry later.')
        else:
            data=await response.json(); tag=str(data.get('tag_name',''))[:100]; current,latest=version(__version__),version(tag)
            state='Update available' if current and latest and latest>current else 'Up to date' if current and latest else 'Compare this release manually'
            result=f'{state}: installed {__version__}, latest {tag}. https://github.com/{repo}/releases/latest · No files were installed.'
    service.release_cache=(time.time()+1800,result); return result
