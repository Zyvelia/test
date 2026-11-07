"""Host-only GitHub updater. Supports ZIP installations and clean Git checkouts."""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import Request,urlopen
from zipfile import ZipFile
from .host_lock import host_lock

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY='Zyvelia/test'
BRANCH='main'
LIMIT=200*1024*1024
PROTECTED={'.git','.venv','.env','data','node_modules','.update-state.json'}

# No credentials are sent: this updater is for the public upstream repository.
def download(url,target):
    request=Request(url,headers={'User-Agent':'Vivi-Updater','Accept':'application/vnd.github+json'})
    with urlopen(request,timeout=60) as response,target.open('wb') as output:
        total=0
        while chunk:=response.read(1024*1024):
            total+=len(chunk)
            if total>LIMIT:raise ValueError('Update download exceeds the size limit.')
            output.write(chunk)

def latest_commit(work):
    path=work/'commit.json';download(f'https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}',path)
    data=json.loads(path.read_text(encoding='utf-8-sig'));sha=data.get('sha','')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('GitHub returned an invalid commit ID.')
    return sha

def protected(path):
    parts=PurePosixPath(path).parts
    return any(part.lower() in PROTECTED or (part.lower().startswith('.env.') and part.lower()!='.env.example') for part in parts) or PurePosixPath(path).suffix.lower() in {'.sqlite','.sqlite3','.db','.vbackup','.key'}

def safe_path(root,name):
    path=PurePosixPath(name)
    if not path.parts or path.is_absolute() or any(p in {'.','..'} or ':' in p or '\\' in p or p.endswith((' ','.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',p) for p in path.parts):raise ValueError('Unsafe update path.')
    result=root.joinpath(*path.parts)
    for parent in [result,*result.parents]:
        if parent==root:break
        if parent.is_symlink():raise ValueError(f'Update refuses symlink path: {name}')
    if result.exists() and not result.is_file():raise ValueError(f'Update path is not a file: {name}')
    return result

def extract(archive,folder):
    files={};seen=set();size=0;prefix=None
    with ZipFile(archive) as zipped:
        if len(zipped.infolist())>10000:raise ValueError('Too many archive files.')
        for item in zipped.infolist():
            parts=PurePosixPath(item.filename).parts
            if len(parts)<2:
                if item.is_dir():continue
                raise ValueError('Unexpected archive layout.')
            if prefix is None:prefix=parts[0]
            if parts[0]!=prefix:raise ValueError('Unexpected archive roots.')
            name='/'.join(parts[1:])
            if item.is_dir():continue
            if stat.S_ISLNK(item.external_attr>>16):raise ValueError('Archive symlinks are not supported.')
            path=safe_path(folder,name)
            if protected(name):continue
            if name.casefold() in seen:raise ValueError('Duplicate archive path.')
            seen.add(name.casefold());size+=item.file_size
            if size>500*1024*1024:raise ValueError('Expanded update exceeds size limit.')
            path.parent.mkdir(parents=True,exist_ok=True)
            with zipped.open(item) as source,path.open('wb') as output:shutil.copyfileobj(source,output)
            mode=(item.external_attr>>16)&0o777
            path.chmod(mode or 0o644);files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    if not {'vivi/bot.py','vivi/updater.py','requirements.txt','start.bat','start.sh'}<=files.keys():raise ValueError('Archive is not a compatible Vivi update.')
    return files

def write_json(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(temporary,path)

def git(root,*args):return subprocess.check_output(['git','-c','core.hooksPath='+str(root/'data'/'no-hooks'),*args],cwd=root,text=True,encoding='utf-8',errors='replace',stderr=subprocess.STDOUT).strip()

def check_git(root):
    if not (root/'.git').exists():return False
    if git(root,'status','--porcelain'):raise ValueError('Git checkout has local changes. Commit/stash them before updating; nothing was overwritten.')
    if git(root,'branch','--show-current')!=BRANCH:raise ValueError('Automatic updates require the main branch.')
    remote=git(root,'remote','get-url','origin').rstrip('/')
    if remote not in {f'https://github.com/{REPOSITORY}',f'https://github.com/{REPOSITORY}.git',f'git@github.com:{REPOSITORY}.git'}:raise ValueError('Git origin must point to Zyvelia/test.')
    return True

def install_dependencies(root,staged):
    if (root/'requirements.txt').exists() and (root/'requirements.txt').read_bytes()==(staged/'requirements.txt').read_bytes():return
    print('Installing updated Python dependencies…',flush=True)
    subprocess.run([sys.executable,'-m','pip','install','-r',str(staged/'requirements.txt')],cwd=staged,check=True)

def recover(root):
    journal=root/'data'/'update-pending.json'
    if not journal.exists():return
    data=json.loads(journal.read_text(encoding='utf-8-sig'));backup=safe_backup(root,data['backup'])
    for name,existed in data['files'].items():
        if protected(name):raise ValueError('Invalid recovery path.')
        target=safe_path(root,name)
        if existed:
            source=safe_path(backup,name)
            if not source.is_file():raise ValueError('Recovery backup is incomplete. Restore the update backup manually.')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        else:target.unlink(missing_ok=True)
    journal.unlink();print('Recovered files from an interrupted update.',flush=True)

def safe_backup(root,name):
    if not re.fullmatch(r'[0-9]+-[0-9a-f]{12}',name):raise ValueError('Invalid update backup ID.')
    path=root/'data'/'update-backups'/name
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('Unsafe update backup path.')
    return path

def apply_zip(root,staged,files,sha):
    state_path=root/'data'/'update-state.json';previous=json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.exists() else {}
    old=previous.get('files',{});changed=[];removed=[]
    for name,digest in files.items():
        target=safe_path(root,name)
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:changed.append(name)
    for name,digest in old.items():
        if name in files or protected(name):continue
        target=safe_path(root,name)
        # Preserve user-modified files removed upstream.
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:removed.append(name)
    if not changed and not removed:
        write_json(state_path,dict(commit=sha,files=files));print('Vivi is already up to date.');return
    backup_id=f'{time.time_ns()}-{sha[:12]}';backup=safe_backup(root,backup_id);backup.mkdir(parents=True)
    paths={name:safe_path(root,name).exists() for name in changed+removed}
    for name,existed in paths.items():
        if existed:
            target=safe_path(backup,name);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(safe_path(root,name),target)
    write_json(backup/'backup-info.json',dict(commit=sha,files=paths,previous_state=previous))
    journal=root/'data'/'update-pending.json';write_json(journal,dict(backup=backup_id,files=paths))
    try:
        for name in changed:
            target=safe_path(root,name);target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.vivi-update-',delete=False) as handle:temporary=Path(handle.name)
            try:
                shutil.copy2(safe_path(staged,name),temporary);os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
        for name in removed:safe_path(root,name).unlink()
        write_json(state_path,dict(commit=sha,files=files));journal.unlink()
    except BaseException:
        recover(root);raise
    print(f'Updated {len(changed)} files; removed {len(removed)} unchanged obsolete files. Backup: {backup}',flush=True)

def rollback(root,backup_id):
    root=Path(root).resolve();recover(root);backup=safe_backup(root,backup_id)
    info=json.loads((backup/'backup-info.json').read_text(encoding='utf-8-sig'))
    # Only explicit archive-update backups can be rolled back here.
    if not isinstance(info.get('files'),dict):raise ValueError('Invalid backup metadata.')
    for name,existed in info['files'].items():
        if protected(name) or type(existed) is not bool:raise ValueError('Invalid backup metadata.')
        safe_path(root,name)
        if existed and not safe_path(backup,name).is_file():raise ValueError('Backup is incomplete.')
    write_json(root/'data'/'update-pending.json',dict(backup=backup_id,files=info['files']))
    recover(root);write_json(root/'data'/'update-state.json',info.get('previous_state',{}))
    print('Source files restored. Run setup to restore compatible dependencies before starting. Database and .env were not rolled back.')

def update(root=ROOT,check=False):
    root=Path(root).resolve();(root/'data').mkdir(exist_ok=True);recover(root);is_git=check_git(root)
    with tempfile.TemporaryDirectory(prefix='vivi-update-') as temporary:
        work=Path(temporary);sha=latest_commit(work)
        current=git(root,'rev-parse','HEAD') if is_git else json.loads((root/'data'/'update-state.json').read_text(encoding='utf-8-sig')).get('commit') if (root/'data'/'update-state.json').exists() else None
        if check:
            print(('Up to date' if current==sha else 'Update available' if current else 'Installed revision unknown; run the updater to compare files')+f' · GitHub {sha[:12]}');return
        if current==sha:
            state={} if is_git else json.loads((root/'data'/'update-state.json').read_text(encoding='utf-8-sig'))
            unchanged=is_git or bool(state.get('files')) and all(safe_path(root,name).is_file() and hashlib.sha256(safe_path(root,name).read_bytes()).hexdigest()==digest for name,digest in state['files'].items() if not protected(name))
            if unchanged:print('Vivi is already up to date.');return
        archive=work/'update.zip';download(f'https://codeload.github.com/{REPOSITORY}/zip/{sha}',archive)
        staged=work/'source';staged.mkdir();files=extract(archive,staged)
        for name in files:safe_path(root,name)
        if is_git:
            git(root,'fetch','origin',BRANCH)
            git(root,'merge-base','--is-ancestor',current,sha)
            # Fetch must actually contain the immutable commit we downloaded.
            if git(root,'rev-parse','origin/main')!=sha:raise ValueError('GitHub changed during the update. Run it again.')
            install_dependencies(root,staged);git(root,'merge','--ff-only',sha)
            print(f'Updated Git checkout to {sha[:12]}. Previous commit: {current}. Local runtime files were preserved.')
        else:
            install_dependencies(root,staged);apply_zip(root,staged,files,sha)
        print('Update complete. Start Vivi normally.',flush=True)

def automatic_update(root=ROOT):
    from dotenv import load_dotenv
    load_dotenv(Path(root)/'.env')
    if os.getenv('AUTO_UPDATE','false').strip().lower() not in {'true','1','yes'}:return
    print('Checking GitHub before starting Vivi…',flush=True)
    update(root)

def main():
    parser=argparse.ArgumentParser(description='Update Vivi from GitHub main without downloading files manually. Stop Vivi first.');options=parser.add_mutually_exclusive_group();options.add_argument('--check',action='store_true',help='Check GitHub without installing files or dependencies.');options.add_argument('--rollback',metavar='BACKUP_ID',help='Restore source files from an archive-update backup; stop Vivi first.');args=parser.parse_args()
    try:
        with host_lock(ROOT):
            if args.rollback:rollback(ROOT,args.rollback)
            else:update(ROOT,args.check)
    except (Exception,KeyboardInterrupt) as error:
        print(f'Update stopped: {error}. Your .env and data folder are not replaced. If dependency installation failed, rerun setup before starting.',file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
