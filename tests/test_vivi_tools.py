import asyncio
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
import wave
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from aiohttp import web
from vivi.bot import ViviBot,register_commands,OpenTicketView
from vivi.community import register_extra
from vivi.dashboard import Dashboard
from vivi.features import enabled
from vivi.music import register_voice
from vivi.operations import register_operations,subscription,RatingView
from vivi.runtime import SingleInstance
from vivi.settings import parse_value
from vivi.startup import script,systemd_unit,linux_startup
from vivi.storage import Store,database_path
from vivi.verify import provider_checks

class Rank:
    def __init__(self,n): self.n=n
    def __lt__(self,other): return self.n<other.n
    def __gt__(self,other): return self.n>other.n
    def __ge__(self,other): return self.n>=other.n

class PureToolsTests(unittest.TestCase):
    def test_database_compatibility_and_conflict_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'data').mkdir()
            self.assertEqual(database_path(root).name,'vivi.sqlite3')
            legacy=root/'data/aurora.sqlite3'; legacy.touch()
            self.assertEqual(database_path(root),legacy)
            (root/'data/vivi.sqlite3').touch()
            with self.assertRaises(ValueError): database_path(root)

    def test_single_instance_blocks_second_process_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lock'
            first=SingleInstance(path)
            try:
                with self.assertRaises(ValueError): SingleInstance(path)
            finally: first.close()
            second=SingleInstance(path); second.close()

    def test_startup_scripts_quote_paths_and_need_no_password(self):
        windows=script(Path("folder with space/it's here"))
        self.assertIn("it''s here",windows)
        self.assertIn('-LogonType Interactive',windows)
        self.assertIn('RunLevel Limited',windows)
        self.assertNotIn('-Password',windows)
        unit=systemd_unit(Path('folder with space/100%'))
        self.assertIn('100%%',unit)
        self.assertIn('KillMode=control-group',unit)
        self.assertIn('vivi.supervisor',unit)
        with self.assertRaises(ValueError): systemd_unit(Path('bad\npath'))

    def test_notification_sources_cannot_supply_urls_or_traversal(self):
        for provider,source in [('github_releases','https://example.com/a/b'),('github_commits','owner/..'),
                                ('twitch','127.0.0.1'),('youtube','not-a-channel')]:
            with self.assertRaises(ValueError): subscription(provider,source,1)
        self.assertEqual(subscription('github_releases','owner/repo',1)['source'],'owner/repo')

    def test_extended_setting_ranges(self):
        self.assertEqual(parse_value('ticket_categories','{"Support":123}'),{'Support':123})
        self.assertEqual(parse_value('warning_count','3'),3)
        for name,text in [('warning_count','1'),('raid_action','ban_everybody'),('raid_window','1'),('mention_limit','0')]:
            with self.assertRaises(ValueError): parse_value(name,text)

    def test_linux_installer_writes_only_user_unit_and_registers_no_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'installation'; (root/'.venv/bin').mkdir(parents=True)
            (root/'.venv/bin/python').touch()
            config=Path(tmp)/'config'
            with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(config)}), patch('vivi.startup.shutil.which',return_value='/usr/bin/systemctl'), patch('vivi.startup.subprocess.run') as run:
                linux_startup(root)
                unit=config/'systemd/user/vivi-bot.service'
                self.assertIn('vivi.supervisor',unit.read_text())
                self.assertEqual(run.call_args_list[-1].args[0],['systemctl','--user','enable','vivi-bot.service'])
                linux_startup(root,True)
                self.assertFalse(unit.exists())

    def test_linux_remover_preserves_unrelated_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp);folder=config/'systemd/user';folder.mkdir(parents=True)
            unit=folder/'vivi-bot.service';unit.write_text('[Unit]\nDescription=Some other app\n')
            with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(config)}), patch('vivi.startup.shutil.which',return_value='/usr/bin/systemctl'), patch('vivi.startup.subprocess.run') as run:
                with self.assertRaises(SystemExit): linux_startup(config,True)
                run.assert_not_called()
                self.assertIn('Some other app',unit.read_text())


class ToolsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.bot=ViviBot(self.store); await self.bot.__aenter__(); self.bot._connection.user=NS(id=99)
        register_commands(self.bot);register_extra(self.bot);register_operations(self.bot);register_voice(self.bot)
        self.service=self.bot.community; self.ops=self.service.operations; self.voice=self.service.voice
        self.user=NS(id=7,display_name='Alex',roles=[NS(id=4)],guild_permissions=discord.Permissions.all(),top_role=Rank(5),voice=None)
        self.guild=NS(id=1,name='Server',owner_id=100,me=NS(id=99,top_role=Rank(10)),default_role=object(),
                      get_channel=lambda ident:None, get_role=lambda ident:None, get_member=lambda ident:self.user,
                      text_channels=[],voice_channels=[],categories=[],roles=[],voice_client=None)
        self.store.configure(1,2,3,4,5)
        self.bot.get_guild=lambda ident:self.guild if ident==1 else None
    async def asyncTearDown(self):
        await self.bot.close();self.store.close();self.tmp.cleanup()
    def interaction(self):
        return NS(guild_id=1,guild=self.guild,user=self.user,channel_id=20,
            response=NS(is_done=lambda:True,defer=AsyncMock(),send_message=AsyncMock(),edit_message=AsyncMock()),
            followup=NS(send=AsyncMock()),permissions=discord.Permissions.all())
    def command(self,group,name): return self.bot.tree.get_command(group).get_command(name).callback
    def enable(self,name): self.store.set_option(1,'feature:'+name,True)
    def dashboard(self):
        d=Dashboard(self.service);d.sessions['sid']={'token':'opaque','csrf':'good','expires':time.time()+100}
        d.api_guilds=AsyncMock(return_value={'1':{'id':'1','permissions':'8'}}); return d
    def form(self,**values):
        return NS(cookies={'vivi_session':'sid'},post=AsyncMock(return_value=dict(csrf='good',guild='1',**values)))
    def response(self,json_body=None,status=200,body=None):
        response=AsyncMock();response.status=status;response.json.return_value=json_body
        response.content=NS(read=AsyncMock(return_value=body))
        cm=MagicMock();cm.__aenter__=AsyncMock(return_value=response);cm.__aexit__=AsyncMock();return cm

    async def test_full_dashboard_setting_and_faq_editor(self):
        d=self.dashboard()
        with self.assertRaises(web.HTTPSeeOther): await d.setting(self.form(name='mention_limit',value='8'))
        self.assertEqual(self.store.option(1,'mention_limit'),8)
        with self.assertRaises(web.HTTPSeeOther): await d.faq(self.form(action='add',question='How?',answer='Like this.'))
        self.assertEqual(self.store.option(1,'faq'),{'How?':'Like this.'})
        with self.assertRaises(web.HTTPSeeOther): await d.faq(self.form(action='remove',question='How?'))
        self.assertEqual(self.store.option(1,'faq'),{})

    async def test_full_dashboard_csrf_and_revoked_admin_cannot_mutate_settings(self):
        d=self.dashboard();request=self.form(name='mention_limit',value='8')
        request.post.return_value['csrf']='bad'
        with self.assertRaises(web.HTTPForbidden): await d.setting(request)
        self.assertIsNone(self.store.option(1,'mention_limit'))
        d.api_guilds.return_value={}
        with self.assertRaises(web.HTTPForbidden): await d.setting(self.form(name='mention_limit',value='8'))
        self.assertIsNone(self.store.option(1,'mention_limit'))

    async def test_dashboard_category_and_subscriptions_are_guild_scoped(self):
        d=self.dashboard();category=MagicMock(spec=discord.CategoryChannel);category.id=30
        text=MagicMock(spec=discord.TextChannel);text.id=40
        self.guild.get_channel=lambda ident:{30:category,40:text}.get(ident)
        with self.assertRaises(web.HTTPSeeOther): await d.ticket_category(self.form(action='add',label='Support',category='30'))
        self.assertEqual(self.store.option(1,'ticket_categories'),{'Support':30})
        with self.assertRaises(web.HTTPBadRequest): await d.ticket_category(self.form(action='add',label='Wrong server',category='999'))
        with self.assertRaises(web.HTTPSeeOther): await d.subscription(self.form(action='add',provider='github_releases',source='owner/repo',channel='40'))
        ident=self.store.records(1,'notification')[0]['id']
        other=self.store.put_record(2,'notification',subscription('twitch','someone',40))
        with self.assertRaises(web.HTTPNotFound): await d.subscription(self.form(action='remove',id=other))
        self.assertIsNotNone(self.store.record(other));self.assertIsNotNone(self.store.record(ident))

    async def test_configuration_backup_preserves_subscriptions_without_poll_state(self):
        self.store.put_record(1,'notification',dict(subscription('twitch','someone',40),last='secret-state',initialized=True))
        backup=self.store.export_config(1)
        self.assertEqual(backup['version'],2)
        self.assertNotIn('last',backup['subscriptions'][0])
        self.store.restore_config(1,backup)
        self.assertFalse(self.store.records(1,'notification')[0]['data']['initialized'])
        legacy={k:v for k,v in backup.items() if k!='subscriptions'};legacy['version']=1
        self.store.restore_config(1,legacy)
        self.assertEqual(self.store.records(1,'notification'),[])

    async def test_mention_protection_does_not_require_word_filter(self):
        self.enable('mention_protection');self.store.set_option(1,'mention_limit',2)
        member=MagicMock(spec=discord.Member);member.id=7;member.bot=False;member.guild_permissions=discord.Permissions.none()
        message=NS(guild=self.guild,author=member,content='hey',mentions=[NS(id=n) for n in range(3)],role_mentions=[],mention_everyone=False,delete=AsyncMock())
        with patch.object(self.service,'case',new_callable=AsyncMock) as case: await self.service.on_message(message)
        message.delete.assert_awaited_once();self.assertEqual(case.call_args.args[4],'mention spam')

    async def test_raid_detection_alerts_once_and_pauses_newcomer_roles(self):
        self.enable('raid_protection');self.store.set_option(1,'raid_limit',3)
        member=NS(guild=self.guild)
        with patch.object(self.service,'case',new_callable=AsyncMock) as case:
            for _ in range(4): await self.ops.on_join(member)
        case.assert_awaited_once()
        self.assertGreater(self.store.option(1,'internal_raid_until'),time.time())

    async def test_warning_threshold_times_out_only_at_configured_count(self):
        self.enable('warning_thresholds');self.store.set_option(1,'warning_count',3)
        member=NS(id=8,top_role=Rank(1),timeout=AsyncMock(),send=AsyncMock())
        with patch.object(self.service,'case',new_callable=AsyncMock):
            for n in range(3):
                self.store.warn(1,8,7,'Warning')
                await self.ops.warning_threshold(self.guild,member,7)
            await self.ops.warning_threshold(self.guild,member,7)
        member.timeout.assert_awaited_once()
        self.assertEqual(member.timeout.call_args.args[0],dt.timedelta(minutes=10))

    async def test_ticket_claim_conflict_and_staff_release(self):
        self.enable('ticket_tools');self.store.add_ticket(1,8,20)
        await self.command('ticket','claim')(self.interaction())
        self.assertEqual(self.ops.ticket_meta(20)['claimed'],7)
        second=self.interaction();second.user=NS(id=9,roles=[NS(id=4)],guild_permissions=discord.Permissions.none())
        await self.command('ticket','claim')(second)
        self.assertEqual(self.ops.ticket_meta(20)['claimed'],7)
        await self.command('ticket','release')(second)
        self.assertEqual(self.ops.ticket_meta(20)['claimed'],7)
        await self.command('ticket','release')(self.interaction())
        self.assertEqual(self.ops.ticket_meta(20)['claimed'],0)

    async def test_ticket_move_preserves_private_overwrites(self):
        self.enable('ticket_tools');self.store.add_ticket(1,8,20)
        category=MagicMock(spec=discord.CategoryChannel);category.id=30
        self.guild.get_channel=lambda ident:category if ident==30 else None
        self.store.set_option(1,'ticket_categories',{'Billing':30})
        i=self.interaction();i.channel=NS(edit=AsyncMock())
        await self.command('ticket','category')(i,'Billing')
        self.assertFalse(i.channel.edit.call_args.kwargs['sync_permissions'])
        self.assertEqual(self.ops.ticket_meta(20)['category'],'Billing')

    async def test_ticket_category_menu_precedes_channel_creation(self):
        self.enable('ticket_tools');self.store.set_option(1,'ticket_categories',{'Support':30})
        i=self.interaction();await OpenTicketView(self.bot).open_ticket.callback(i)
        i.response.send_message.assert_awaited_once()
        self.assertIn('category',i.response.send_message.call_args.args[0])
        self.assertIsNone(self.store.ticket_for_user(1,7))

    async def test_rating_only_owner_once(self):
        ident=self.store.put_record(1,'ticket_rating',dict(user=7,channel=20,claimed=9,expires=time.time()+100,rating=0))
        view=RatingView(self.ops,ident);i=self.interaction();i.user=NS(id=8)
        await view.rate(i,5)
        self.assertEqual(self.store.record(ident)['data']['rating'],0)
        with patch('vivi.operations.audit',new_callable=AsyncMock):
            await view.rate(self.interaction(),4);await view.rate(self.interaction(),1)
        self.assertEqual(self.store.record(ident)['data']['rating'],4)

    async def test_notifications_baseline_new_event_and_deduplication(self):
        self.enable('notifications')
        self.store.put_record(1,'notification',subscription('twitch','someone',40),'watch')
        channel=NS(send=AsyncMock());self.guild.get_channel=lambda ident:channel
        self.ops.events=AsyncMock(return_value=[dict(id='old',title='old',url='https://example.com')])
        await self.ops.poll_notifications();channel.send.assert_not_awaited()
        record=self.store.record('watch');record['data']['next_poll']=0;self.store.put_record(1,'notification',record['data'],'watch')
        self.ops.events.return_value=[dict(id='new',title='new',url='https://example.com')]
        await self.ops.poll_notifications();channel.send.assert_awaited_once()
        record=self.store.record('watch');record['data']['next_poll']=0;self.store.put_record(1,'notification',record['data'],'watch')
        await self.ops.poll_notifications();channel.send.assert_awaited_once()

    async def test_removed_subscription_cannot_be_resurrected_after_provider_request(self):
        self.enable('notifications');self.store.put_record(1,'notification',subscription('twitch','someone',40),'watch')
        channel=NS(send=AsyncMock());self.guild.get_channel=lambda ident:channel
        async def fetch(*args):
            self.store.delete_record('watch')
            return [dict(id='event',title='Event',url='https://example.com')]
        self.ops.events=AsyncMock(side_effect=fetch)
        await self.ops.poll_notifications()
        self.assertIsNone(self.store.record('watch'));channel.send.assert_not_awaited()

    async def test_disabling_notifications_during_fetch_prevents_post(self):
        self.enable('notifications')
        data=dict(subscription('twitch','someone',40),initialized=True,last='old')
        self.store.put_record(1,'notification',data,'watch')
        channel=NS(send=AsyncMock());self.guild.get_channel=lambda ident:channel
        async def fetch(*args):
            self.store.set_option(1,'feature:notifications',False)
            return [dict(id='new',title='Event',url='https://example.com')]
        self.ops.events=AsyncMock(side_effect=fetch)
        await self.ops.poll_notifications();channel.send.assert_not_awaited()
        self.assertEqual(self.store.record('watch')['data']['last'],'old')

    async def test_github_token_used_only_for_bound_server_and_repository(self):
        self.service.session=NS(get=MagicMock(side_effect=[self.response([]),self.response([])]),close=AsyncMock())
        with patch.dict(os.environ,{'NOTIFY_GITHUB_TOKEN':'example-not-a-real-token','NOTIFY_GITHUB_ACCESS':'{"1":["owner/repo"]}'}):
            await self.ops.events(subscription('github_releases','owner/repo',40),2)
            self.assertNotIn('Authorization',self.service.session.get.call_args.kwargs['headers'])
            await self.ops.events(subscription('github_releases','owner/repo',40),1)
            self.assertIn('Authorization',self.service.session.get.call_args.kwargs['headers'])
            self.assertFalse(self.service.session.get.call_args.kwargs['allow_redirects'])

    async def test_youtube_feed_metadata_is_parsed_without_video_download(self):
        feed=b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry><yt:videoId>abc</yt:videoId><title>New upload</title></entry></feed>'
        self.service.session=NS(get=MagicMock(return_value=self.response(body=feed)),close=AsyncMock())
        events=await self.ops.events(subscription('youtube','UC'+'a'*22,40),1)
        self.assertEqual(events,[dict(id='abc',title='New upload',url='https://www.youtube.com/watch?v=abc')])

    async def test_provider_error_is_retained_for_retry_without_secrets(self):
        self.enable('notifications');self.store.put_record(1,'notification',subscription('twitch','someone',40),'watch')
        self.ops.events=AsyncMock(side_effect=RuntimeError('credential-secret-do-not-store'))
        with self.assertLogs('vivi.operations',level='WARNING'): await self.ops.poll_notifications()
        data=self.store.record('watch')['data']
        self.assertEqual(data['error'],'RuntimeError');self.assertGreater(data['next_poll'],time.time())
        self.assertNotIn('credential-secret',json.dumps(data))

    async def test_music_controls_require_same_voice_channel(self):
        mine=MagicMock(spec=discord.VoiceChannel);mine.id=1
        self.user.voice=NS(channel=mine);self.guild.voice_client=NS(channel=NS(id=2),is_connected=lambda:True)
        with self.assertRaises(ValueError): await self.voice.actor_channel(self.interaction(),True)
        self.guild.voice_client=None

    async def test_music_rejects_url_playlists_and_oversized_uploads(self):
        for name,size in [('playlist.m3u',10),('track.mp3',11*1024*1024)]:
            attachment=NS(filename=name,size=size,read=AsyncMock())
            with self.assertRaises(ValueError): await self.voice.enqueue(self.interaction(),attachment)
            attachment.read.assert_not_awaited()

    async def test_stale_audio_callback_cannot_skip_new_playback(self):
        self.voice.active[1]=dict(path='new-track')
        with patch.object(self.voice,'_next',new_callable=AsyncMock) as next_track:
            await self.voice.advance(self.guild,'old-track')
        next_track.assert_not_awaited()
        self.voice.active.clear()

    async def test_room_unlock_restores_original_private_connect_deny(self):
        self.enable('voice_rooms')
        channel=MagicMock(spec=discord.VoiceChannel);channel.id=20
        channel.overwrites_for.return_value=discord.PermissionOverwrite(connect=False)
        channel.set_permissions=AsyncMock()
        self.user.voice=NS(channel=channel)
        self.store.put_record(1,'voice_room',dict(channel=20,owner=7,previous_connect=False),'voice:20')
        await self.command('room','lock')(self.interaction(),False)
        self.assertFalse(channel.set_permissions.call_args.kwargs['overwrite'].connect)
        self.store.delete_record('voice:20')

    async def test_provider_verification_absent_credentials_makes_no_request(self):
        session=NS(post=MagicMock())
        with patch.dict(os.environ,{'AI_BASE_URL':'','AI_MODEL':'','TRANSLATE_URL':''}):
            report=await provider_checks(session,True)
        session.post.assert_not_called()
        self.assertTrue(all(r['status']=='not configured' for r in report))

    async def test_real_ffmpeg_decodes_local_wav_to_discord_pcm(self):
        executable=shutil.which('ffmpeg')
        if not executable: self.skipTest('FFmpeg is an optional host dependency; not installed on this runner.')
        path=Path(self.tmp.name)/'audio.wav'
        with wave.open(str(path),'wb') as audio:
            audio.setnchannels(2);audio.setsampwidth(2);audio.setframerate(48000);audio.writeframes(b'\x00'*3840*3)
        source=discord.FFmpegPCMAudio(str(path),executable=executable,before_options='-nostdin -protocol_whitelist file,pipe -f wav',options='-vn')
        try:
            self.assertEqual(len(source.read()),3840)
        finally: source.cleanup()

if __name__=='__main__': unittest.main()
