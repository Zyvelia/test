import datetime as dt
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import discord
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from vivi.bot import ViviBot
from vivi.core.storage import Store
from vivi.site.dashboard import Dashboard
from vivi.site.studio_layout import DEFAULT_LAYOUT,validate_layout,render_layout
from vivi.tray import tray_image

class StaffDashboardTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.bot=ViviBot(self.store);await self.bot.__aenter__()
  self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
  self.member=NS(id=10,roles=[],guild_permissions=discord.Permissions(administrator=True))
  self.channel=NS(id=30,created_at=dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=2))
  self.guild=NS(id=1,owner_id=99,name='Velvet Ruins',member_count=42,fetch_member=AsyncMock(side_effect=lambda uid:self.member),get_channel=lambda ident:self.channel if ident==30 else None)
  self.bot.get_guild=lambda gid:self.guild if gid==1 else None;self.dashboard=Dashboard(self.bot.community);self.dashboard.sessions['sid']=dict(user_id=10,token='secret-token',csrf='good',expires=time.time()+3600)
  self.case=self.store.add_case(1,20,10,'ban','Spam <script>alert(1)</script> links');self.foreign=self.store.add_case(2,20,10,'kick','OTHER_SERVER_SECRET')
  self.store.put_record(1,'report',dict(author=20,target=30,text='REPORT_PRIVATE',status='pending'),'report-one');self.store.put_record(1,'appeal',dict(author=20,case=self.case,text='APPEAL_PRIVATE',status='pending'),'appeal-one');self.store.put_record(2,'report',dict(author=20,text='OTHER_SERVER_SECRET',status='pending'),'report-two')
  self.store.add_ticket(1,20,30);self.bot.community.operations.save_ticket_meta(1,30,dict(priority='urgent',claimed=10,category='General'))
  self.store.db.execute('UPDATE ticket_events SET at=? WHERE guild=1 AND channel=30',(time.time()-7200,));self.store.db.commit()
 async def asyncTearDown(self):await self.dashboard.close();await self.bot.close();self.store.close();self.tmp.cleanup()
 def request(self,path):return make_mocked_request('GET',path,headers={'Cookie':'vivi_session=sid'})
 async def test_home_uses_actual_counts_and_bot_state(self):
  response=await self.dashboard.staff_home(self.request('/staff?guild=1'));self.assertIn('42',response.text);self.assertIn('Offline',response.text);self.assertIn('Enabled modules',response.text);self.assertIn('Pending reports',response.text);self.assertNotIn('secret-token',response.text)
 async def test_ordinary_members_denied_before_record_queries(self):
  self.member.guild_permissions=discord.Permissions.none()
  for handler,path in [(self.dashboard.staff_home,'/staff'),(self.dashboard.staff_cases,'/staff/cases'),(self.dashboard.staff_queue,'/staff/queue'),(self.dashboard.staff_tickets,'/staff/tickets')]:
   with self.subTest(path=path),self.assertRaises(web.HTTPForbidden):await handler(self.request(path+'?guild=1'))
 async def test_moderators_get_cases_and_queue_but_not_support_without_authority(self):
  self.member.guild_permissions=discord.Permissions(moderate_members=True)
  response=await self.dashboard.staff_cases(self.request('/staff/cases?guild=1'));self.assertIn('Moderation cases',response.text);self.assertNotIn('/modules?',response.text)
  await self.dashboard.staff_queue(self.request('/staff/queue?guild=1'))
  with self.assertRaises(web.HTTPForbidden):await self.dashboard.staff_tickets(self.request('/staff/tickets?guild=1'))
 async def test_support_role_gets_tickets_but_not_moderation(self):
  self.store.configure(1,30,40,50,60);self.member.guild_permissions=discord.Permissions.none();self.member.roles=[NS(id=50)]
  response=await self.dashboard.staff_tickets(self.request('/staff/tickets?guild=1'));self.assertIn('urgent',response.text);self.assertIn('2h',response.text);self.assertIn('Claimed by',response.text)
  for handler,path in [(self.dashboard.staff_cases,'/staff/cases'),(self.dashboard.staff_queue,'/staff/queue')]:
   with self.assertRaises(web.HTTPForbidden):await handler(self.request(path+'?guild=1'))
 async def test_case_filters_detail_and_server_isolation(self):
  response=await self.dashboard.staff_cases(self.request('/staff/cases?guild=1&member=20&action=ban&reason=Spam'));self.assertIn('#'+str(self.case),response.text);self.assertNotIn('OTHER_SERVER_SECRET',response.text);self.assertNotIn('<script>alert',response.text)
  response=await self.dashboard.staff_cases(self.request(f'/staff/cases?guild=1&case={self.case}'));self.assertIn('Time (UTC)',response.text);self.assertIn('Staff member ID',response.text);self.assertIn('&lt;script&gt;',response.text)
  with self.assertRaises(web.HTTPNotFound):await self.dashboard.staff_cases(self.request(f'/staff/cases?guild=1&case={self.foreign}'))
  response=await self.dashboard.staff_cases(self.request('/staff/cases?guild=1&reason=missing'));self.assertIn('No matching cases',response.text)
 async def test_queue_contains_only_server_reports_and_appeals(self):
  response=await self.dashboard.staff_queue(self.request('/staff/queue?guild=1'));self.assertIn('REPORT_PRIVATE',response.text);self.assertIn('APPEAL_PRIVATE',response.text);self.assertNotIn('OTHER_SERVER_SECRET',response.text)
  response=await self.dashboard.staff_queue(self.request('/staff/queue?guild=1&kind=appeal'));self.assertNotIn('REPORT_PRIVATE',response.text)
 async def test_role_revocation_and_membership_failure_are_applied_immediately(self):
  await self.dashboard.staff_home(self.request('/staff?guild=1'));self.member.guild_permissions=discord.Permissions.none()
  with self.assertRaises(web.HTTPForbidden):await self.dashboard.staff_home(self.request('/staff?guild=1'))
  self.guild.fetch_member.side_effect=discord.NotFound(NS(status=404,reason='Not Found'),'Gone')
  with self.assertRaises(web.HTTPForbidden):await self.dashboard.staff_cases(self.request('/staff/cases?guild=1'))
 async def test_closed_and_missing_ticket_status(self):
  self.guild.get_channel=lambda ident:None
  self.store.put_record(1,'ticket_rating',dict(channel=31,user=40,priority='low',claimed=0),'closed')
  response=await self.dashboard.staff_tickets(self.request('/staff/tickets?guild=1'));self.assertIn('Channel missing',response.text);self.assertIn('Closed',response.text);self.assertIn('Not recorded',response.text)
 async def test_invalid_filters_are_rejected(self):
  for url in ['/staff/cases?guild=1&member=abc','/staff/cases?guild=1&page=-1','/staff/queue?guild=1&kind=privacy','/staff/tickets?guild=1&status=bad']:
   handler=self.dashboard.staff_cases if '/cases' in url else self.dashboard.staff_queue if '/queue' in url else self.dashboard.staff_tickets
   with self.subTest(url=url),self.assertRaises(web.HTTPBadRequest):await handler(self.request(url))
 async def test_disabling_module_preserves_configuration_and_embed_templates(self):
  from vivi.site.embed_writer import save
  from vivi.core.features import enabled
  self.store.set_option(1,'welcome_text','Saved welcome');ident=save(self.store,1,dict(name='Rules',title='Rules'),10)
  self.store.set_option(1,'feature:welcome',False);self.assertFalse(enabled(self.store,1,'welcome'));self.assertEqual(self.store.option(1,'welcome_text'),'Saved welcome');self.assertIsNotNone(self.store.record(ident))
 async def test_new_welcome_style_and_native_icon_assets(self):
  validate_layout(DEFAULT_LAYOUT);self.assertEqual(DEFAULT_LAYOUT['style'],'velvet');self.assertTrue(render_layout(DEFAULT_LAYOUT,'Member','Server','Welcome').startswith(b'\x89PNG'))
  self.assertEqual(tray_image().size,(64,64));self.assertEqual(tray_image(self.tmp.name).size,(64,64))
  from PIL import Image
  with Image.open(Path(__file__).resolve().parents[1]/'assets/vivi/tray/vivi.ico') as icon:self.assertIn((16,16),icon.ico.sizes());self.assertIn((256,256),icon.ico.sizes())

 async def test_queue_and_ticket_pagination_does_not_hide_later_records(self):
  for n in range(55):
   self.store.put_record(1,'report',dict(author=20,target=30,text=f'REPORT_{n}',status='pending'),f'report-{n:03}')
   self.store.put_record(1,'ticket_rating',dict(channel=100+n,user=40,priority='low',claimed=0),f'closed-{n}')
  response=await self.dashboard.staff_queue(self.request('/staff/queue?guild=1'));self.assertEqual(response.text.count('class="staff-request"'),50);self.assertIn('Next',response.text)
  response=await self.dashboard.staff_queue(self.request('/staff/queue?guild=1&page=1'));self.assertIn('Previous',response.text);self.assertNotEqual(response.text.count('class="staff-request"'),0)
  response=await self.dashboard.staff_tickets(self.request('/staff/tickets?guild=1&page=1'));self.assertIn('Closed',response.text);self.assertIn('Previous',response.text)
 async def test_staff_server_selector_hides_ordinary_member_servers(self):
  self.dashboard.api_guilds=AsyncMock(return_value={'1':dict(id='1',name='Velvet Ruins')})
  response=await self.dashboard.staff_home(self.request('/staff'));self.assertIn('Staff access verified',response.text)
  self.member.guild_permissions=discord.Permissions.none();response=await self.dashboard.staff_home(self.request('/staff'));self.assertIn('No authorized staff servers',response.text);self.assertNotIn('Staff access verified',response.text)

 async def test_cached_member_display_names_are_escaped(self):
  self.guild.get_member=lambda uid:NS(display_name='<script>NAME</script>')
  response=await self.dashboard.staff_cases(self.request('/staff/cases?guild=1'));self.assertIn('&lt;script&gt;NAME',response.text);self.assertNotIn('<script>NAME',response.text)

 async def test_ticket_age_uses_opening_not_an_unrelated_update(self):
  self.store.db.execute("UPDATE ticket_events SET action='updated',at=? WHERE guild=1 AND channel=30",(time.time()-60,));self.store.db.commit()
  response=await self.dashboard.staff_tickets(self.request('/staff/tickets?guild=1'));self.assertIn('2h',response.text)
