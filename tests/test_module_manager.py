import json
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
from vivi.dashboard import Dashboard
from vivi.storage import Store
from vivi.features import FEATURES,enabled
from vivi.module_manager import DESCRIPTIONS,group_for

class ModuleManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.guild=NS(id=1,name='Velvet Ruins',text_channels=[],roles=[],categories=[],voice_channels=[]);self.bot.get_guild=lambda gid:self.guild if gid==1 else None
        self.dashboard=Dashboard(self.bot.community);self.dashboard.sessions['sid']={'user_id':10,'token':'opaque-token','csrf':'good','expires':time.time()+3600}
        self.dashboard.api_guilds=AsyncMock(return_value={'1':{'id':'1','name':'Velvet Ruins','permissions':'8'}})
    async def asyncTearDown(self):await self.dashboard.close();await self.bot.close();self.store.close();self.tmp.cleanup()
    def request(self,url):return make_mocked_request('GET',url,headers={'Cookie':'vivi_session=sid'})
    def post(self,**values):return NS(cookies={'vivi_session':'sid'},headers={'Accept':'application/json'},post=AsyncMock(return_value={'csrf':'good','guild':'1',**values}))
    async def test_anonymous_manager_requests_discord_login_without_state_changes(self):
        response=await self.dashboard.modules(make_mocked_request('GET','/modules'))
        self.assertIn('/login?next=modules',response.text);self.assertEqual(self.store.history(1),[])
    async def test_server_selector_routes_installed_servers_to_modules(self):
        response=await self.dashboard.modules(self.request('/modules'));self.assertIn('/modules?guild=1',response.text)
    async def test_cards_cover_supported_features_and_escape_names(self):
        self.guild.name='<script>alert(1)</script>';response=await self.dashboard.modules(self.request('/modules?guild=1'))
        self.assertIn('&lt;script&gt;',response.text);self.assertNotIn('<script>alert(1)',response.text);self.assertNotIn('opaque-token',response.text)
        for feature in FEATURES:
            if feature=='faq':continue
            self.assertIn('data-feature-module="'+feature+'"',response.text);self.assertIn(feature,DESCRIPTIONS);self.assertTrue(group_for(feature))
        self.assertNotIn('data-feature-module="faq"',response.text)
    async def test_ajax_toggles_update_shared_store_and_discord_changes_sync_back(self):
        response=await self.dashboard.feature(self.post(feature='games',enabled='true'))
        payload=json.loads(response.text);self.assertTrue(payload['enabled']);self.assertTrue(enabled(self.store,1,'games'))
        user=NS(guild_permissions=discord.Permissions.all(),id=10)
        i=NS(guild_id=1,user=user,response=NS(is_done=lambda:False,send_message=AsyncMock()))
        await self.bot.tree.get_command('admin').get_command('feature').callback(i,'games',False)
        state=json.loads((await self.dashboard.module_state(self.request('/api/modules?guild=1'))).text)
        self.assertFalse(state['features']['games']);self.assertEqual(set(state),{'features','revision'})
    async def test_csrf_permissions_and_guild_scoping_remain_enforced(self):
        bad=self.post(feature='ai',enabled='true');bad.post.return_value['csrf']='bad'
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.feature(bad)
        self.dashboard.api_guilds.return_value={}
        for action in [lambda:self.dashboard.feature(self.post(feature='ai',enabled='true')),lambda:self.dashboard.module_state(self.request('/api/modules?guild=1')),lambda:self.dashboard.modules(self.request('/modules?guild=1'))]:
            with self.assertRaises(web.HTTPForbidden):await action()
        self.assertFalse(enabled(self.store,1,'ai'))
        self.dashboard.api_guilds.return_value={'1':{'id':'1','permissions':'8'}}
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.module_state(self.request('/api/modules?guild=2'))
    async def test_global_network_requires_owner_and_explicit_consent(self):
        self.bot._connection.user=NS(id=99);self.guild.owner_id=10;self.guild.me=NS(guild_permissions=discord.Permissions(ban_members=True))
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.feature(self.post(feature='global_bans',enabled='true'))
        request=self.post(feature='global_bans',enabled='true',global_consent='true');response=await self.dashboard.feature(request)
        self.assertTrue(json.loads(response.text)['enabled']);self.assertTrue(self.bot.community.global_bans.participating(self.guild))
        self.guild.owner_id=11
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.feature(self.post(feature='global_bans',enabled='true',global_consent='true'))
        state=json.loads((await self.dashboard.module_state(self.request('/api/modules?guild=1'))).text);self.assertFalse(state['features']['global_bans'])
    async def test_native_form_fallback_returns_to_modules(self):
        request=self.post(feature='welcome',enabled='false',**{'return':'modules'});request.headers={}
        with self.assertRaises(web.HTTPSeeOther) as caught:await self.dashboard.feature(request)
        self.assertEqual(caught.exception.location,'/modules?guild=1');self.assertFalse(enabled(self.store,1,'welcome'))
    async def test_module_login_return_is_fixed_not_an_open_redirect(self):
        self.dashboard.client='1568121020047429775';self.dashboard.secret='test-only'
        for next_value,expected in [('modules','/modules'),('https://evil.example','/dashboard')]:
            response=await self.dashboard.login(self.request('/login?next='+next_value))
            self.assertEqual(list(self.dashboard.states.values())[-1]['next'],expected)
            self.assertTrue(response.location.startswith('https://discord.com/'))
