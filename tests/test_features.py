import asyncio
import datetime as dt
import io
import hashlib
import hmac
import sqlite3
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from aiohttp import web
from aiohttp.test_utils import make_mocked_request, TestClient, TestServer
from PIL import Image

from vivi.bot import ViviBot, register_commands
from vivi.server.community import FeatureView, GameView, DeleteView, card_bytes, register_extra
from vivi.site.dashboard import Dashboard
from vivi.core.features import (FEATURES, SHOP, award_activity, blocked_word, convert, enabled,
                             suspicious_link, validate_backup, validate_option, win_board)
from vivi.core.storage import Store

class PureTests(unittest.TestCase):
    def test_suspicious_links_without_opening_urls(self):
        for text in ['https://user:pass@example.com', 'https://127.0.0.1/a',
                     'https://xn--example.com', 'https://sub.bad.example/path']:
            self.assertTrue(suspicious_link(text,['bad.example']))
        self.assertFalse(suspicious_link('https://notbad.example/path https://example.com', ['bad.example']))

    def test_blocked_words_match_boundaries_and_escape_regex(self):
        self.assertTrue(blocked_word('A blocked word', ['blocked']))
        self.assertFalse(blocked_word('Scunthorpe', ['cunt']))
        self.assertFalse(blocked_word('anything', ['.*']))

    def test_units_and_temperature_validation(self):
        self.assertAlmostEqual(convert(1,'mi','m'),1609.344)
        self.assertAlmostEqual(convert(32,'f','c'),0)
        self.assertAlmostEqual(convert(0,'c','k'),273.15)
        with self.assertRaises(ValueError): convert(-1,'k','c')
        with self.assertRaises(ValueError): convert(1,'kg','m')

    def test_xp_cooldown_and_duplicate_message_defense(self):
        p=dict(last_xp=0,last_hash='',xp=0,coins=0,achievements=[])
        self.assertTrue(award_activity(p,'hello server',100))
        self.assertFalse(award_activity(p,'another message',110))
        self.assertFalse(award_activity(p,'HELLO SERVER',200))
        self.assertFalse(award_activity(p,'a',200))
        self.assertTrue(award_activity(p,'different message',201))
        self.assertEqual((p['xp'],p['coins']),(20,4))
        self.assertEqual(p['achievements'],['First words'])

    def test_tictactoe_results(self):
        self.assertEqual(win_board(['X','X','X','','','','','','']),'X')
        self.assertEqual(win_board(['X','O','X','X','O','O','O','X','X']),'draw')
        self.assertIsNone(win_board(['']*9))

    def test_welcome_card_has_avatar_and_valid_png(self):
        avatar=io.BytesIO(); Image.new('RGB',(20,20),'red').save(avatar,format='PNG')
        data=card_bytes('Alex','Our Server','Please read the rules.','#87CEEB',avatar.getvalue())
        image=Image.open(io.BytesIO(data))
        self.assertEqual(image.size,(900,260))
        self.assertEqual(image.getpixel((110,130)),(255,0,0))

    def test_setting_validation_rejects_unsafe_shapes(self):
        for key,value in [('feature:ai','true'),('ai_channels',['123']),('welcome_color','red'),
                          ('spam_limit',0),('daily_hour',24),('unknown','a')]:
            with self.assertRaises((ValueError,KeyError)): validate_option(key,value)
        validate_option('ai_channels',[123])
        validate_option('timezone','America/New_York')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'db.sqlite3')
    def tearDown(self): self.store.close(); self.tmp.cleanup()

    def test_features_default_to_opt_in_except_existing_core(self):
        self.assertFalse(enabled(self.store,1,'ai'))
        self.assertFalse(enabled(self.store,1,'automod'))
        self.assertTrue(enabled(self.store,1,'moderation'))
        self.store.set_option(1,'feature:ai',True)
        self.assertTrue(enabled(self.store,1,'ai'))
        self.assertFalse(enabled(self.store,2,'ai'))

    def test_backup_is_scoped_and_excludes_personal_data(self):
        self.store.configure(1,2,3,4,5); self.store.set_option(1,'feature:ai',False)
        self.store.set_option(1,'internal_daily:birthdays','2026-11-06')
        self.store.set_option(1,'faq',{'How?':'Like this.'})
        self.store.add_role(1,8); p=self.store.profile(1,9); p['coins']=99; self.store.save_profile(1,9,p)
        backup=self.store.export_config(1)
        self.assertNotIn('internal_daily:birthdays',backup['options'])
        self.assertNotIn('profiles',backup)
        self.store.set_option(1,'feature:ai',True)
        self.store.restore_config(1,backup)
        self.assertFalse(enabled(self.store,1,'ai'))
        self.assertEqual(self.store.profile(1,9)['coins'],99)
        with self.assertRaises(ValueError): self.store.restore_config(2,backup)
        bad=dict(backup,options={'AI_API_KEY':'secret'})
        with self.assertRaises(ValueError): self.store.restore_config(1,bad)
        self.assertEqual(self.store.option(1,'faq'),{'How?':'Like this.'})

    def test_cases_are_server_scoped_and_searchable(self):
        case=self.store.add_case(1,7,8,'timeout','Repeated spam')
        self.store.add_case(2,7,8,'ban','Repeated spam')
        rows=self.store.search_cases(1,7,'SPAM')
        self.assertEqual([x['id'] for x in rows],[case])
        self.assertEqual(self.store.search_cases(1,9,'SPAM'),[])

    def test_privacy_self_service_preserves_moderation_pending_staff_review(self):
        self.store.save_profile(1,7,self.store.profile(1,7)); self.store.save_profile(2,7,self.store.profile(2,7))
        self.store.warn(1,7,8,'Reason'); self.store.add_case(1,7,8,'warn','Reason')
        item=self.store.put_record(1,'poll',{})
        self.store.vote(item,7,1)
        self.store.delete_personal(1,7)
        self.assertEqual(self.store.votes(item),[])
        self.assertEqual(len(self.store.warnings(1,7)),1)
        self.assertEqual(len(self.store.profiles(1)),0)
        self.assertEqual(len(self.store.profiles(2)),1)
        self.store.erase_moderation(1,7)
        self.assertEqual(self.store.warnings(1,7),[])
        self.assertEqual(self.store.search_cases(1,7),[])

    def test_legacy_warnings_migrate_to_cases_once(self):
        path=Path(self.tmp.name)/'legacy.sqlite3'
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE warnings(id INTEGER PRIMARY KEY,guild INTEGER,user INTEGER,moderator INTEGER,reason TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP)')
        db.execute("INSERT INTO warnings(guild,user,moderator,reason) VALUES(1,7,8,'Old warning')")
        db.commit(); db.close()
        first=Store(path); self.assertEqual(len(first.search_cases(1,7)),1); first.close()
        second=Store(path); self.assertEqual(len(second.search_cases(1,7)),1); second.close()

    def test_privacy_removes_anonymous_open_poll_ballot(self):
        salt='ab'*32
        ident=self.store.put_record(1,'poll',dict(anonymous=True,salt=salt))
        voter=hmac.new(bytes.fromhex(salt),b'7',hashlib.sha256).hexdigest()
        self.store.vote(ident,voter,1)
        self.store.delete_personal(1,7)
        self.assertEqual(self.store.votes(ident),[])



class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.bot=ViviBot(self.store); await self.bot.__aenter__()
        self.bot._connection.user=NS(id=99)
        self.service=self.bot.community
        register_commands(self.bot); register_extra(self.bot)
        self.guild=NS(id=1,owner_id=100,me=NS(id=99),get_channel=lambda x:None, text_channels=[],categories=[],voice_channels=[],roles=[])
        self.user=NS(id=7,bot=False,display_name='Alex',guild_permissions=discord.Permissions.all())
    async def asyncTearDown(self):
        await self.bot.close(); self.store.close(); self.tmp.cleanup()
    def i(self):
        return NS(guild_id=1,guild=self.guild,user=self.user,channel_id=20,
            response=NS(is_done=lambda:True,defer=AsyncMock(),send_message=AsyncMock(),edit_message=AsyncMock()),
            followup=NS(send=AsyncMock()),permissions=discord.Permissions.all())
    def command(self,group,name): return self.bot.tree.get_command(group).get_command(name).callback

    async def test_disabled_ai_makes_no_provider_request(self):
        self.service.session=NS(post=MagicMock(),close=AsyncMock())
        i=self.i(); await self.command('ai','ask')(i,'hello')
        self.service.session.post.assert_not_called()
        self.assertIn('disabled',i.followup.send.call_args.args[0])

    async def test_ai_requires_allowed_channel_even_if_enabled(self):
        self.store.set_option(1,'feature:ai',True)
        self.service.session=NS(post=MagicMock(),close=AsyncMock())
        i=self.i(); await self.command('ai','ask')(i,'hello')
        self.service.session.post.assert_not_called()
        self.assertIn('not allowed',i.followup.send.call_args.args[0])

    async def test_ai_budget_blocks_provider(self):
        self.store.set_option(1,'feature:ai',True); self.store.set_option(1,'ai_channels',[20]); self.store.set_option(1,'ai_limit',1)
        p=self.store.profile(1,7); p.update(ai_day=dt.datetime.now(dt.timezone.utc).date().isoformat(),ai_used=1)
        self.store.save_profile(1,7,p)
        self.service.session=NS(post=MagicMock(),close=AsyncMock())
        with patch.dict(os.environ,{'AI_BASE_URL':'http://localhost:11434/v1','AI_MODEL':'model'}):
            await self.command('ai','ask')(self.i(),'hello')
        self.service.session.post.assert_not_called()

    async def test_ai_response_and_opt_in_memory(self):
        self.store.set_option(1,'feature:ai',True); self.store.set_option(1,'ai_channels',[20])
        p=self.store.profile(1,7); p['memory']=True; self.store.save_profile(1,7,p)
        response=AsyncMock(); response.status=200
        response.json.return_value={'choices':[{'message':{'content':'Hello Alex'}}]}
        cm=MagicMock(); cm.__aenter__=AsyncMock(return_value=response); cm.__aexit__=AsyncMock()
        self.service.session=NS(post=MagicMock(return_value=cm),close=AsyncMock())
        with patch.dict(os.environ,{'AI_BASE_URL':'http://localhost:11434/v1','AI_MODEL':'model'}):
            i=self.i(); await self.command('ai','ask')(i,'Hello')
        self.assertEqual(i.followup.send.call_args.args[0],'Hello Alex')
        self.assertEqual(len(self.store.profile(1,7)['turns']),2)
        self.assertEqual(self.store.profile(1,7)['ai_used'],1)
        await self.command('ai','memory')(self.i(),False)
        self.assertEqual(self.store.profile(1,7)['turns'],[])

    async def test_clearing_ai_memory_while_request_runs_does_not_restore_old_turns(self):
        self.store.set_option(1,'feature:ai',True); self.store.set_option(1,'ai_channels',[20])
        p=self.store.profile(1,7); p.update(memory=True,turns=[{'role':'user','content':'Old secret'}],memory_at=time.time())
        self.store.save_profile(1,7,p)
        async def response_json():
            await self.command('ai','clear')(self.i())
            return {'choices':[{'message':{'content':'Response'}}]}
        response=AsyncMock(); response.status=200; response.json.side_effect=response_json
        cm=MagicMock(); cm.__aenter__=AsyncMock(return_value=response); cm.__aexit__=AsyncMock()
        self.service.session=NS(post=MagicMock(return_value=cm),close=AsyncMock())
        with patch.dict(os.environ,{'AI_BASE_URL':'http://localhost:11434/v1','AI_MODEL':'model'}):
            await self.command('ai','ask')(self.i(),'Hi')
        self.assertEqual(self.store.profile(1,7)['turns'],[])

    async def test_automod_deletes_blocked_content_without_awarding_xp(self):
        self.store.set_option(1,'feature:automod',True); self.store.set_option(1,'feature:xp',True)
        self.store.set_option(1,'blocked_words',['blocked'])
        author=MagicMock(spec=discord.Member); author.id=7; author.bot=False
        author.guild_permissions=discord.Permissions.none()
        message=NS(guild=self.guild,author=author,content='This is blocked content',delete=AsyncMock())
        with patch.object(self.service,'case',new_callable=AsyncMock) as case:
            await self.service.on_message(message)
        message.delete.assert_awaited_once(); case.assert_awaited_once()
        self.assertEqual(self.store.profile(1,7)['xp'],0)

    async def test_message_edits_do_not_farm_xp(self):
        self.store.set_option(1,'feature:xp',True)
        author=MagicMock(spec=discord.Member); author.id=7; author.bot=False
        message=NS(guild=self.guild,author=author,content='A valid edited message')
        await self.service.on_message(message,edited=True)
        self.assertEqual(self.store.profile(1,7)['xp'],0)

    async def test_translation_uses_only_explicit_text(self):
        self.store.set_option(1,'feature:translation',True)
        response=AsyncMock(); response.status=200; response.json.return_value={'translatedText':'Hola'}
        cm=MagicMock(); cm.__aenter__=AsyncMock(return_value=response); cm.__aexit__=AsyncMock()
        self.service.session=NS(post=MagicMock(return_value=cm),close=AsyncMock())
        with patch.dict(os.environ,{'TRANSLATE_URL':'https://translate.example/translate','TRANSLATE_API_KEY':''}):
            i=self.i(); await self.command('tools','translate')(i,'Hello','es','en')
        self.assertEqual(i.followup.send.call_args.args[0],'Hola')
        self.assertEqual(self.service.session.post.call_args.kwargs['json']['q'],'Hello')
        self.assertFalse(self.service.session.post.call_args.kwargs['allow_redirects'])

    async def test_anonymous_poll_uses_hash_and_replaces_vote(self):
        self.store.set_option(1,'feature:polls',True)
        ident=self.store.put_record(1,'poll',dict(choices=['A','B'],ends=time.time()+100,anonymous=True,salt='ab'*32))
        view=FeatureView(self.service,self.store.record(ident))
        await view.click(self.i(),0); await view.click(self.i(),1)
        ballots=self.store.votes(ident)
        self.assertEqual(len(ballots),1); self.assertNotEqual(ballots[0]['voter'],'7')
        self.assertEqual(ballots[0]['value'],1)

    async def test_closed_poll_rejects_votes(self):
        self.store.set_option(1,'feature:polls',True)
        ident=self.store.put_record(1,'poll',dict(choices=['A','B'],closed=True))
        await FeatureView(self.service,self.store.record(ident)).click(self.i(),0)
        self.assertEqual(self.store.votes(ident),[])

    async def test_giveaway_requirements_and_reroll_exclusion(self):
        now=discord.utils.utcnow()
        member=NS(id=7,bot=False,created_at=now-dt.timedelta(days=100),joined_at=now-dt.timedelta(days=20),
                  roles=[NS(id=30)],guild=self.guild)
        data=dict(account_days=30,member_days=10,role=30,level=0,winners=1,prize='Fun',channel=20,draws=[])
        self.assertTrue(self.service.eligible(member,data))
        member.roles=[]; self.assertFalse(self.service.eligible(member,data)); member.roles=[NS(id=30)]
        channel=NS(send=AsyncMock()); self.guild.get_channel=lambda x:channel; self.guild.fetch_member=AsyncMock(return_value=member)
        self.bot.get_guild=lambda x:self.guild
        ident=self.store.put_record(1,'giveaway',data); self.store.vote(ident,7,1)
        await self.service.draw(self.store.record(ident))
        self.assertEqual(self.store.record(ident)['data']['draws'][0]['winners'],[7])
        await self.service.draw(self.store.record(ident),100)
        self.assertEqual(self.store.record(ident)['data']['draws'][1]['winners'],[])
        self.assertEqual(channel.send.await_count,2)

    async def test_expired_tempban_and_lockdown_restore_after_restart(self):
        self.bot.get_guild=lambda x:self.guild
        ban=self.store.put_record(1,'tempban',dict(user=7,until=time.time()-10))
        self.guild.fetch_ban=AsyncMock(return_value=NS(reason=f'Vivi tempban {ban}: test'))
        self.guild.unban=AsyncMock()
        self.guild.default_role=object()
        channel=NS(overwrites_for=lambda role:discord.PermissionOverwrite(send_messages=False),set_permissions=AsyncMock())
        self.guild.get_channel=lambda x:channel
        lock=self.store.put_record(1,'lockdown',dict(channel=20,previous=None,until=time.time()-1))
        with patch.object(self.service,'case',new_callable=AsyncMock): await self.service.run_due()
        self.guild.unban.assert_awaited_once()
        self.assertIsNone(channel.set_permissions.call_args.kwargs['overwrite'].send_messages)
        self.assertIsNone(self.store.record(ban)); self.assertIsNone(self.store.record(lock))

    async def test_manual_reban_is_not_removed_by_old_tempban(self):
        self.bot.get_guild=lambda x:self.guild
        ident=self.store.put_record(1,'tempban',dict(user=7,until=time.time()-1))
        self.guild.fetch_ban=AsyncMock(return_value=NS(reason='New permanent ban by human moderator'))
        self.guild.unban=AsyncMock()
        await self.service.run_due()
        self.guild.unban.assert_not_awaited(); self.assertIsNone(self.store.record(ident))

    async def test_timer_failure_retains_work_for_retry(self):
        self.bot.get_guild=lambda x:self.guild
        ident=self.store.put_record(1,'tempban',dict(user=7,until=time.time()-1))
        self.guild.fetch_ban=AsyncMock(side_effect=RuntimeError('Network unavailable'))
        with self.assertLogs('vivi.server.community',level='ERROR'): await self.service.run_due()
        self.assertIsNotNone(self.store.record(ident))

    async def test_shop_does_not_spend_twice_or_allow_negative_balance(self):
        self.store.set_option(1,'feature:economy',True)
        p=self.store.profile(1,7); p['coins']=100; self.store.save_profile(1,7,p)
        await self.command('economy','buy')(self.i(),'starlight')
        await self.command('economy','buy')(self.i(),'starlight')
        await self.command('economy','buy')(self.i(),'royal')
        self.assertEqual(self.store.profile(1,7)['coins'],0)
        self.assertEqual(self.store.profile(1,7)['owned'],['starlight'])

    async def test_game_blocks_other_players_and_double_rewards(self):
        self.store.set_option(1,'feature:games',True); self.store.set_option(1,'feature:economy',True)
        view=GameView(self.service,7,trivia=('Question',['A','B'],0))
        outsider=self.i(); outsider.user=NS(id=8)
        await view.play(outsider,0)
        self.assertFalse(view.done)
        await view.play(self.i(),0); await view.play(self.i(),0)
        self.assertEqual(self.store.profile(1,7)['coins'],10)

    async def test_admin_settings_reject_nonadmin(self):
        i=self.i(); i.user=NS(id=7,guild_permissions=discord.Permissions.none())
        command=self.bot.tree.get_command('admin').get_command('feature')
        with self.assertRaises(discord.app_commands.MissingPermissions):
            await command.checks[0](i)

    async def test_moderator_inbox_hides_privacy_requests_but_admin_can_review(self):
        self.store.put_record(1,'privacy',dict(author=20,text='PRIVATE_DELETION_REQUEST',status='pending'))
        self.store.put_record(1,'report',dict(author=20,text='MODERATION_REPORT',status='pending'))
        self.user.guild_permissions=discord.Permissions(moderate_members=True)
        interaction=self.i();await self.command('mod','inbox')(interaction)
        message=interaction.followup.send.call_args.args[0]
        self.assertIn('MODERATION_REPORT',message);self.assertNotIn('PRIVATE_DELETION_REQUEST',message)
        self.user.guild_permissions=discord.Permissions.all()
        interaction=self.i();await self.command('mod','inbox')(interaction)
        self.assertIn('PRIVATE_DELETION_REQUEST',interaction.followup.send.call_args.args[0])

    async def test_data_deletion_requires_confirmation_and_keeps_server_isolation(self):
        p=self.store.profile(1,7); p['birthday']='07-23'; self.store.save_profile(1,7,p)
        view=DeleteView(self.service,7,1)
        i=self.i(); i.user=NS(id=8)
        await view.confirm.callback(i)
        self.assertEqual(self.store.profile(1,7)['birthday'],'07-23')
        i=self.i()
        with patch('vivi.server.community.audit',new_callable=AsyncMock): await view.confirm.callback(i)
        self.assertEqual(self.store.profile(1,7)['birthday'],'')
        self.assertEqual(len(self.store.records(1,'privacy')),1)

    async def test_dashboard_requires_fresh_admin_rights_and_rejects_csrf(self):
        dashboard=Dashboard(self.service)
        dashboard.sessions['sid']={'token':'opaque','csrf':'good','expires':time.time()+100}
        request=make_mocked_request('GET','/',headers={'Cookie':'vivi_session=sid'})
        dashboard.api_guilds=AsyncMock(return_value={})
        self.bot.get_guild=lambda x:self.guild
        with self.assertRaises(web.HTTPForbidden): await dashboard.authorize(request,1)
        post=NS(cookies={'vivi_session':'sid'},post=AsyncMock(return_value={'csrf':'wrong','guild':'1','feature':'ai','enabled':'true'}))
        with self.assertRaises(web.HTTPForbidden): await dashboard.feature(post)
        self.assertFalse(enabled(self.store,1,'ai'))

    async def test_dashboard_oauth_state_rejects_wrong_browser(self):
        dashboard=Dashboard(self.service)
        dashboard.states['state']={'expires':time.time()+100,'verifier':'correct'}
        request=NS(query={'state':'state','code':'unused'},cookies={'vivi_oauth':'wrong'})
        with self.assertRaises(web.HTTPForbidden): await dashboard.callback(request)
        self.assertNotIn('state',dashboard.states)

    async def test_dashboard_serves_login_page_and_security_headers(self):
        dashboard=Dashboard(self.service)
        server=TestServer(dashboard.app)
        client=TestClient(server)
        try:
            await client.start_server()
            dashboard.host='127.0.0.1'; dashboard.port=server.port
            response=await client.get('/')
            self.assertEqual(response.status,200)
            self.assertIn('Sign in with Discord',await response.text())
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertEqual(response.headers['X-Frame-Options'],'DENY')
            response=await client.get('/callback?state=invalid&code=invalid')
            self.assertEqual(response.status,403)
            response=await client.get('/',headers={'Host':'evil.example'})
            self.assertEqual(response.status,403)
        finally: await client.close()

    async def test_dashboard_rejects_remote_binding(self):
        with patch.dict(os.environ,{'DASHBOARD_REDIRECT_URI':'http://0.0.0.0:8765/callback'}):
            with self.assertRaises(ValueError): Dashboard(self.service)

    async def test_dashboard_permission_change_is_applied_and_html_is_escaped(self):
        self.guild.name='<script>evil</script>'
        dashboard=Dashboard(self.service)
        dashboard.sessions['sid']={'token':'opaque','csrf':'good','expires':time.time()+100}
        dashboard.api_guilds=AsyncMock(return_value={'1':{'id':'1','name':self.guild.name,'permissions':'8'}})
        self.bot.get_guild=lambda x:self.guild
        request=make_mocked_request('GET','/?guild=1',headers={'Cookie':'vivi_session=sid'})
        response=await dashboard.index(request)
        self.assertIn('&lt;script&gt;',response.text); self.assertNotIn('<script>',response.text)
        post=NS(cookies={'vivi_session':'sid'},post=AsyncMock(return_value={'csrf':'good','guild':'1','feature':'ai','enabled':'true'}))
        with self.assertRaises(web.HTTPSeeOther): await dashboard.feature(post)
        self.assertTrue(enabled(self.store,1,'ai'))
        dashboard.api_guilds.return_value={}
        with self.assertRaises(web.HTTPForbidden): await dashboard.feature(post)

    async def test_dashboard_settings_sync_with_discord_commands_and_recheck_permissions(self):
        dashboard=Dashboard(self.service)
        self.bot.get_guild=lambda gid:self.guild if gid==1 else None
        dashboard.sessions['sid']={'token':'opaque','csrf':'good','expires':time.time()+100}
        dashboard.api_guilds=AsyncMock(return_value={'1':{'id':'1','permissions':'8'}})
        request=make_mocked_request('GET','/api/dashboard-state?guild=1',headers={'Cookie':'vivi_session=sid'})
        initial=json.loads((await dashboard.dashboard_state(request)).text)['revision']
        await self.command('admin','setting')(self.i(),'welcome_text','Hello from Discord')
        changed=json.loads((await dashboard.dashboard_state(request)).text)['revision']
        self.assertNotEqual(initial,changed)
        self.assertEqual(changed,json.loads((await dashboard.dashboard_state(request)).text)['revision'])
        post=NS(cookies={'vivi_session':'sid'},post=AsyncMock(return_value={'csrf':'good','guild':'1','name':'welcome_text','value':'Hello from the dashboard'}))
        with self.assertRaises(web.HTTPSeeOther):await dashboard.setting(post)
        self.assertEqual(self.store.option(1,'welcome_text'),'Hello from the dashboard')
        self.assertNotEqual(changed,json.loads((await dashboard.dashboard_state(request)).text)['revision'])
        self.assertNotIn('Hello from the dashboard',(await dashboard.dashboard_state(request)).text)
        dashboard.api_guilds.return_value={}
        with self.assertRaises(web.HTTPForbidden):await dashboard.dashboard_state(request)

if __name__=='__main__': unittest.main()
