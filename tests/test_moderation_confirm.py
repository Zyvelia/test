import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
import discord
from vivi.bot import ViviBot,register_commands
from vivi.core.storage import Store
from vivi.server.moderation import ModerationConfirm

class ModerationConfirmationTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.bot=ViviBot(self.store);await self.bot.__aenter__();register_commands(self.bot)
  self.actor=NS(id=10,top_role=5,guild_permissions=discord.Permissions(kick_members=True,ban_members=True))
  self.bot_member=NS(id=99,top_role=10,guild_permissions=discord.Permissions(kick_members=True,ban_members=True))
  self.target=NS(id=20,top_role=1,kick=AsyncMock(),ban=AsyncMock())
  self.members={10:self.actor,99:self.bot_member,20:self.target}
  self.guild=NS(id=1,owner_id=100,me=self.bot_member,fetch_member=AsyncMock(side_effect=lambda ident:self.members[ident]))
  self.views=[]
 async def asyncTearDown(self):
  for view in self.views:view.stop()
  await self.bot.close();self.store.close();self.tmp.cleanup()
 def interaction(self,actor=None,guild=None):
  state={'deferred':False}
  async def defer(*args,**kwargs):state['deferred']=True
  return NS(user=actor or self.actor,guild=self.guild,guild_id=guild or 1,response=NS(defer=AsyncMock(side_effect=defer),is_done=lambda:state['deferred'],send_message=AsyncMock(),edit_message=AsyncMock()),followup=NS(send=AsyncMock()),original_response=AsyncMock(return_value=NS(edit=AsyncMock())),edit_original_response=AsyncMock())
 async def prompt(self,action='kick'):
  i=self.interaction();await self.bot.tree.get_command(action).callback(i,self.target,'Spam links')
  view=i.response.send_message.call_args.kwargs['view'];self.views.append(view);return i,view
 async def test_actions_wait_for_confirmation_then_log_one_real_case(self):
  for action in ['kick','ban']:
   i,view=await self.prompt(action);self.assertIsInstance(view,ModerationConfirm);self.assertTrue(i.response.send_message.call_args.kwargs['ephemeral']);getattr(self.target,action).assert_not_awaited()
   before=len(self.store.search_cases(1));await view.confirm(i);getattr(self.target,action).assert_awaited_once();self.assertEqual(len(self.store.search_cases(1)),before+1)
   row=self.store.search_cases(1)[0];self.assertEqual(row['action'],action);self.assertEqual(row['moderator'],10);self.assertIn('Case #',i.edit_original_response.call_args.kwargs['content'])
   await view.confirm(i);getattr(self.target,action).assert_awaited_once()
  self.assertEqual(self.target.ban.call_args.kwargs['delete_message_seconds'],0)
 async def test_another_account_or_server_cannot_confirm_or_cancel(self):
  i,view=await self.prompt()
  for other in [self.interaction(NS(id=500)),self.interaction(guild=2)]:await view.confirm(other);await view.cancel(other)
  self.target.kick.assert_not_awaited();self.assertFalse(view.used);self.assertEqual(self.store.search_cases(1),[])
 async def test_cancel_and_expiry_never_act_or_log(self):
  i,view=await self.prompt();await view.cancel(i);await view.confirm(i)
  i,view=await self.prompt();await view.on_timeout();await view.confirm(i)
  self.target.kick.assert_not_awaited();self.assertEqual(self.store.search_cases(1),[]);self.assertTrue(all(child.disabled for child in view.children))
 async def test_changed_permissions_and_hierarchy_are_checked_fresh(self):
  for member,attribute,value in [(self.actor,'guild_permissions',discord.Permissions.none()),(self.bot_member,'guild_permissions',discord.Permissions.none()),(self.target,'top_role',50),(self.actor,'top_role',0)]:
   i,view=await self.prompt();original=getattr(member,attribute);setattr(member,attribute,value)
   await view.confirm(i);setattr(member,attribute,original)
   self.target.kick.assert_not_awaited();self.assertEqual(self.store.search_cases(1),[])
 async def test_member_leaving_before_confirmation_does_not_ban(self):
  i,view=await self.prompt('ban');self.guild.fetch_member.side_effect=discord.NotFound(NS(status=404,reason='Not Found'),'Gone')
  await view.confirm(i);self.target.ban.assert_not_awaited();self.assertIn('no longer',i.edit_original_response.call_args.kwargs['content']);self.assertEqual(self.store.search_cases(1),[])
 async def test_discord_failure_does_not_create_a_success_case(self):
  i,view=await self.prompt();self.target.kick.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'Denied')
  with self.assertLogs('vivi',level='ERROR'):await view.confirm(i)
  self.assertEqual(self.store.search_cases(1),[]);self.assertIn('Nothing was logged',i.edit_original_response.call_args.kwargs['content'])
 async def test_disabling_moderation_cancels_pending_confirmation(self):
  i,view=await self.prompt();self.store.set_option(1,'feature:moderation',False)
  await view.confirm(i);self.target.kick.assert_not_awaited();self.assertEqual(self.store.search_cases(1),[])
 async def test_concurrent_confirmations_execute_only_once(self):
  i,view=await self.prompt('ban');await asyncio.gather(view.confirm(i),view.confirm(i));self.target.ban.assert_awaited_once();self.assertEqual(len(self.store.search_cases(1)),1)
 async def test_logging_failure_does_not_repeat_successful_action(self):
  i,view=await self.prompt();self.bot.community.case=AsyncMock(side_effect=RuntimeError('Case unavailable'))
  with self.assertLogs('vivi',level='ERROR'):await view.confirm(i)
  await view.confirm(i);self.target.kick.assert_awaited_once();self.assertIn('do not repeat',i.edit_original_response.call_args.kwargs['content'])
