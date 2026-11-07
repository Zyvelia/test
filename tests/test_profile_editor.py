import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
import discord
from vivi.bot import ViviBot
from vivi.profile_editor import ProfileEditor,TextEditor,open_editor
from vivi.storage import Store

class EditorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__();self.store.set_option(1,'feature:profiles',True)
        self.i=NS(user=NS(id=10,display_name='Member',guild_permissions=discord.Permissions.none()),guild_id=1,guild=NS(id=1),data={},response=NS(defer=AsyncMock(),is_done=lambda:True,send_message=AsyncMock(),edit_message=AsyncMock()),followup=NS(send=AsyncMock(return_value=NS(edit=AsyncMock()))),edit_original_response=AsyncMock())
        self.editor=ProfileEditor(self.bot,self.i)
    async def asyncTearDown(self):self.editor.stop();await self.bot.close();self.store.close();self.tmp.cleanup()
    async def test_changes_refresh_png_without_saving_then_save_preserves_privacy(self):
        before=copy.deepcopy(self.bot.community.profiles.style(1,10));p=self.store.profile(1,10);p['card_visibility']={'coins':False};self.store.save_profile(1,10,p)
        def change(style):style['background']='rose_dusk'
        await self.editor.update(self.i,change=change)
        self.assertEqual(self.bot.community.profiles.style(1,10),before)
        self.assertEqual(self.editor.draft['background'],'rose_dusk');options=self.i.edit_original_response.call_args.kwargs;self.assertEqual(options['attachments'][0].filename,'profile-preview.png');options['attachments'][0].close()
        await self.editor.update(self.i,save=True);self.i.edit_original_response.call_args.kwargs['attachments'][0].close()
        self.assertEqual(self.bot.community.profiles.style(1,10)['background'],'rose_dusk');self.assertFalse(self.store.profile(1,10)['card_visibility']['coins'])
    async def test_revert_discards_draft_and_stale_save_does_not_overwrite(self):
        def change(style):style['layout']='compact'
        await self.editor.update(self.i,change=change);self.i.edit_original_response.call_args.kwargs['attachments'][0].close()
        p=self.store.profile(1,10);p['card_style']=dict(self.editor.baseline,font='mono');self.store.save_profile(1,10,p)
        await self.editor.update(self.i,save=True);self.assertIn('changed',self.i.followup.send.call_args.args[0]);self.assertEqual(self.bot.community.profiles.style(1,10)['font'],'mono')
        await self.editor.update(self.i,revert=True);self.i.edit_original_response.call_args.kwargs['attachments'][0].close();self.assertEqual(self.editor.draft['font'],'mono');self.assertEqual(self.editor.draft['layout'],self.editor.baseline['layout'])
    async def test_owner_guild_and_disabled_feature(self):
        self.i.user.id=20;self.assertFalse(await self.editor.interaction_check(self.i));self.i.user.id=10;self.i.guild_id=2;self.assertFalse(await self.editor.interaction_check(self.i))
        self.i.guild_id=1;self.store.set_option(1,'feature:profiles',False);await self.editor.update(self.i,save=True);self.i.edit_original_response.assert_not_awaited()
    async def test_invalid_and_blocked_status_does_not_change_draft(self):
        self.store.set_option(1,'blocked_words',['blocked']);before=copy.deepcopy(self.editor.draft)
        for text in ['blocked','x'*121]:
            def change(style):style['status']=text
            await self.editor.update(self.i,change=change);self.assertEqual(self.editor.draft,before)
    async def test_only_own_approved_banners_are_options(self):
        for ident,user,status in [('a'*32,10,'approved'),('b'*32,20,'approved'),('c'*32,10,'pending')]:self.store.put_record(1,'profile_banner',dict(user=user,status=status),ident)
        values=self.editor.options();self.assertIn('upload:'+'a'*32,values);self.assertNotIn('upload:'+'b'*32,values);self.assertNotIn('upload:'+'c'*32,values)
    async def test_controls_fit_component_limits_and_close_discards_changes(self):
        self.editor.draft['layout']='compact';self.editor.controls()
        for row in self.editor.to_components():self.assertLessEqual(len(row['components']),5)
        close=next(c for c in self.editor.children if getattr(c,'label','')=='Close without saving');await close.callback(self.i)
        self.assertTrue(self.editor.is_finished());self.assertEqual(self.bot.community.profiles.style(1,10)['layout'],self.editor.baseline['layout'])
    async def test_native_dropdown_changes_the_preview_image(self):
        await self.editor.update(self.i,initial=True);first=self.i.followup.send.call_args.kwargs['file'];before=first.fp.getvalue();first.close()
        self.i.data={'values':['rose_dusk']};await self.editor.children[1].callback(self.i)
        file=self.i.edit_original_response.call_args.kwargs['attachments'][0];after=file.fp.getvalue();file.close()
        self.assertNotEqual(before,after);self.assertEqual(self.editor.draft['background'],'rose_dusk');self.assertNotEqual(self.bot.community.profiles.style(1,10)['background'],'rose_dusk')
    async def test_sticker_limit_and_custom_gradient_use_the_existing_validators(self):
        def invalid(style):style['gradient']='not-a-gradient'
        await self.editor.update(self.i,change=invalid);self.assertNotEqual(self.editor.draft['gradient'],'not-a-gradient')
        self.editor.draft['stickers']=[dict(item='star',x=800,y=35+n*35) for n in range(6)];self.editor.property='stickers';self.editor.controls();self.i.data={'values':['heart']}
        await self.editor.children[1].callback(self.i);self.assertEqual(len(self.editor.draft['stickers']),6)
    async def test_initial_preview_is_private(self):
        await self.editor.update(self.i,initial=True);options=self.i.followup.send.call_args.kwargs;self.assertTrue(options['ephemeral']);self.assertIs(options['view'],self.editor);options['file'].close()
