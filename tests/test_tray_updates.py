import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from types import SimpleNamespace as NS
from vivi.tray import TrayController

class TrayUpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  (self.root/'.venv/Scripts').mkdir(parents=True);(self.root/'.venv/Scripts/python.exe').touch();(self.root/'vivi').mkdir();(self.root/'vivi/updater.py').touch()
  self.controller=TrayController(self.root)
 def prepare(self,running=False):
  if running:self.controller.process=Mock(pid=123,poll=Mock(return_value=None))
  self.thread_patch=patch('vivi.tray.threading.Thread');self.thread=self.thread_patch.start();self.addCleanup(self.thread_patch.stop)
  self.done=Mock();self.controller.begin_update(self.done)
 def worker(self):self.controller._update_worker(self.done)
 def test_claims_update_before_thread_start_and_blocks_conflicting_actions(self):
  self.prepare();self.assertTrue(self.controller.updating);self.thread.return_value.start.assert_called_once()
  for action in [self.controller.begin_update,self.controller.start,self.controller.stop]:
   with self.assertRaises(ValueError):action()
 def test_update_stops_owned_bot_runs_local_updater_then_restarts(self):
  self.prepare(True);events=[]
  def stop():events.append('stop');self.controller.process=None
  def run(*args,**kwargs):events.append('update');self.assertEqual(args[0],[str(self.root/'.venv/Scripts/python.exe'),'-u','-m','vivi.updater']);self.assertEqual(kwargs['cwd'],self.root);self.assertEqual(kwargs['stdout'].name,str(self.root/'data/logs/update.log'));return NS(returncode=0)
  with patch.object(self.controller,'_stop',side_effect=stop),patch('vivi.tray.subprocess.run',side_effect=run),patch.object(self.controller,'_start',side_effect=lambda **kwargs:events.append(('start',kwargs)) or True):self.worker()
  self.assertEqual(events,['stop','update',('start',{'after_update':True})]);self.assertFalse(self.controller.updating);self.done.assert_called_once_with(True,'Update complete. Vivi is starting.')
 def test_stopped_bot_remains_stopped_after_success(self):
  self.prepare()
  with patch('vivi.tray.subprocess.run',return_value=NS(returncode=0)),patch.object(self.controller,'_start') as start:self.worker();start.assert_not_called()
  self.assertEqual(self.done.call_args.args,(True,'Update complete. Vivi remains stopped.'))
 def test_failed_update_never_restarts_and_logs_result(self):
  self.prepare(True)
  with patch.object(self.controller,'_stop',side_effect=lambda:setattr(self.controller,'process',None)),patch('vivi.tray.subprocess.run',return_value=NS(returncode=1)),patch.object(self.controller,'_start') as start:self.worker();start.assert_not_called()
  self.assertFalse(self.done.call_args.args[0]);self.assertIn('remains stopped',self.controller.last_update);self.assertIn('Update failed',(self.root/'data/logs/update.log').read_text());self.assertFalse(self.controller.updating)
 def test_foreign_process_is_never_stopped_or_updated(self):
  with patch.object(self.controller,'running',return_value=True),patch('vivi.tray.threading.Thread') as thread,patch('vivi.tray.subprocess.run') as run:
   with self.assertRaisesRegex(ValueError,'outside this tray'):self.controller.begin_update()
   thread.assert_not_called();run.assert_not_called();self.assertFalse(self.controller.updating)
 def test_exception_clears_busy_flag_and_reports_failure(self):
  self.prepare()
  with patch('vivi.tray.subprocess.run',side_effect=OSError('spawn failed')):self.worker()
  self.assertFalse(self.controller.updating);self.assertEqual(self.done.call_args.args,(False,'spawn failed'))
 def test_update_rechecks_for_external_process_before_spawning_updater(self):
  self.prepare()
  with patch.object(self.controller,'running',return_value=True),patch('vivi.tray.subprocess.run') as run:self.worker();run.assert_not_called()
  self.assertFalse(self.done.call_args.args[0]);self.assertIn('Another Vivi',self.done.call_args.args[1])
 def test_restart_skips_second_automatic_update_without_changing_environment(self):
  import os
  with patch.dict(os.environ,{'AUTO_UPDATE':'true'}),patch('vivi.tray.subprocess.Popen') as spawn:
   self.controller._start(after_update=True);self.assertEqual(spawn.call_args.kwargs['env']['AUTO_UPDATE'],'false');self.assertEqual(os.environ['AUTO_UPDATE'],'true')
 def test_worker_creation_failure_releases_busy_flag(self):
  with patch('vivi.tray.threading.Thread') as thread:
   thread.return_value.start.side_effect=RuntimeError('thread unavailable')
   with self.assertRaises(RuntimeError):self.controller.begin_update()
   self.assertFalse(self.controller.updating)
