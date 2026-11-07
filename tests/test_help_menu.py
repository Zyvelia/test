import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import discord
from vivi.bot import ViviBot
from vivi.server.help_menu import HelpMenu,SearchModal,open_help
from vivi.core.storage import Store

class HelpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'help.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock(return_value=[]);self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.i=NS(user=NS(id=10,guild_permissions=discord.Permissions.all()),guild_id=1,data={},response=NS(is_done=lambda:False,send_message=AsyncMock(),edit_message=AsyncMock(),send_modal=AsyncMock()),original_response=AsyncMock(return_value=NS(edit=AsyncMock())))
        self.view=HelpMenu(self.bot,10,1)
    async def asyncTearDown(self):self.view.stop();await self.bot.close();self.store.close();self.tmp.cleanup()
    def button(self,label):return next(c for c in self.view.children if isinstance(c,discord.ui.Button) and c.label==label)
    async def test_help_command_opens_private_menu(self):
        await self.bot.tree.get_command('help').callback(self.i)
        options=self.i.response.send_message.call_args.kwargs;self.assertTrue(options['ephemeral']);self.assertIsInstance(options['view'],HelpMenu)
        self.assertIn('Help menu',options['embed'].title);options['view'].stop()
    async def test_categories_include_live_new_games_and_paginate(self):
        self.view.section='games';self.view.draw(self.i);commands=self.view.rows(self.i)
        self.assertTrue(any(c.qualified_name=='idle farm' for c in commands));self.assertTrue(any(c.qualified_name=='cards blackjack' for c in commands))
        first=[f.name for f in self.view.draw(self.i).fields];self.assertEqual(len(first),10)
        await self.button('Next').callback(self.i);self.assertEqual(self.view.page,1);self.assertNotEqual(first,[f.name for f in self.i.response.edit_message.call_args.kwargs['embed'].fields])
        await self.button('Previous').callback(self.i);self.assertEqual(self.view.page,0)
    async def test_search_modal_and_command_details(self):
        self.view.draw(self.i);await self.button('Search').callback(self.i)
        modal=self.i.response.send_modal.call_args.args[0];self.assertIsInstance(modal,SearchModal);modal.query._value='blackjack';await modal.on_submit(self.i)
        self.assertEqual([c.qualified_name for c in self.view.rows(self.i)],['cards blackjack'])
        menu=next(c for c in self.view.children if isinstance(c,discord.ui.Select) and c.row==1);self.i.data={'values':['cards blackjack']};await menu.callback(self.i)
        embed=self.i.response.edit_message.call_args.kwargs['embed'];self.assertIn('/cards blackjack',embed.title);self.assertTrue(any('opponent' in f.name for f in embed.fields))
        await self.button('Back').callback(self.i);self.assertIsNone(self.view.selected)
    async def test_favorites_share_existing_profile_storage(self):
        self.view.section='games';self.view.selected='idle farm';self.view.draw(self.i);await self.button('Save favorite').callback(self.i)
        self.assertEqual(self.store.profile(1,10)['favorites'],['idle farm']);await self.button('Favorites').callback(self.i)
        self.assertEqual([c.qualified_name for c in self.view.rows(self.i)],['idle farm'])
        self.view.selected='idle farm';self.view.draw(self.i);await self.button('Remove favorite').callback(self.i);self.assertEqual(self.store.profile(1,10)['favorites'],[])
    async def test_regular_members_do_not_see_admin_and_moderation_commands(self):
        self.i.user.guild_permissions=discord.Permissions.none();names=[c.qualified_name for c in self.view.commands(self.i)]
        self.assertNotIn('admin feature',names);self.assertNotIn('ban',names);self.assertIn('idle farm',names)
        self.view.selected='admin feature';self.view.section='all';embed=self.view.draw(self.i);self.assertNotEqual(embed.title,'Vivi · /admin feature')
    async def test_owner_guild_and_closed_menu_checks(self):
        self.i.user.id=20;self.assertFalse(await self.view.interaction_check(self.i));self.i.user.id=10;self.i.guild_id=2;self.assertFalse(await self.view.interaction_check(self.i))
        self.i.guild_id=1;self.assertTrue(await self.view.interaction_check(self.i));self.view.draw(self.i);await self.button('Close').callback(self.i)
        self.assertTrue(self.view.is_finished());self.assertIsNone(self.i.response.edit_message.call_args.kwargs['view']);self.assertFalse(await self.view.interaction_check(self.i))
    async def test_dm_menu_does_not_save_server_favorites(self):
        self.i.guild_id=None;menu=HelpMenu(self.bot,10,None);menu.section='all';menu.selected='help';menu.draw(self.i)
        names=[c.qualified_name for c in menu.commands(self.i)];self.assertNotIn('idle farm',names);self.assertIn('help',names)
        self.assertFalse(any(getattr(c,'label','')=='Save favorite' for c in menu.children));menu.stop()
    async def test_limits_timeout_and_empty_results(self):
        for section in ['home','all','favorites','games','settings']:
            self.view.section=section;embed=self.view.draw(self.i);self.assertLess(len(embed),6000)
            for row in self.view.to_components():self.assertLessEqual(len(row['components']),5)
            self.assertLessEqual(len(self.view.children),25)
        self.view.section='all';self.view.query='zzzzzzzz-no-match';self.assertEqual(len(self.view.rows(self.i)),0);self.assertIn('No matches',[f.name for f in self.view.draw(self.i).fields])
        self.view.message=NS(edit=AsyncMock());await self.view.on_timeout();self.assertTrue(all(item.disabled for item in self.view.children));self.view.message.edit.assert_awaited_once()
