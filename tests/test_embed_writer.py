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
from vivi.site import embed_writer as writer
from vivi.bot import ViviBot
from vivi.site.dashboard import Dashboard
from vivi.core.storage import Store
from vivi.site.embed_menu import EmbedMenu,DraftForm,PostView,DeleteView

class EmbedValidationTests(unittest.TestCase):
    def test_renders_all_supported_components(self):
        doc=dict(name='Rules',title='Hello',description='**Read these**',footer='Vivi',color='#ff65ad',url='https://example.com',image='https://example.com/a.png',thumbnail='https://example.com/b.png',fields=[dict(name='Respect',value='Be kind',inline=True)])
        embed=writer.render(doc);self.assertEqual(embed.fields[0].value,'Be kind');self.assertEqual(embed.image.url,doc['image']);self.assertEqual(embed.color.value,0xff65ad)
    def test_validation_rejects_invalid_and_oversized_documents(self):
        for doc in [dict(name=''),dict(name='X',title='x'*257),dict(name='X',title='Hi',color='pink'),dict(name='X',title='Hi',image='javascript:alert(1)'),dict(name='X',title='Hi',url='https://user:pass@example.com'),dict(name='X',title='Hi',fields=[dict(name='a',value='b')]*26),dict(name='X',title='Hi',fields=[dict(name='',value='b')]),dict(name='X',description='x'*4000,footer='y'*2048),dict(name='X',title='😀'*129),dict(name='X',title='Hi',fields=[dict(name='a',value='😀'*513)])]:
            with self.subTest(doc=str(doc)[:80]),self.assertRaises(ValueError):writer.validate(doc)

class EmbedWriterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.guild=NS(id=1,name='Test',text_channels=[],get_channel=lambda ident:None,fetch_member=AsyncMock(return_value=NS(guild_permissions=discord.Permissions(administrator=True))))
        self.bot.get_guild=lambda ident:self.guild if ident==1 else None;self.dashboard=Dashboard(self.bot.community)
        self.dashboard.sessions['sid']=dict(user_id=10,token='private-token',csrf='good',expires=time.time()+3600)
        self.dashboard.api_guilds=AsyncMock(return_value={'1':dict(id='1',name='Test',permissions='8')})
        self.doc=dict(name='Rules',title='Rules',description='Be kind',color='#ff65ad',fields=[])
    async def asyncTearDown(self):await self.dashboard.close();await self.bot.close();self.store.close();self.tmp.cleanup()
    def request(self,url):return make_mocked_request('GET',url,headers={'Cookie':'vivi_session=sid'})
    def post(self,**extra):return NS(cookies={'vivi_session':'sid'},headers={},post=AsyncMock(return_value=dict(csrf='good',guild='1',action='save',**{k:v for k,v in self.doc.items() if k!='fields'},fields='[]',**extra)))
    def interaction(self,user=10,admin=True):return NS(user=NS(id=user,guild_permissions=discord.Permissions(administrator=admin)),guild_id=1,guild=self.guild,response=NS(is_done=lambda:False,send_message=AsyncMock(),send_modal=AsyncMock(),edit_message=AsyncMock(),defer=AsyncMock()),followup=NS(send=AsyncMock()))
    async def test_named_library_scoping_edit_and_persistence(self):
        ident=writer.save(self.store,1,self.doc,10);writer.save(self.store,1,{**self.doc,'title':'Updated'},10,ident)
        self.assertEqual(writer.load(self.store,1,ident)['data']['document']['title'],'Updated')
        with self.assertRaises(ValueError):writer.load(self.store,2,ident)
        with self.assertRaises(ValueError):writer.save(self.store,2,self.doc,10,ident)
        self.assertEqual(self.store.records(2,writer.KIND),[])
        other=Store(self.store.path) if hasattr(self.store,'path') else Store(Path(self.tmp.name)/'db')
        self.assertEqual(writer.load(other,1,ident)['data']['document']['name'],'Rules');other.close()
    async def test_dashboard_saves_named_embed_and_escapes_html(self):
        with self.assertRaises(web.HTTPSeeOther) as result:await self.dashboard.embed_action(self.post())
        self.assertIn('/embeds?',result.exception.location);ident=self.store.records(1,writer.KIND)[0]['id']
        writer.save(self.store,1,{**self.doc,'title':'<script>alert(1)</script>'},10,ident)
        response=await self.dashboard.embed_editor(self.request('/embeds?guild=1&id='+ident));self.assertIn('&lt;script&gt;',response.text);self.assertNotIn('<script>alert(1)',response.text);self.assertNotIn('private-token',response.text)
    async def test_permissions_csrf_and_cross_server_ids(self):
        ident=writer.save(self.store,2,self.doc,10)
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.embed_action(self.post(id=ident))
        bad=self.post();bad.post.return_value['csrf']='bad'
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.embed_action(bad)
        self.dashboard.api_guilds.return_value={}
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.embed_editor(self.request('/embeds?guild=1'))
        with self.assertRaises(web.HTTPForbidden):await self.dashboard.embed_action(self.post())
    async def test_publish_needs_explicit_confirmation_and_deletion_keeps_other_records(self):
        post=self.post();post.post.return_value['action']='publish'
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.embed_action(post)
        self.guild.fetch_member.assert_not_awaited()
        ident=writer.save(self.store,1,self.doc,10);post=self.post(id=ident);post.post.return_value['action']='delete'
        with self.assertRaises(web.HTTPBadRequest):await self.dashboard.embed_action(post)
        post.post.return_value['delete_confirm']='yes'
        with self.assertRaises(web.HTTPSeeOther):await self.dashboard.embed_action(post)
        self.assertIsNone(self.store.record(ident))
    async def test_post_checks_fresh_admin_and_channel_permissions_and_disables_mentions(self):
        channel=MagicMock(spec=discord.TextChannel);channel.send=AsyncMock();channel.permissions_for.return_value=discord.Permissions(view_channel=True,send_messages=True,embed_links=True);self.guild.me=NS(id=99);self.guild.get_channel=lambda ident:channel
        await writer.publish(self.guild,3,self.doc,10);kwargs=channel.send.call_args.kwargs;self.assertFalse(kwargs['allowed_mentions'].everyone);self.assertFalse(kwargs['allowed_mentions'].users);self.guild.fetch_member.assert_awaited_once_with(10)
        channel.send.reset_mock();self.guild.fetch_member.return_value=NS(guild_permissions=discord.Permissions.none())
        with self.assertRaises(PermissionError):await writer.publish(self.guild,3,self.doc,10)
        channel.send.assert_not_awaited();self.guild.fetch_member.return_value=NS(guild_permissions=discord.Permissions(administrator=True));channel.permissions_for.return_value=discord.Permissions.none()
        with self.assertRaises(PermissionError):await writer.publish(self.guild,3,self.doc,10)
    async def test_discord_menu_shares_templates_and_modal_preserves_advanced_fields(self):
        ident=writer.save(self.store,1,{**self.doc,'image':'https://example.com/a.png','fields':[dict(name='A',value='B')]},10)
        i=self.interaction();view=EmbedMenu(self.store,i,ident=ident);form=DraftForm(view)
        form.inputs['title']._value='Edited';await form.on_submit(i)
        data=writer.load(self.store,1,ident)['data']['document'];self.assertEqual(data['title'],'Edited');self.assertEqual(data['fields'][0]['name'],'A');self.assertEqual(data['image'],'https://example.com/a.png')
        self.assertFalse(await view.interaction_check(self.interaction(user=11)));self.assertFalse(await view.interaction_check(self.interaction(admin=False)))
    async def test_discord_command_has_runtime_permission_check(self):
        command=self.bot.tree.get_command('embed');self.assertIsNotNone(command)
        i=self.interaction(admin=False);await command.callback(i);self.assertIn('Administrator',i.response.send_message.call_args.args[0])
    async def test_saved_template_count_and_menu_pagination(self):
        for n in range(100):writer.save(self.store,1,{**self.doc,'name':f'Rule {n}'},10)
        with self.assertRaises(ValueError):writer.save(self.store,1,self.doc,10)
        view=EmbedMenu(self.store,self.interaction(),page=4);self.assertEqual(len(view.children[0].options),20)
