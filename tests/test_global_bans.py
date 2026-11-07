import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock,patch
import discord
from vivi.server.global_bans import GlobalBans,DEFAULT_OPERATOR_ID,is_operator,user_id
from vivi.server.global_ban_menu import GlobalMenu,ConfirmGlobal
from vivi.core.storage import Store

TARGET=123456789012345678
OP=DEFAULT_OPERATOR_ID

def missing():return discord.NotFound(NS(status=404,reason='Not Found'),{'code':10026,'message':'Unknown Ban'})
class Guild:
    def __init__(self,ident):
        self.id=ident;self.name=f'Server {ident}';self.owner_id=1000+ident;self.me=NS(guild_permissions=discord.Permissions(ban_members=True,view_audit_log=True),top_role=10)
        self.current=None;self.events=[];self.member=None;self.fetch_ban=AsyncMock(side_effect=self.fetch);self.ban=AsyncMock(side_effect=self.apply);self.unban=AsyncMock(side_effect=self.clear)
    def get_member(self,target):return self.member
    async def fetch(self,target):
        if self.current is None:raise missing()
        return self.current
    async def apply(self,target,reason,delete_message_seconds):
        self.current=NS(reason=reason);self.events.insert(0,NS(target=target,user=NS(id=99),reason=reason))
    async def clear(self,target,reason):self.current=None
    def audit_logs(self,**kwargs):
        async def stream():
            for event in self.events:yield event
        return stream()

class GlobalBanRules(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env=patch.dict(os.environ,{'GLOBAL_BAN_OPERATOR_ID':str(OP)});self.env.start()
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite3';self.store=Store(self.path);self.guilds=[Guild(1),Guild(2)]
        self.bot=NS(user=NS(id=99),guilds=self.guilds,get_guild=lambda ident:next((g for g in self.guilds if g.id==ident),None))
        self.service=NS(bot=self.bot,store=self.store,case=AsyncMock(),productivity=NS(error=MagicMock()))
        self.network=GlobalBans(self.service)
    async def asyncTearDown(self):await self.network.close();self.store.close();self.tmp.cleanup();self.env.stop()
    def optin(self,index=0):
        guild=self.guilds[index];self.network.set_participation(guild,guild.owner_id,True,confirmed=True)
    def add(self,scope=None):return self.network.add(TARGET,'Repeated documented scam messages','Case 123 and evidence reference',OP,[g.id for g in self.guilds] if scope is None else scope)
    async def test_exact_operator_id_only_not_names_or_administrator_roles(self):
        self.assertTrue(is_operator(NS(id=OP)))
        self.assertFalse(is_operator(NS(id=OP+1,name='ZyVelia',guild_permissions=discord.Permissions.all())))
        with self.assertRaises(PermissionError):self.network.add(TARGET,'A sufficient reason','Evidence',OP+1,[1])
        self.assertIsNone(self.network.entry(TARGET))
    async def test_owner_consent_requires_explicit_confirmation(self):
        with self.assertRaises(ValueError):self.network.set_participation(self.guilds[0],self.guilds[0].owner_id,True)
        self.assertFalse(self.network.participating(self.guilds[0]))
    async def test_invalid_ids_and_protected_accounts_fail_closed(self):
        for text in ['ZyVelia','-1','0','９７３','999999999999999999999999']:
            with self.assertRaises(ValueError):user_id(text)
        for target in [OP,99]:
            with self.assertRaises(ValueError):self.network.add(target,'A sufficient reason','Evidence',OP,[1])
        with patch.dict(os.environ,{'GLOBAL_BAN_OPERATOR_ID':'invalid'}):self.assertFalse(is_operator(NS(id=OP)))
    async def test_server_owner_must_explicitly_opt_in(self):
        guild=self.guilds[0]
        with self.assertRaises(PermissionError):self.network.set_participation(guild,55,True,administrator=True)
        self.assertFalse(self.network.participating(guild));self.store.set_option(1,'feature:global_bans',True);self.assertFalse(self.network.participating(guild))
        self.optin();self.assertTrue(self.network.participating(guild));guild.owner_id+=1;self.assertFalse(self.network.participating(guild))
    async def test_consent_is_bound_to_operator_and_bot_identity(self):
        self.optin()
        with patch.dict(os.environ,{'GLOBAL_BAN_OPERATOR_ID':str(OP+1)}):self.assertFalse(self.network.participating(self.guilds[0]))
        self.bot.user.id=100;self.assertFalse(self.network.participating(self.guilds[0]))
    async def test_only_participating_servers_receive_bans_without_message_deletion(self):
        self.optin();self.assertEqual(self.add(),1);await self.network.tick()
        self.guilds[0].ban.assert_awaited_once();self.guilds[1].ban.assert_not_awaited()
        self.assertEqual(self.guilds[0].ban.call_args.kwargs['delete_message_seconds'],0)
        self.assertEqual(self.store.records(1,'global_ban_job')[0]['data']['status'],'success')
    async def test_later_owner_optin_queues_existing_entries(self):
        self.assertEqual(self.add(),0);self.optin(1);await self.network.tick();self.guilds[1].ban.assert_awaited_once();self.guilds[0].ban.assert_not_awaited()
    async def test_disabling_and_config_restore_cannot_recreate_consent(self):
        self.optin();backup=self.store.export_config(1)
        self.network.set_participation(self.guilds[0],22,False,administrator=True);self.assertFalse(self.network.participating(self.guilds[0]))
        self.store.restore_config(1,backup);self.assertFalse(self.network.participating(self.guilds[0]));self.assertFalse(self.store.option(1,'feature:global_bans'))
    async def test_optout_before_worker_cancels_pending_bans(self):
        self.optin();self.add();self.network.set_participation(self.guilds[0],self.guilds[0].owner_id,False);await self.network.tick()
        self.guilds[0].ban.assert_not_awaited();self.assertEqual(self.store.records(1,'global_ban_job')[0]['data']['status'],'skipped')
    async def test_missing_permissions_and_hierarchy_report_failures(self):
        self.optin();self.add();self.guilds[0].me.guild_permissions.ban_members=False;await self.network.tick()
        self.assertEqual(self.store.records(1,'global_ban_job')[0]['data']['status'],'failed');self.guilds[0].ban.assert_not_awaited()
        self.guilds[0].me.guild_permissions.ban_members=True;self.guilds[0].member=NS(top_role=11);self.network.queue(self.guilds[0],self.network.entry(TARGET)['data'],'ban',OP,force=True);await self.network.tick()
        self.assertIn('role',self.store.records(1,'global_ban_job')[0]['data']['result'])
    async def test_independent_existing_ban_is_never_claimed_or_unbanned(self):
        self.optin();self.guilds[0].current=NS(reason='Independent server ban');self.add();await self.network.tick();self.guilds[0].ban.assert_not_awaited()
        self.assertEqual(self.store.records(1,'global_ban_job')[0]['data']['status'],'preexisting')
        self.network.remove(TARGET,'Appeal accepted after review',True,OP);await self.network.tick();self.guilds[0].unban.assert_not_awaited()
    async def test_verified_system_bans_can_be_undone(self):
        self.optin();self.add();await self.network.tick();self.network.remove(TARGET,'Appeal accepted after review',True,OP);await self.network.tick()
        self.guilds[0].unban.assert_awaited_once();self.assertFalse(self.network.active(TARGET));self.assertFalse(self.store.record(f'globalledger:1:{TARGET}')['data']['issued'])
    async def test_list_removal_does_not_implicitly_unban(self):
        self.optin();self.add();await self.network.tick();self.network.remove(TARGET,'Appeal accepted after review',False,OP);await self.network.tick()
        self.guilds[0].unban.assert_not_awaited();self.assertIsNotNone(self.guilds[0].current)
    async def test_withdrawn_consent_also_preserves_existing_bans_on_global_removal(self):
        self.optin();self.add();await self.network.tick();self.network.set_participation(self.guilds[0],self.guilds[0].owner_id,False)
        self.network.remove(TARGET,'Operator accepted the appeal',True,OP);await self.network.tick();self.guilds[0].unban.assert_not_awaited()
        row=next(r for r in self.store.records(1,'global_ban_job') if r['data']['action']=='unban');self.assertEqual(row['data']['status'],'skipped')
    async def test_modified_or_unverifiable_server_ban_is_preserved(self):
        self.optin();self.add();await self.network.tick();guild=self.guilds[0]
        guild.events.insert(0,NS(target=NS(id=TARGET),user=NS(id=55),reason=guild.current.reason))
        self.network.remove(TARGET,'Appeal accepted after review',True,OP);await self.network.tick();guild.unban.assert_not_awaited()
        guild.events=guild.events[1:];guild.me.guild_permissions.view_audit_log=False
        self.network.queue(guild,self.network.entry(TARGET)['data'],'unban',OP,force=True);await self.network.tick();guild.unban.assert_not_awaited()
    async def test_pending_jobs_and_consent_survive_restart(self):
        self.optin();self.add();self.store.close();self.store=Store(self.path);self.service.store=self.store;self.network=GlobalBans(self.service)
        await self.network.tick();self.guilds[0].ban.assert_awaited_once()
    async def test_transient_discord_failure_is_retried(self):
        self.optin();self.add();guild=self.guilds[0];guild.ban.side_effect=discord.HTTPException(NS(status=503,reason='Unavailable'),'Unavailable')
        await self.network.tick();job=self.store.records(1,'global_ban_job')[0];self.assertEqual(job['data']['status'],'pending');self.assertGreater(job['data']['next'],0)
        guild.ban.side_effect=guild.apply;job['data']['next']=0;self.store.put_record(1,'global_ban_job',job['data'],job['id']);await self.network.tick()
        self.assertEqual(self.store.record(job['id'])['data']['status'],'success')
    async def test_inflight_ban_is_recorded_then_verified_undo_can_remove_it(self):
        self.optin();self.add();guild=self.guilds[0]
        async def race(target,**kwargs):
            await guild.apply(target,**kwargs);self.network.remove(TARGET,'Operator cancelled the entry',True,OP)
        guild.ban.side_effect=race;await self.network.tick();await self.network.tick();guild.unban.assert_awaited_once()
    async def test_join_enforcement_precedes_welcome_and_roles(self):
        from vivi.server.community import Community
        self.optin();self.add();self.service.global_bans=self.network;self.service.operations=NS(on_join=AsyncMock())
        await Community.on_join(self.service,NS(id=TARGET,guild=self.guilds[0]));self.guilds[0].ban.assert_awaited_once();self.service.operations.on_join.assert_not_awaited()
    async def test_join_api_failure_is_saved_as_a_failed_server_result(self):
        self.optin();self.add();guild=self.guilds[0];guild.ban.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'Missing Permissions')
        self.assertTrue(await self.network.on_join(NS(id=TARGET,guild=guild)))
        job=self.store.records(1,'global_ban_job')[0];self.assertEqual(job['data']['status'],'failed');self.assertIn('403',job['data']['result'])
    async def test_ui_confirmation_is_owner_bound_single_use_and_private(self):
        i=NS(user=NS(id=OP),guild_id=1,response=NS(is_done=lambda:False,send_message=AsyncMock(),edit_message=AsyncMock()))
        self.optin();view=ConfirmGlobal(self.network,i,TARGET,'Documented scam activity','Evidence case 123');self.assertFalse(self.network.active(TARGET))
        i.user.id=OP+1;await view.children[0].callback(i);self.assertFalse(self.network.active(TARGET))
        i.user.id=OP;await view.children[0].callback(i);self.assertTrue(self.network.active(TARGET));self.assertTrue(view.used);view.stop()
        menu=GlobalMenu(self.network,i);i.user.id=OP+1;self.assertFalse(await menu.interaction_check(i));menu.stop()

class GlobalCommandBinding(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from vivi.bot import ViviBot
        self.env=patch.dict(os.environ,{'GLOBAL_BAN_OPERATOR_ID':str(OP)});self.env.start()
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.i=NS(user=NS(id=OP+1,guild_permissions=discord.Permissions.all()),guild_id=None,guild=None,response=NS(is_done=lambda:False,send_message=AsyncMock()),original_response=AsyncMock(return_value=NS(edit=AsyncMock())))
    async def asyncTearDown(self):await self.bot.close();self.store.close();self.tmp.cleanup();self.env.stop()
    async def test_admin_roles_do_not_grant_global_command_access(self):
        await self.bot.tree.get_command('globalban').callback(self.i)
        self.assertIn('restricted',self.i.response.send_message.call_args.args[0]);self.assertNotIn('view',self.i.response.send_message.call_args.kwargs)
    async def test_exact_account_can_open_private_controls_without_admin_roles(self):
        self.i.user.id=OP;self.i.user.guild_permissions=discord.Permissions.none()
        await self.bot.tree.get_command('globalban').callback(self.i)
        options=self.i.response.send_message.call_args.kwargs;self.assertTrue(options['ephemeral']);self.assertIsInstance(options['view'],GlobalMenu);options['view'].stop()
