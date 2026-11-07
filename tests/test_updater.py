import io
import json
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch,Mock
from zipfile import ZipFile,ZipInfo
from vivi import updater
from vivi.host_lock import host_lock

SHA='a'*40
class UpdaterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'installed';self.root.mkdir();(self.root/'data').mkdir();self.stage=self.base/'staged';self.stage.mkdir()
 def archive(self,extra=None):
  path=self.base/'update.zip'
  with ZipFile(path,'w') as z:
   for name,content in {'vivi/bot.py':'new code','vivi/updater.py':'updater','requirements.txt':'same deps','start.bat':'start','start.sh':'start',**(extra or {})}.items():z.writestr('test-'+SHA+'/'+name,content)
  return path
 def test_extract_skips_secrets_database_and_preserves_example(self):
  files=updater.extract(self.archive({'.env':'token','data/bot.sqlite3':'db','.venv/bin/python':'bad','node_modules/x':'x','.env.local':'secret','.env.example':'example','private.key':'key'}),self.stage)
  self.assertIn('.env.example',files)
  for name in ['.env','data/bot.sqlite3','.venv/bin/python','node_modules/x','.env.local','private.key']:self.assertNotIn(name,files)
 def test_rejects_traversal_windows_paths_symlinks_and_duplicates(self):
  for name in ['../outside','/absolute','vivi/../../outside','vivi\\bad','C:/file','CON','vivi/file:stream','vivi/trailing.']:
   with self.subTest(name=name),self.assertRaises(ValueError):updater.safe_path(self.root,name)
  path=self.base/'bad.zip'
  with ZipFile(path,'w') as z:
   info=ZipInfo('root/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'target')
  with self.assertRaises(ValueError):updater.extract(path,self.stage)
  with ZipFile(path,'w') as z:z.writestr('root/A','a');z.writestr('root/a','b')
  with self.assertRaises(ValueError):updater.extract(path,self.stage)
 def test_existing_symlink_is_never_overwritten(self):
  target=self.base/'outside';target.write_text('safe')
  try:(self.root/'link').symlink_to(target)
  except OSError:self.skipTest('Symlinks unavailable')
  with self.assertRaises(ValueError):updater.safe_path(self.root,'link')
  self.assertEqual(target.read_text(),'safe')
 def test_zip_update_preserves_runtime_and_custom_files_and_can_rollback(self):
  (self.root/'.env').write_text('secret');(self.root/'data/db.sqlite3').write_text('database');(self.root/'custom.png').write_text('custom');(self.root/'vivi').mkdir();(self.root/'vivi/bot.py').write_text('old code')
  files=updater.extract(self.archive(),self.stage);updater.apply_zip(self.root,self.stage,files,SHA)
  self.assertEqual((self.root/'vivi/bot.py').read_text(),'new code');self.assertEqual((self.root/'.env').read_text(),'secret');self.assertEqual((self.root/'data/db.sqlite3').read_text(),'database');self.assertEqual((self.root/'custom.png').read_text(),'custom')
  backup=next((self.root/'data/update-backups').iterdir());self.assertEqual((backup/'vivi/bot.py').read_text(),'old code')
  updater.rollback(self.root,backup.name);self.assertEqual((self.root/'vivi/bot.py').read_text(),'old code');self.assertFalse((self.root/'vivi/updater.py').exists());self.assertEqual((self.root/'data/db.sqlite3').read_text(),'database')
 def test_obsolete_files_only_removed_when_unchanged(self):
  (self.root/'old.py').write_text('old');(self.root/'modified.py').write_text('changed');digest=updater.hashlib.sha256(b'old').hexdigest()
  updater.write_json(self.root/'data/update-state.json',dict(files={'old.py':digest,'modified.py':digest}))
  files=updater.extract(self.archive(),self.stage);updater.apply_zip(self.root,self.stage,files,SHA)
  self.assertFalse((self.root/'old.py').exists());self.assertTrue((self.root/'modified.py').exists())
 def test_interrupted_update_restores_files(self):
  backup=self.root/'data/update-backups'/('123-'+SHA[:12]);(backup/'vivi').mkdir(parents=True);(backup/'vivi/bot.py').write_text('old')
  (self.root/'vivi').mkdir();(self.root/'vivi/bot.py').write_text('partial');(self.root/'new.py').write_text('new')
  updater.write_json(self.root/'data/update-pending.json',dict(backup=backup.name,files={'vivi/bot.py':True,'new.py':False}))
  updater.recover(self.root);self.assertEqual((self.root/'vivi/bot.py').read_text(),'old');self.assertFalse((self.root/'new.py').exists())
 def test_apply_failure_restores_previous_source(self):
  (self.root/'vivi').mkdir();(self.root/'vivi/bot.py').write_text('old')
  files=updater.extract(self.archive(),self.stage)
  with patch.object(updater.os,'replace',side_effect=lambda source,target: (_ for _ in ()).throw(OSError('simulated disk failure')) if str(target).endswith('bot.py') else __import__('os').rename(source,target)):
   with self.assertRaises(OSError):updater.apply_zip(self.root,self.stage,files,SHA)
  self.assertEqual((self.root/'vivi/bot.py').read_text(),'old');self.assertFalse((self.root/'data/update-pending.json').exists())
 def test_running_launcher_blocks_updater(self):
  with host_lock(self.root):
   with self.assertRaises(RuntimeError):
    with host_lock(self.root):pass
  with host_lock(self.root):pass
 def test_dependency_install_only_when_changed_and_failure_stops_update(self):
  files=updater.extract(self.archive(),self.stage);(self.root/'requirements.txt').write_text('same deps')
  with patch.object(updater.subprocess,'run') as run:updater.install_dependencies(self.root,self.stage);run.assert_not_called()
  (self.root/'requirements.txt').write_text('old deps')
  with patch.object(updater.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['pip'])):
   with self.assertRaises(subprocess.CalledProcessError):updater.install_dependencies(self.root,self.stage)
  self.assertFalse((self.root/'vivi/bot.py').exists())
 def test_check_downloads_no_archive_and_installs_nothing(self):
  with patch.object(updater,'latest_commit',return_value=SHA),patch.object(updater,'download') as download,patch.object(updater,'install_dependencies') as install:
   updater.update(self.root,check=True);download.assert_not_called();install.assert_not_called()
  self.assertFalse((self.root/'vivi').exists())
 def test_git_requires_clean_main_and_expected_remote(self):
  (self.root/'.git').mkdir()
  for results in [[' M vivi/bot.py'],['','feature'],['','main','https://evil.example/other']]:
   with patch.object(updater,'git',side_effect=results),self.assertRaises(ValueError):updater.check_git(self.root)
  with patch.object(updater,'git',side_effect=['','main','https://github.com/Zyvelia/test.git']):self.assertTrue(updater.check_git(self.root))
 def test_auto_update_is_opt_in(self):
  with patch.dict(updater.os.environ,{'AUTO_UPDATE':'false'}),patch.object(updater,'update') as update:updater.automatic_update(self.root);update.assert_not_called()
  with patch.dict(updater.os.environ,{'AUTO_UPDATE':'true'}),patch.object(updater,'update') as update:updater.automatic_update(self.root);update.assert_called_once_with(self.root)
 def test_launcher_has_actionable_update_errors(self):
  from vivi import supervisor
  with patch.object(supervisor,'ROOT',self.root),patch('vivi.updater.automatic_update',side_effect=ValueError('network unavailable')),patch.object(supervisor,'run') as run,patch('builtins.print'):
   with self.assertRaises(SystemExit) as result:supervisor.main()
   self.assertEqual(result.exception.code,2);run.assert_not_called()

 def test_git_update_fetches_and_fast_forwards_pinned_commit(self):
  archive=self.archive();old='b'*40
  def fetch(url,target):target.write_bytes(archive.read_bytes())
  with patch.object(updater,'check_git',return_value=True),patch.object(updater,'latest_commit',return_value=SHA),patch.object(updater,'download',side_effect=fetch),patch.object(updater,'git',side_effect=[old,'','',SHA,'']) as git,patch.object(updater,'install_dependencies') as deps,patch.object(updater,'apply_zip') as apply:
   updater.update(self.root);apply.assert_not_called();deps.assert_called_once()
   self.assertEqual(git.call_args.args,(self.root,'merge','--ff-only',SHA))
 def test_failed_download_leaves_installed_source_untouched(self):
  (self.root/'vivi').mkdir();(self.root/'vivi/bot.py').write_text('original')
  with patch.object(updater,'latest_commit',side_effect=OSError('offline')),self.assertRaises(OSError):updater.update(self.root)
  self.assertEqual((self.root/'vivi/bot.py').read_text(),'original');self.assertFalse((self.root/'data/update-pending.json').exists())
 def test_bootstrap_requires_existing_venv_installation(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('vivi_bootstrap_script',Path(__file__).resolve().parents[1]/'scripts/bootstrap_update.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with patch.object(module.Path,'cwd',return_value=self.root),self.assertRaises(ValueError):module.main()
 def test_bootstrap_loads_pinned_updater_in_temporary_package(self):
  import importlib.util,sys
  spec=importlib.util.spec_from_file_location('vivi_bootstrap_script',Path(__file__).resolve().parents[1]/'scripts/bootstrap_update.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  (self.root/'vivi').mkdir();(self.root/'vivi/bot.py').write_text('old bot')
  def read(url):
   if url.endswith('/commits/main'):return json.dumps(dict(sha=SHA)).encode()
   self.assertIn('/'+SHA+'/',url)
   return b'from contextlib import contextmanager\n@contextmanager\ndef host_lock(root):\n yield\n' if url.endswith('/host_lock.py') else b'def update(root):\n (root/"bootstrap-result").write_text("updated")\n'
  saved_path=list(sys.path)
  try:
   with patch.object(module.Path,'cwd',return_value=self.root),patch.object(module.sys,'prefix',str(self.root/'.venv')),patch.object(module,'read',side_effect=read):module.main()
   self.assertEqual((self.root/'bootstrap-result').read_text(),'updated');self.assertEqual((self.root/'vivi/bot.py').read_text(),'old bot')
  finally:
   sys.path[:]=saved_path
   for key in list(sys.modules):
    if key=='vivi_bootstrap' or key.startswith('vivi_bootstrap.'):sys.modules.pop(key)

 def test_unchanged_zip_installation_does_not_redownload_archive(self):
  files=updater.extract(self.archive(),self.stage);updater.apply_zip(self.root,self.stage,files,SHA)
  with patch.object(updater,'latest_commit',return_value=SHA),patch.object(updater,'download') as download:
   updater.update(self.root);download.assert_not_called()
