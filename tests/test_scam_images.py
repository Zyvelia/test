import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock,patch
import discord
from PIL import Image,ImageDraw
from vivi.scam_images import ScamImages,fingerprint,compare,MAX_BYTES,actions
from vivi.features import validate_option
from vivi.storage import Store

def picture(color='white',format='PNG',size=(160,120),**kwargs):
    image=Image.new('RGB',size,color);draw=ImageDraw.Draw(image);draw.rectangle((size[0]//5,10,size[0]//2,size[1]-10),fill='black');draw.line((0,0,*size),fill='red',width=6)
    body=io.BytesIO();image.save(body,format,**kwargs);return body.getvalue()
def attachment(body):return NS(size=len(body),filename='image.png',content_type='image/png',read=AsyncMock(return_value=body))

class HashRules(unittest.TestCase):
    def test_hashes_match_identical_pixels_with_different_encoding(self):
        a=fingerprint(picture(compress_level=0));b=fingerprint(picture(compress_level=9))
        self.assertNotEqual(a['sha256'],b['sha256']);self.assertEqual(a['pixels'],b['pixels']);self.assertEqual(compare(a,b),'exact pixels')
    def test_similarity_is_opt_in_and_low_detail_images_do_not_match(self):
        a=fingerprint(picture());b=dict(a,sha256='different',pixels='different',dhash=f"{int(a['dhash'],16)^3:016x}")
        self.assertIsNone(compare(a,b));self.assertIsNotNone(compare(a,b,2));self.assertIsNone(compare(a,b,1))
        a['contrast']=0;self.assertIsNone(compare(a,b,4))
        with self.assertRaises(ValueError):validate_option('scam_image_distance',5)
        with self.assertRaises(ValueError):validate_option('scam_image_distance',-1)
    def test_invalid_oversized_animated_and_unsupported_images_rejected(self):
        with self.assertRaises(ValueError):fingerprint(b'x'*(MAX_BYTES+1))
        with self.assertRaises(OSError):fingerprint(b'not an image')
        image=Image.new('RGB',(10,10),'red');body=io.BytesIO();image.save(body,'GIF')
        with self.assertRaises(ValueError):fingerprint(body.getvalue())
        body=io.BytesIO();image.save(body,'PNG',save_all=True,append_images=[Image.new('RGB',(10,10),'blue')])
        with self.assertRaises(ValueError):fingerprint(body.getvalue())

class ImageModeration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.store.set_option(1,'feature:scam_images',True)
        self.service=NS(store=self.store,bot=NS(user=NS(id=99)),case=AsyncMock(),productivity=NS(error=MagicMock()))
        self.scanner=ScamImages(self.service);self.body=picture();self.ident,_,_=await self.scanner.add(1,7,attachment(self.body),'Known sample')
    async def asyncTearDown(self):self.store.close();self.tmp.cleanup()
    def message(self,body=None,guild=1,ident=50):return NS(id=ident,guild=NS(id=guild),channel=NS(id=20),author=NS(id=10,guild_permissions=discord.Permissions.none()),attachments=[attachment(self.body if body is None else body)],delete=AsyncMock())
    async def test_reference_deduplication_guild_scope_and_no_original_file(self):
        ident,_,created=await self.scanner.add(1,7,attachment(picture(compress_level=1)),'Duplicate pixels')
        self.assertEqual(ident,self.ident);self.assertFalse(created)
        self.assertEqual(list(Path(self.tmp.name).iterdir()),[self.store.path])
        with self.assertRaises(ValueError):self.scanner.remove(2,self.ident)
        self.assertFalse(await self.scanner.inspect(self.message(guild=2)))
    async def test_exact_and_reencoded_matches_are_deleted_and_logged(self):
        for n,body in enumerate([self.body,picture(compress_level=1)]):
            message=self.message(body,ident=50+n);self.assertTrue(await self.scanner.inspect(message));message.delete.assert_awaited_once()
        self.service.case.assert_awaited_once();self.assertIn(self.ident,self.service.case.call_args.args[4])
    async def test_disabled_exempt_unknown_and_large_attachments_are_not_deleted(self):
        message=self.message(picture('blue'));self.assertFalse(await self.scanner.inspect(message));message.delete.assert_not_awaited()
        self.store.set_option(1,'feature:scam_images',False);message=self.message();self.assertFalse(await self.scanner.inspect(message));message.attachments[0].read.assert_not_awaited()
        self.store.set_option(1,'feature:scam_images',True);message.author.guild_permissions=discord.Permissions(manage_messages=True);self.assertFalse(await self.scanner.inspect(message))
        message=self.message();message.attachments[0].size=MAX_BYTES+1;self.assertFalse(await self.scanner.inspect(message));message.attachments[0].read.assert_not_awaited()
    async def test_removed_reference_cancels_pending_match(self):
        message=self.message()
        async def read():self.scanner.remove(1,self.ident);return self.body
        message.attachments[0].read.side_effect=read
        self.assertFalse(await self.scanner.inspect(message));message.delete.assert_not_awaited()
    async def test_deletion_failure_is_reported_without_claiming_success(self):
        message=self.message();message.delete.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'Missing Permissions')
        self.assertTrue(await self.scanner.inspect(message));self.service.productivity.error.assert_called_once();self.assertIn('failed',self.service.case.call_args.args[3])
    async def test_duplicate_events_do_not_repeat_deletion(self):
        message=self.message();await self.scanner.inspect(message);await self.scanner.inspect(message);message.delete.assert_awaited_once()
    async def test_invalid_image_does_not_crash_moderation(self):
        message=self.message(b'bad');self.assertFalse(await self.scanner.inspect(message));message.delete.assert_not_awaited()
    async def test_references_survive_restart(self):
        self.store.close();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.service.store=self.store;scanner=ScamImages(self.service)
        message=self.message();self.assertTrue(await scanner.inspect(message));message.delete.assert_awaited_once()
    async def test_matched_attachment_stops_xp_and_attachment_only_edits_are_checked(self):
        from vivi.community import Community
        self.store.set_option(1,'feature:xp',True);self.service.scam_images=self.scanner
        message=self.message();author=MagicMock(spec=discord.Member);author.id=10;author.bot=False;author.guild_permissions=discord.Permissions.none();message.author=author
        await Community.on_message(self.service,message);message.delete.assert_awaited_once();self.assertEqual(self.store.profile(1,10)['xp'],0)
        listener=NS(on_message=AsyncMock());before=NS(content='same',attachments=[]);after=NS(content='same',attachments=[NS(id=123)])
        await Community.on_message_edit(listener,before,after);listener.on_message.assert_awaited_once_with(after,edited=True)
    async def test_training_actions_require_administrator(self):
        bot=NS(community=NS(scam_images=self.scanner));registered=actions(bot)
        self.assertEqual(len(registered),3)
        i=NS(user=NS(guild_permissions=discord.Permissions.none()))
        for command in registered.values():
            self.assertTrue(command.default_permissions.administrator)
            with self.assertRaises(discord.app_commands.MissingPermissions):await command.checks[0](i)
