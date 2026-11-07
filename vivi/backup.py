"""Host-only authenticated full-data backups. Keys and .env are never archived."""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import secrets
import shutil
import sqlite3
import stat
import tempfile
import zipfile

from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
MAGIC=b'VIVI-BACKUP-1\x00'
CHUNK=1024*1024
LIMIT=10*1024**3

def default_key():
 return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.config')))/'Vivi'/'backup.key'

def key_bytes(path,root):
 path=Path(path).expanduser().resolve()
 if path.is_relative_to(Path(root).resolve()):raise ValueError('Keep the encryption key outside the Vivi checkout.')
 key=path.read_bytes()
 if len(key)!=32:raise ValueError('The backup key must contain exactly 32 bytes; generate it with the key command.')
 return key

def generate_key(path):
 path=Path(path).expanduser();path.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as out:out.write(secrets.token_bytes(32))
 return path

def encrypt_file(source,target,key):
 if len(key)!=32:raise ValueError('AES-256 requires a 32-byte key.')
 nonce=secrets.token_bytes(12);header=MAGIC+nonce
 cipher=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor();cipher.authenticate_additional_data(header)
 fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'wb') as out,open(source,'rb') as src:
   out.write(header)
   while chunk:=src.read(CHUNK):out.write(cipher.update(chunk))
   out.write(cipher.finalize());out.write(cipher.tag);out.flush();os.fsync(out.fileno())
 except BaseException:
  Path(target).unlink(missing_ok=True);raise

def decrypt_file(source,target,key):
 if len(key)!=32:raise ValueError('AES-256 requires a 32-byte key.')
 source=Path(source)
 if source.stat().st_size<len(MAGIC)+12+16:raise ValueError('Invalid backup header.')
 with source.open('rb') as src:
  header=src.read(len(MAGIC)+12)
  if not header.startswith(MAGIC):raise ValueError('Unknown backup format.')
  src.seek(-16,2);tag=src.read(16);remaining=source.stat().st_size-len(header)-16
  src.seek(len(header));cipher=Cipher(algorithms.AES(key),modes.GCM(header[-12:],tag)).decryptor();cipher.authenticate_additional_data(header)
  fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  try:
   with os.fdopen(fd,'wb') as out:
    while remaining:
     chunk=src.read(min(CHUNK,remaining))
     if not chunk:raise ValueError('Truncated backup.')
     remaining-=len(chunk);out.write(cipher.update(chunk))
    out.write(cipher.finalize())
  except BaseException:
   Path(target).unlink(missing_ok=True);raise

def create(root,database,key_file,output=None):
 root=Path(root).resolve();data=root/'data';database=Path(database).resolve()
 key=key_bytes(key_file,root)
 if not database.is_file() or not database.is_relative_to(data.resolve()):raise ValueError('Choose an existing Vivi database under data/.')
 folder=data/'encrypted-backups';folder.mkdir(parents=True,exist_ok=True)
 output=Path(output) if output else folder/f'full-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}-{secrets.token_hex(4)}.vbackup'
 if output.exists():raise ValueError('Backup output already exists.')
 output.parent.mkdir(parents=True,exist_ok=True)
 temporary=output.with_name(output.name+'.tmp-'+secrets.token_hex(4))
 with tempfile.TemporaryDirectory(prefix='vivi-full-') as work:
  work=Path(work);snapshot=work/database.name
  with closing(sqlite3.connect(database)) as src,closing(sqlite3.connect(snapshot)) as dst:
   src.backup(dst)
   if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed.')
  archive=work/'data.zip';manifest={'version':1,'database':'data/'+database.name,'files':{},'excluded':['.env','encryption key','backups','encrypted-backups','audio','locks','SQLite journals','heartbeat']}
  with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
   candidates=[(snapshot,'data/'+database.name)]
   for path in data.rglob('*'):
    rel=path.relative_to(data)
    if any(part in {'backups','encrypted-backups','audio'} for part in rel.parts):continue
    if path.is_symlink() or not path.is_file() or path.resolve()==database:continue
    if path.name=='.env' or path.name.startswith('.env.'):continue
    if path.name.endswith(('.lock','-journal','-wal','-shm')) or path.name=='heartbeat.json':continue
    if path.suffix=='.vbackup' or '.tmp-' in path.name or path.resolve() in {output.resolve(),temporary.resolve()}:continue
    if path.suffix=='.sqlite3':continue  # Only the selected, consistent online snapshot is archived.
    if not path.resolve().is_relative_to(data.resolve()):raise ValueError('Data file escapes its directory.')
    candidates.append((path,'data/'+rel.as_posix()))
   if len(candidates)>99999 or sum(path.stat().st_size for path,name in candidates)>LIMIT:raise ValueError('Data exceeds the supported restore limits.')
   for path,name in candidates:
    before=path.stat();digest=hashlib.sha256();count=0
    with path.open('rb') as src,z.open(name,'w',force_zip64=True) as dst:
     while chunk:=src.read(CHUNK):digest.update(chunk);count+=len(chunk);dst.write(chunk)
    after=path.stat()
    if count!=before.st_size or before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:raise ValueError('A data file changed during backup; retry after stopping Vivi.')
    manifest['files'][name]={'size':count,'sha256':digest.hexdigest()}
   manifest_body=json.dumps(manifest)
   if len(manifest_body.encode())>32*1024*1024:raise ValueError('Manifest exceeds restore limits.')
   z.writestr('manifest.json',manifest_body)
  try:encrypt_file(archive,temporary,key);os.replace(temporary,output)
  finally:temporary.unlink(missing_ok=True)
 return output

def restore(source,key_file,target,root=ROOT):
 key=key_bytes(key_file,root);target=Path(target).resolve()
 if target.is_relative_to(Path(root).resolve()):raise ValueError('Restore outside the live checkout.')
 if target.exists() and (not target.is_dir() or any(target.iterdir())):raise ValueError('Restore target must be a new or empty directory.')
 target.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='vivi-decrypt-') as work,tempfile.TemporaryDirectory(prefix='.vivi-restore-',dir=target.parent) as stage:
  archive=Path(work)/'verified.zip';decrypt_file(source,archive,key)  # Authentication completes before any extraction.
  with zipfile.ZipFile(archive) as z:
   infos=z.infolist()
   if len(infos)>100000 or sum(x.file_size for x in infos)>LIMIT:raise ValueError('Archive exceeds restore limits.')
   if len({x.filename for x in infos})!=len(infos):raise ValueError('Duplicate archive paths.')
   if z.getinfo('manifest.json').file_size>32*1024*1024:raise ValueError('Manifest is too large.')
   manifest=json.loads(z.read('manifest.json'))
   if manifest.get('version')!=1 or set(manifest.get('files',{}))!={x.filename for x in infos if x.filename!='manifest.json'}:raise ValueError('Invalid backup manifest.')
   for info in infos:
    if info.filename=='manifest.json':continue
    name=PurePosixPath(info.filename)
    if name.is_absolute() or '\\' in info.filename or ':' in info.filename or '..' in name.parts or not name.parts or name.parts[0]!='data':raise ValueError('Unsafe archive path.')
    reserved={'CON','PRN','AUX','NUL'}|{f'COM{n}' for n in range(1,10)}|{f'LPT{n}' for n in range(1,10)}
    if any(part.endswith(('.', ' ')) or part.split('.')[0].upper() in reserved for part in name.parts):raise ValueError('Archive path is not portable to Windows.')
    if stat.S_ISLNK(info.external_attr>>16) or info.is_dir():raise ValueError('Unsupported archive entry.')
    destination=Path(stage).joinpath(*name.parts);destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);digest=hashlib.sha256();count=0
    with z.open(info) as src,os.fdopen(fd,'wb') as out:
     while chunk:=src.read(CHUNK):out.write(chunk);digest.update(chunk);count+=len(chunk)
    expected=manifest['files'][info.filename]
    if count!=expected['size'] or digest.hexdigest()!=expected['sha256']:raise ValueError('Backup file checksum mismatch.')
   database=PurePosixPath(manifest['database'])
   if str(database) not in manifest['files'] or database.suffix!='.sqlite3':raise ValueError('Invalid database entry.')
   with closing(sqlite3.connect(Path(stage).joinpath(*database.parts))) as db:
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored database failed integrity check.')
  if target.exists():target.rmdir()
  os.replace(stage,target)
 return target

def main():
 load_dotenv(ROOT/'.env');parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('action',choices=['key','create','restore']);parser.add_argument('--key',default=os.getenv('BACKUP_KEY_FILE') or str(default_key()))
 parser.add_argument('--file');parser.add_argument('--target')
 args=parser.parse_args()
 try:
  if args.action=='key':
   if Path(args.key).expanduser().resolve().is_relative_to(ROOT.resolve()):raise ValueError('Keep keys outside the checkout.')
   print('Private key file created:',generate_key(args.key));return
  if args.action=='create':
   from vivi.core.storage import database_path
   print('Encrypted backup created:',create(ROOT,database_path(ROOT),args.key,args.file));return
  if not args.file or not args.target:raise ValueError('Restore requires --file and --target.')
  print('Authenticated data restored into:',restore(args.file,args.key,args.target))
 except Exception as error:
  print(f'Backup operation failed ({type(error).__name__}): check paths, key, free space and archive integrity. Existing live data was not restored over.')
  raise SystemExit(1)

if __name__=='__main__':main()
