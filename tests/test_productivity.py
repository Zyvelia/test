import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock,patch

import discord
from aiohttp import web
from PIL import Image
from vivi.bot import ViviBot,register_commands,reply
from vivi.server.community import register_extra
from vivi.server.operations import register_operations
from vivi.server.music import register_voice
from vivi.server.productivity import register_productivity,validate_aliases,atomic_private
from vivi.core.storage import Store
from vivi.site.dashboard import Dashboard
from vivi.core.i18n import tr,localize_message,localize_html,UI_LANGUAGE
from vivi.healthcheck import healthy
from vivi.tray import TrayController
from vivi.core.runtime import SingleInstance

class PureTests(unittest.TestCase):
    def test_localization_preserves_placeholders_and_falls_back(self):
        self.assertEqual(tr('es','Added {name}.',name='Gaming'),'Se añadió Gaming.')
        self.assertEqual(localize_message('fr','Volume: 50%.'),'Volume : 50 %.')
        self.assertEqual(localize_message('es','Unique custom server message'),'Unique custom server message')
        self.assertEqual(tr('de','Remove'),'Remove')

    def test_html_localization_leaves_user_content_alone(self):
        result=localize_html('es','<p>Remove</p><button name="test">Remove</button><summary>Health dashboard</summary>')
        self.assertIn('<p>Remove</p>',result)
        self.assertIn('>Eliminar</button>',result)
        self.assertIn('Estado de Vivi',result)

    def test_aliases_cannot_run_moderation_or_code_or_override_commands(self):
        validate_aliases({'rules':dict(target='faq',argument='rules')})
        for value in [{'ban':dict(target='ping',argument='')},{'rules':dict(target='ban',argument='123')},
                      {'rules':dict(target='help',argument='extra')},{'bad name':dict(target='help',argument='')}]:
            with self.assertRaises(ValueError): validate_aliases(value)

    def test_atomic_backup_is_private_and_failure_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'backup.json'
            atomic_private(path,b'{"ok":true}')
            self.assertEqual(path.read_bytes(),b'{"ok":true}')
            if os.name!='nt': self.assertEqual(path.stat().st_mode&0o777,0o600)
            with patch('vivi.server.productivity.os.replace',side_effect=OSError('test')):
                with self.assertRaises(OSError): atomic_private(path,b'changed')
            self.assertEqual(path.read_bytes(),b'{"ok":true}')
            self.assertEqual(len(list(Path(tmp).glob('*.tmp'))),0)

    def test_container_health_requires_fresh_connected_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'heartbeat.json'
            for data,expected in [(dict(at=950,ready=True),True),(dict(at=500,ready=True),False),
                                  (dict(at=1050,ready=True),False),(dict(at=950,ready=False),False)]:
                path.write_text(json.dumps(data));self.assertEqual(healthy(path,1000),expected)
            path.write_text('invalid');self.assertFalse(healthy(path,1000))

    def test_tray_does_not_start_a_second_instance_or_stop_foreign_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lock=SingleInstance(root/'data/vivi.lock')
            controller=TrayController(root)
            try:
                with patch('vivi.tray.subprocess.Popen') as spawn:
                    self.assertFalse(controller.start());spawn.assert_not_called()
                with patch('vivi.tray.subprocess.run') as terminate:
                    self.assertFalse(controller.stop());terminate.assert_not_called()
            finally: lock.close()

    def test_tray_starts_only_local_venv_and_stops_its_own_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'.venv/Scripts').mkdir(parents=True);(root/'.venv/Scripts/python.exe').touch()
            process=MagicMock();process.poll.return_value=None
            controller=TrayController(root)
            with patch('vivi.tray.subprocess.Popen',return_value=process) as spawn:
                self.assertTrue(controller.start())
                self.assertEqual(spawn.call_args.args[0][-2:],['-m','vivi.supervisor'])
                self.assertFalse(controller.start())
            with patch('vivi.tray.os.name','nt'),patch('vivi.tray.subprocess.run') as kill:
                controller.stop();self.assertEqual(kill.call_args.args[0][-3:],[str(process.pid),'/T','/F'])


class HistoryTests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3')
    def tearDown(self): self.store.close();self.tmp.cleanup()
    def test_configuration_actor_scope_and_internal_state_exclusion(self):
        token=self.store.actor.set('discord:7')
        self.store.set_option(1,'language','es');self.store.actor.reset(token)
        self.store.set_option(1,'internal_backup_last',123)
        self.store.save_profile(1,99,self.store.profile(1,99))
        rows=self.store.history(1)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['actor'],'discord:7')
        revision=self.store.revision(1,rows[0]['id'])
        self.assertEqual(revision['after']['options']['language'],'es')
        self.assertIsNone(self.store.revision(2,rows[0]['id']))

    def test_history_retains_latest_100_and_rollback_is_a_new_revision(self):
        for index in range(105): self.store.set_option(1,'spam_limit',index%100+1)
        self.assertEqual(len(self.store.history(1)),100)
        revision=self.store.revision(1,self.store.history(1)[-1]['id'])
        self.store.restore_config(1,revision['after'])
        self.assertEqual(self.store.option(1,'spam_limit'),revision['after']['options']['spam_limit'])
        self.assertEqual(self.store.history(1)[0]['action'],'restore')

    def test_notification_poll_updates_do_not_generate_config_changes(self):
        data=dict(provider='twitch',source='someone',channel=3,initialized=False)
        self.store.put_record(1,'notification',data,'watch')
        count=len(self.store.history(1))
        self.store.put_record(1,'notification',dict(data,last='new',initialized=True),'watch')
        self.assertEqual(len(self.store.history(1)),count)
        self.store.delete_record('watch');self.assertEqual(len(self.store.history(1)),count+1)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'db.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot._connection.user=NS(id=99)
        register_commands(self.bot);register_extra(self.bot);register_operations(self.bot);register_voice(self.bot);register_productivity(self.bot)
        self.bot.tree.sync=AsyncMock(return_value=[])
        self.service=self.bot.community;self.p=self.service.productivity
        self.guild=NS(id=1,name='Our Server',me=NS(id=99,display_name='Vivi'),get_member=lambda ident:None,
                      text_channels=[],categories=[],voice_channels=[],roles=[],voice_client=None)
        self.bot.get_guild=lambda ident:self.guild if ident==1 else None
        self.user=NS(id=7,display_name='Alex',guild_permissions=discord.Permissions.all())
    async def asyncTearDown(self): await self.bot.close();self.store.close();self.tmp.cleanup()
    def i(self):
        return NS(client=self.bot,guild_id=1,guild=self.guild,user=self.user,channel_id=20,permissions=discord.Permissions.all(),
            response=NS(is_done=lambda:True,defer=AsyncMock(),send_message=AsyncMock()),followup=NS(send=AsyncMock()))
    def command(self,group,name):return self.bot.tree.get_command(group).get_command(name).callback
    def enable(self,name):self.store.set_option(1,'feature:'+name,True)
    def dashboard(self):
        d=Dashboard(self.service);d.sessions['sid']=dict(token='opaque',csrf='ok',expires=time.time()+100,user_id=7)
        d.api_guilds=AsyncMock(return_value={'1':{'id':'1','permissions':'8'}});return d
    def form(self,**values):return NS(cookies={'vivi_session':'sid'},post=AsyncMock(return_value=dict(csrf='ok',guild='1',**values)))

    async def test_afk_set_mention_rate_limit_and_return(self):
        self.enable('afk');await self.command('tools','afk')(self.i(),'Taking a break @everyone')
        record=self.store.record('afk:1:7');self.assertEqual(record['data']['user'],7)
        other=NS(id=8,display_name='Other')
        message=NS(guild=self.guild,author=other,mentions=[self.user],channel=NS(id=20),reply=AsyncMock())
        await self.p.on_message(message);await self.p.on_message(message)
        message.reply.assert_awaited_once()
        mentions=message.reply.call_args.kwargs['allowed_mentions'];self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.users)
        message.author=self.user;message.mentions=[]
        await self.p.on_message(message)
        self.assertIsNone(self.store.record('afk:1:7'))

    async def test_afk_other_server_is_not_disclosed(self):
        self.enable('afk');self.store.put_record(2,'afk',dict(user=7,reason='Private',at=time.time()),'afk:2:7')
        message=NS(guild=self.guild,author=NS(id=8),mentions=[self.user],channel=NS(id=20),reply=AsyncMock())
        await self.p.on_message(message);message.reply.assert_not_awaited()

    async def test_personal_and_server_language_responses(self):
        self.store.set_option(1,'language','es');i=self.i();await reply(i,'Paused.')
        self.assertEqual(i.followup.send.call_args.args[0],'En pausa.')
        p=self.store.profile(1,7);p['language']='fr';self.store.save_profile(1,7,p)
        i=self.i();await reply(i,'Paused.');self.assertEqual(i.followup.send.call_args.args[0],'En pause.')

    async def test_backup_schedule_retention_and_no_personal_data(self):
        self.enable('scheduled_backups');self.store.set_option(1,'backup_keep',2)
        self.store.save_profile(1,999,dict(self.store.profile(1,999),private_note='not in config'))
        self.bot._connection._guilds[1]=self.guild
        with patch('vivi.server.productivity.ROOT',self.root):
            await self.p.tick();await self.p.tick()
            self.assertEqual(len(list((self.root/'data/backups/1').glob('*.json'))),1)
            for _ in range(3):self.p.backup(1)
            paths=list((self.root/'data/backups/1').glob('*.json'))
            self.assertEqual(len(paths),2)
            self.assertNotIn('not in config',paths[0].read_text())
            self.assertTrue(healthy(self.root/'data/heartbeat.json') is False)  # no live gateway in this test

    async def test_health_does_not_claim_connected_or_leak_error_values(self):
        self.p.error('job',ValueError('example-secret'))
        data=self.p.health(1);self.assertEqual(data['gateway'],'not connected')
        self.assertNotIn('example-secret',json.dumps(data))

    async def test_alias_read_target_checks_and_feature_switch_remain_active(self):
        self.enable('custom_aliases')
        self.store.set_option(1,'aliases',{'myqueue':dict(target='queue',argument='')})
        i=self.i();await self.p.run_alias(i,'myqueue')
        self.assertIn('music is disabled',i.followup.send.call_args.args[0])
        self.store.set_option(1,'feature:custom_aliases',False)
        i=self.i();await self.p.run_alias(i,'myqueue')
        self.assertIn('custom_aliases is disabled',i.followup.send.call_args.args[0])

    async def test_alias_native_command_registration_and_closure(self):
        self.enable('custom_aliases')
        self.store.set_option(1,'aliases',{'rules':dict(target='commands',argument='rules'),'aboutvivi':dict(target='help',argument='')})
        await self.p.refresh_aliases(1)
        command=self.bot.tree.get_command('rules',guild=discord.Object(id=1))
        self.assertEqual(command.parameters,[])
        i=self.i();await command.callback(i);self.assertIn('/community rules',i.followup.send.call_args.args[0])
        self.assertIsNone(self.bot.tree.get_command('rules',guild=discord.Object(id=2)))
        self.store.set_option(1,'aliases',{})
        await self.p.refresh_aliases(1)
        self.assertIsNone(self.bot.tree.get_command('rules',guild=discord.Object(id=1)))

    async def test_one_alias_registration_failure_does_not_block_other_servers(self):
        for gid in [1,2]:self.store.set_option(gid,'aliases',{'hello':dict(target='ping',argument='')})
        self.bot.tree.sync.side_effect=[RuntimeError('Server unavailable'),[]]
        await self.p.start_aliases()
        self.assertEqual(self.bot.tree.sync.await_count,2)
        self.assertEqual(self.p.errors[-1]['job'],'alias startup sync')
        self.assertEqual(self.p.errors[-1]['error'],'RuntimeError')

    async def test_alias_does_not_bypass_target_checks(self):
        self.enable('custom_aliases');self.store.set_option(1,'aliases',{'hello':dict(target='ping',argument='')})
        command=self.bot.tree.get_command('ping');command.checks.append(lambda i:False)
        i=self.i();await self.p.run_alias(i,'hello')
        self.assertIn('denied',i.followup.send.call_args.args[0])

    async def test_dashboard_feature_switch_records_oauth_actor(self):
        d=self.dashboard()
        with self.assertRaises(web.HTTPSeeOther):await d.feature(self.form(feature='afk',enabled='true'))
        self.assertEqual(self.store.history(1)[0]['actor'],'dashboard:7')

    async def test_dashboard_previews_are_read_only_and_escape_announcement(self):
        d=self.dashboard();count=len(self.store.history(1))
        response=await d.preview(self.form(type='welcome',text='Welcome {member}',color='#87CEEB'))
        self.assertEqual(response.content_type,'image/png');self.assertEqual(Image.open(io.BytesIO(response.body)).size,(900,260))
        response=await d.preview(self.form(type='announcement',text='<script>alert(1)</script>'))
        self.assertIn('&lt;script&gt;',response.text);self.assertNotIn('<script>',response.text)
        self.assertEqual(len(self.store.history(1)),count)

    async def test_dashboard_revision_and_backups_are_server_scoped(self):
        self.store.set_option(2,'language','fr');ident=self.store.history(2)[0]['id'];d=self.dashboard()
        request=NS(cookies={'vivi_session':'sid'},query={'guild':'1','id':str(ident)})
        with self.assertRaises(web.HTTPNotFound):await d.revision(request)
        request=NS(cookies={'vivi_session':'sid'},query={'guild':'1','name':'../../.env'})
        with self.assertRaises(web.HTTPBadRequest):await d.scheduled_backup(request)

    async def test_dashboard_rollback_requires_confirmation_and_records_actor(self):
        self.store.set_option(1,'language','es');ident=self.store.history(1)[0]['id'];d=self.dashboard()
        with self.assertRaises(web.HTTPBadRequest):await d.rollback(self.form(id=str(ident)))
        with self.assertRaises(web.HTTPSeeOther):await d.rollback(self.form(id=str(ident),confirm='yes'))
        self.assertEqual(self.store.history(1)[0]['actor'],'dashboard:7')
        self.assertEqual(self.store.history(1)[0]['action'],'restore')

    async def test_container_bind_is_explicit_and_callback_stays_loopback(self):
        with patch.dict(os.environ,{'DASHBOARD_BIND_HOST':'0.0.0.0','VIVI_CONTAINER':'0'}):
            with self.assertRaises(ValueError):Dashboard(self.service)
        with patch.dict(os.environ,{'DASHBOARD_BIND_HOST':'0.0.0.0','VIVI_CONTAINER':'1'}):
            d=Dashboard(self.service);self.assertEqual(d.host,'127.0.0.1');self.assertEqual(d.bind_host,'0.0.0.0')

if __name__=='__main__':unittest.main()
