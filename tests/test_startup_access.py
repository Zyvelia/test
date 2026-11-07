"""Offline startup diagnostics: permanent access failures must not cause restart loops."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock,patch
import discord
from vivi.bot import ViviBot,StartupConfigurationError,main
from vivi.storage import Store
from vivi import supervisor

class CommandRegistrationTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'vivi.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__();self.bot.tree.sync=AsyncMock(return_value=[])
 async def asyncTearDown(self):await self.bot.close();self.store.close();self.tmp.cleanup()
 async def test_missing_access_has_server_scope_recovery_and_no_global_fallback(self):
  error=discord.Forbidden(NS(status=403,reason='Forbidden'),dict(code=50001,message='Missing Access'));self.bot.tree.sync.side_effect=error
  with patch.dict(os.environ,{'DEV_GUILD_ID':'1437198741202272329'}):
   with self.assertRaises(StartupConfigurationError) as caught:await self.bot.sync_application_commands()
  message=str(caught.exception)
  for text in ['1437198741202272329','50001','applications.commands','Server Install','DEV_GUILD_ID= blank']:self.assertIn(text,message)
  self.assertEqual(self.bot.tree.sync.await_count,1);self.assertEqual(self.bot.tree.sync.call_args.kwargs['guild'].id,1437198741202272329)
 async def test_unknown_server_is_a_configuration_error(self):
  self.bot.tree.sync.side_effect=discord.NotFound(NS(status=404,reason='Not Found'),dict(code=10004,message='Unknown Guild'))
  with patch.dict(os.environ,{'DEV_GUILD_ID':'123'}):
   with self.assertRaises(StartupConfigurationError):await self.bot.sync_application_commands()
 async def test_blank_server_uses_global_sync(self):
  with patch.dict(os.environ,{'DEV_GUILD_ID':''}):await self.bot.sync_application_commands()
  self.bot.tree.sync.assert_awaited_once_with()
 async def test_global_access_failure_is_actionable(self):
  self.bot.tree.sync.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),dict(code=50001,message='Missing Access'))
  with patch.dict(os.environ,{'DEV_GUILD_ID':''}):
   with self.assertRaises(StartupConfigurationError) as caught:await self.bot.sync_application_commands()
  self.assertIn('global slash commands',str(caught.exception));self.assertIn('DISCORD_TOKEN',str(caught.exception));self.bot.tree.sync.assert_awaited_once_with()
 async def test_invalid_server_does_not_make_api_request(self):
  for value in ['channel-name','-1','0',str(2**64)]:
   with patch.dict(os.environ,{'DEV_GUILD_ID':value}):
    with self.assertRaises(StartupConfigurationError):await self.bot.sync_application_commands()
  self.bot.tree.sync.assert_not_awaited()
 async def test_transient_http_failure_keeps_normal_retry_path(self):
  error=discord.HTTPException(NS(status=503,reason='Unavailable'),dict(code=0,message='Unavailable'));self.bot.tree.sync.side_effect=error
  with patch.dict(os.environ,{'DEV_GUILD_ID':'123'}):
   with self.assertRaises(discord.HTTPException):await self.bot.sync_application_commands()
 async def test_failed_registration_does_not_start_background_services(self):
  self.bot.sync_application_commands=AsyncMock(side_effect=StartupConfigurationError('Missing server access'));self.bot.community.start=AsyncMock()
  with self.assertRaises(StartupConfigurationError):await self.bot.setup_hook()
  self.bot.community.start.assert_not_awaited()

class LauncherTests(unittest.TestCase):
 def test_configuration_error_exits_two_and_releases_store_and_lock(self):
  bot=MagicMock();bot.run.side_effect=StartupConfigurationError('Actionable configuration failure');store=MagicMock();lock=MagicMock()
  with patch.dict(os.environ,{'DISCORD_TOKEN':'example-not-a-real-token','DEV_GUILD_ID':''}),patch('vivi.bot.load_dotenv'),patch('vivi.bot.logging.basicConfig'),patch('vivi.bot.Store',return_value=store),patch('vivi.runtime.SingleInstance',return_value=lock),patch('vivi.bot.ViviBot',return_value=bot),self.assertLogs('vivi',level='ERROR') as logs:
   with self.assertRaises(SystemExit) as caught:main()
  self.assertEqual(caught.exception.code,2);self.assertTrue(any('Actionable configuration failure' in line for line in logs.output));self.assertFalse(any('example-not-a-real-token' in line for line in logs.output));store.close.assert_called_once();lock.close.assert_called_once()
 def test_supervisor_does_not_restart_a_configuration_exit(self):
  with tempfile.TemporaryDirectory() as temporary:
   process=MagicMock();process.stdout=iter(['Actionable setup error\n']);process.wait.return_value=2
   with patch.object(supervisor,'ROOT',Path(temporary)),patch.object(supervisor.signal,'signal'),patch.object(supervisor.subprocess,'Popen',return_value=process) as spawn,patch.object(supervisor.time,'sleep') as sleep,patch('builtins.print'):
    supervisor.main()
   self.assertEqual(spawn.call_count,1);sleep.assert_not_called()
