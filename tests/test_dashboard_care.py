import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock
import discord
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from vivi.bot import ViviBot
from vivi.core.storage import Store
from vivi.core.privacy import cleanup
from vivi.site.dashboard import Dashboard

class CareTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.member=NS(id=10,display_name='Admin',roles=[],guild_permissions=discord.Permissions.all())
        self.channel=MagicMock(spec=discord.TextChannel);self.channel.id=3;self.channel.permissions_for.return_value=discord.Permissions.all();self.channel.send=AsyncMock()
        self.guild=NS(id=1,owner_id=99,name='Server',member_count=42,fetch_member=AsyncMock(return_value=self.member),get_member=lambda uid:self.member if uid==10 else None,get_channel=lambda ident:self.channel if ident==3 else None,get_role=lambda ident:None,default_role=NS(id=1),me=NS(guild_permissions=discord.Permissions.all()))
        self.bot.get_guild=lambda gid:self.guild if gid==1 else None;self.dashboard=Dashboard(self.bot.community);self.dashboard.sessions['sid']=dict(user_id=10,csrf='good',expires=time.time()+3600)
        self.dashboard.api_guilds=AsyncMock(return_value={'1':dict(id='1',permissions='8')})
    async def asyncTearDown(self):
        await self.bot.close();self.store.close();self.tmp.cleanup()
    def request(self,path):return make_mocked_request('GET',path,headers={'Cookie':'vivi_session=sid'})
    def post(self,**values):
        data=dict(csrf='good',guild='1',**values)
        return NS(cookies={'vivi_session':'sid'},post=AsyncMock(return_value=data),method='POST')
    async def test_change_log_compares_old_and_new_and_keeps_server_isolation(self):
        self.store.actor.set('dashboard:10');self.store.set_option(1,'welcome_text','OLD <script>');self.store.set_option(1,'welcome_text','NEW VALUE');self.store.set_option(2,'welcome_text','OTHER_SERVER_SECRET')
        ident=self.store.history(1)[0]['id'];response=await self.dashboard.change_log(self.request(f'/changes?guild=1&id={ident}'))
        for text in ('OLD &lt;script&gt;','NEW VALUE','Admin (10)','Previous value','UTC'):self.assertIn(text,response.text)
        self.assertNotIn('OTHER_SERVER_SECRET',response.text);self.assertNotIn('OLD <script>',response.text)
        response=await self.dashboard.change_log(self.request('/changes?guild=1&search=nonexistent'));self.assertIn('No matching',response.text)
    async def test_sensitive_pages_recheck_membership_even_with_admin_oauth_cache(self):
        self.member.guild_permissions=discord.Permissions(moderate_members=True)
        for handler,path in [(self.dashboard.change_log,'/changes'),(self.dashboard.checks_page,'/checks'),(self.dashboard.privacy_settings,'/privacy-settings')]:
            with self.assertRaises(web.HTTPForbidden):await handler(self.request(path+'?guild=1'))
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.run_checks(self.post(kind='roles'))
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.save_privacy(self.post(confirm='yes'))
    async def test_csrf_and_cross_server_privacy_review(self):
        request=self.post(kind='roles');request.post=AsyncMock(return_value=dict(csrf='bad',guild='1',kind='roles'))
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.run_checks(request)
        ident=self.store.put_record(2,'privacy',dict(author=20,status='pending',text='FOREIGN'))
        with self.assertRaises(web.HTTPNotFound):await self.dashboard.privacy_review(self.post(id=ident,status='completed',note='Reviewed'))
        response=await self.dashboard.privacy_settings(self.request('/privacy-settings?guild=1'));self.assertNotIn('FOREIGN',response.text)
    async def test_notification_tests_are_read_only_and_show_missing_permissions(self):
        self.store.put_record(1,'notification',dict(provider='youtube',source='channel',channel=3))
        before=self.store.export_config(1);response=await self.dashboard.run_checks(self.post(kind='notifications'))
        self.assertIn('Passed',response.text);self.channel.send.assert_not_awaited();self.assertEqual(before,self.store.export_config(1))
        self.channel.permissions_for.return_value=discord.Permissions.none();response=await self.dashboard.run_checks(self.post(kind='notifications'));self.assertIn('embed_links',response.text)
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.run_checks(self.post(kind='arbitrary'))
    async def test_role_checks_include_manage_roles_and_protected_staff_roles(self):
        self.store.configure(1,3,4,5,3);self.store.set_option(1,'autorole',5)
        response=await self.dashboard.run_checks(self.post(kind='roles'));self.assertIn('Role 5',response.text);self.assertIn('Needs attention',response.text)
        self.guild.me.guild_permissions=discord.Permissions.none();response=await self.dashboard.run_checks(self.post(kind='roles'));self.assertIn('Grant Vivi Manage Roles',response.text)
    async def test_retention_updates_are_atomic_and_audited(self):
        values=dict(confirm='yes',retention_history_days='30',retention_privacy_days='7',retention_ticket_events_days='0')
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_privacy(self.post(**values))
        self.assertEqual(self.store.option(1,'retention_history_days'),30);self.assertEqual(self.store.history(1)[0]['actor'],'dashboard:10')
        before=self.store.export_config(1);values['retention_privacy_days']='1'
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.save_privacy(self.post(**values))
        self.assertEqual(before,self.store.export_config(1))
    async def test_privacy_queue_pages_do_not_hide_older_requests(self):
        for number in range(26):self.store.put_record(1,'privacy',dict(author=20,status='pending',text=f'Request sequence {number}'))
        response=await self.dashboard.privacy_settings(self.request('/privacy-settings?guild=1'))
        self.assertIn('page=1',response.text);self.assertNotIn('Request sequence 0<',response.text)
        response=await self.dashboard.privacy_settings(self.request('/privacy-settings?guild=1&page=1'))
        self.assertIn('Request sequence 0',response.text)
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.privacy_settings(self.request('/privacy-settings?guild=1&page=-1'))

    async def test_privacy_review_records_actor_note_and_can_reopen(self):
        ident=self.store.put_record(1,'privacy',dict(author=20,status='pending',text='Review retained data'))
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.privacy_review(self.post(id=ident,status='completed',note=''))
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.privacy_review(self.post(id=ident,status='completed',note='Removed active records; backup review recorded.'))
        data=self.store.record(ident)['data'];self.assertEqual(data['reviewer'],10);self.assertGreater(data['resolved_at'],0)
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.privacy_review(self.post(id=ident,status='reviewing',note='Reopened for further review'))
        self.assertIsNone(self.store.record(ident)['data']['resolved_at'])
    async def test_retention_never_removes_pending_requests_active_tickets_or_other_guilds(self):
        now=time.time()
        for key in ('retention_history_days','retention_privacy_days','retention_ticket_events_days'):self.store.set_option(1,key,7)
        self.store.db.execute("UPDATE config_history SET created='2000-01-01 00:00:00' WHERE guild=1")
        old=now-30*86400
        expired=self.store.put_record(1,'privacy',dict(status='completed',resolved_at=old))
        pending=self.store.put_record(1,'privacy',dict(status='pending',resolved_at=old))
        foreign=self.store.put_record(2,'privacy',dict(status='completed',resolved_at=old))
        accepted=self.store.put_record(1,'privacy',dict(status='accepted',resolved_at=old))
        active=self.store.put_record(1,'privacy',dict(status='completed',resolved_at=now))
        self.store.add_ticket(1,20,3)
        with self.store.db:
            for gid,channel in [(1,3),(1,4),(2,5)]:self.store.db.execute('INSERT INTO ticket_events(guild,channel,at) VALUES (?,?,?)',(gid,channel,old))
        case=self.store.add_case(1,20,10,'warn','Keep evidence')
        result=cleanup(self.store,now);self.assertEqual(result['privacy'],2);self.assertEqual(result['ticket_events'],1);self.assertGreater(result['history'],0)
        self.assertIsNone(self.store.record(expired));self.assertIsNone(self.store.record(accepted))
        for ident in (pending,foreign,active):self.assertIsNotNone(self.store.record(ident))
        self.assertIsNotNone(self.store.db.execute('SELECT id FROM cases WHERE id=?',(case,)).fetchone())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM ticket_events WHERE at=?',(old,)).fetchone()[0],2)
