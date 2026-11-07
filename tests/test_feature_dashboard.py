import json
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
from vivi.storage import Store
from vivi.dashboard import Dashboard
from vivi.features import FEATURES,OPTION_TYPES,validate_option
from vivi.feature_dashboard import PREFIXES
from vivi import embed_writer
from vivi.message_templates import message_embed,expand

class FeatureDashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.channel=MagicMock(spec=discord.TextChannel);self.channel.id=3;self.channel.name='welcome';self.channel.send=AsyncMock();self.channel.permissions_for.return_value=discord.Permissions.all()
        self.guild=NS(id=1,name='Velvet Ruins',member_count=123,text_channels=[self.channel],roles=[],categories=[],voice_channels=[],get_channel=lambda ident:self.channel if ident==3 else None,me=NS(id=99))
        self.bot.get_guild=lambda ident:self.guild if ident==1 else None;self.dashboard=Dashboard(self.bot.community);self.dashboard.sessions['sid']=dict(user_id=10,token='secret-token',csrf='good',expires=time.time()+3600)
        self.dashboard.api_guilds=AsyncMock(return_value={'1':dict(id='1',name='Velvet Ruins',permissions='8')})
        self.member=NS(id=20,display_name='ZyVelia',mention='<@20>',guild=self.guild)
        self.doc=dict(name='Welcome',title='Hi {username}',description='Welcome to {server}, {member}! Member {member_count}',color='#ff65ad')
    async def asyncTearDown(self):await self.dashboard.close();await self.bot.close();self.store.close();self.tmp.cleanup()
    def request(self,module):return make_mocked_request('GET','/configure?guild=1&module='+module,headers={'Cookie':'vivi_session=sid'})
    def post(self,**extra):
        data=dict(csrf='good',guild='1',kind='welcome',channel='3',mode='text',text='Hi {member} in {server}!',action='save',enabled='yes');data.update(extra)
        return NS(cookies={'vivi_session':'sid'},headers={},post=AsyncMock(return_value=data))
    async def test_every_active_module_has_a_configure_page(self):
        for feature in FEATURES:
            if feature=='faq':continue
            response=await self.dashboard.configure_module(self.request(feature));self.assertEqual(response.status,200);self.assertNotIn('secret-token',response.text)
    async def test_save_welcome_without_ticket_setup_and_runtime_delivery(self):
        self.assertIsNone(self.store.settings(1))
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post())
        self.bot.community.operations.on_join=AsyncMock();await self.bot.community.on_join(self.member)
        args=self.channel.send.call_args;self.assertIn('<@20>',args.args[0]);self.assertIn('Velvet Ruins',args.args[0]);self.assertEqual(self.store.option(1,'welcome_channel'),3)
    async def test_embed_snapshot_is_independent_from_deleted_library_and_runtime_uses_it(self):
        ident=embed_writer.save(self.store,1,self.doc,10)
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post(mode='embed',template=ident))
        self.store.delete_record(ident);self.bot.community.operations.on_join=AsyncMock();await self.bot.community.on_join(self.member)
        kwargs=self.channel.send.call_args.kwargs;self.assertEqual(kwargs['embed'].title,'Hi ZyVelia');self.assertIn('123',kwargs['embed'].description);self.assertFalse(kwargs['allowed_mentions'].users)
        with self.assertRaises(web.HTTPSeeOther):await self._save_goodbye()
        self.channel.send.reset_mock();await self.bot.community.on_member_remove(self.member);self.assertIsNotNone(self.channel.send.call_args.kwargs['embed'])
    async def _save_goodbye(self):
        self.store.set_option(1,'goodbye_embed',self.store.option(1,'welcome_embed'))
        await self.dashboard.save_messages(self.post(kind='goodbye',mode='embed',text='Bye'))
    async def test_goodbye_text_never_pings(self):
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post(kind='goodbye',text='Bye {username} @everyone'))
        await self.bot.community.on_member_remove(self.member);self.assertIn('ZyVelia',self.channel.send.call_args.args[0]);self.assertFalse(self.channel.send.call_args.kwargs['allowed_mentions'].everyone)
    async def test_preview_does_not_save_or_send(self):
        response=await self.dashboard.save_messages(self.post(action='preview',text='<script> {username}'));self.assertIn('&lt;script&gt;',response.text);self.assertEqual(self.store.history(1),[]);self.channel.send.assert_not_awaited()
    async def test_rejects_missing_permissions_wrong_guild_templates_and_bad_csrf(self):
        ident=embed_writer.save(self.store,2,self.doc,10)
        for request in [self.post(mode='embed',template=ident),self.post(channel='999'),self.post(mode='unknown'),self.post(mode='embed'),self.post(text='')]:
            with self.assertRaises(web.HTTPBadRequest):await self.dashboard.save_messages(request)
        self.channel.permissions_for.return_value=discord.Permissions(view_channel=True,send_messages=True)
        ident=embed_writer.save(self.store,1,self.doc,10)
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.save_messages(self.post(mode='embed',template=ident))
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.save_messages(self.post(csrf='bad'))
        self.assertEqual(self.store.history(1),[])
    async def test_failed_validation_keeps_all_settings_unchanged(self):
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post())
        before=self.store.export_config(1)
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.save_messages(self.post(channel='999',text='changed'))
        self.assertEqual(self.store.export_config(1),before)
    async def test_settings_saved_in_discord_are_visible_on_page_and_disabled_drafts_work(self):
        self.store.set_option(1,'welcome_text','Saved through shared settings')
        response=await self.dashboard.configure_module(self.request('welcome'));self.assertIn('Saved through shared settings',response.text)
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post(enabled='no',channel='0'))
        self.assertFalse(self.store.option(1,'feature:welcome'));self.assertEqual(self.store.option(1,'welcome_channel'),0)
        self.dashboard.api_guilds.return_value={}
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.configure_module(self.request('welcome'))
    async def test_embed_expansion_stays_within_discord_limits(self):
        data={**self.doc,'title':'{username}'*25,'description':'{server}'*400,'footer':'{server}'*200}
        embed=message_embed(data,self.member);self.assertLessEqual(len(embed),6000);self.assertLessEqual(len(embed.title),256)
    async def test_new_options_validate_for_configuration_backup(self):
        for key,value in [('welcome_channel',3),('welcome_mode','embed'),('goodbye_mode','text'),('welcome_embed',self.doc),('goodbye_embed',{})]:validate_option(key,value)
        with self.assertRaises(ValueError):validate_option('welcome_mode','invalid')

    async def test_setup_and_composer_channel_changes_share_the_same_channel(self):
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post())
        self.store.configure(1,4,5,6,7);self.assertEqual(self.store.option(1,'welcome_channel'),4)
        self.store.set_option(1,'welcome_channel',3);self.assertEqual(self.store.settings(1)['welcome'],3)
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.save_messages(self.post())
        self.assertEqual(self.store.settings(1)['welcome'],3)
