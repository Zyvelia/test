"""Exercise the SDK's real translated registration payload, without uploading to Discord."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
import discord
from discord import app_commands
from discord.app_commands.commands import validate_name
from vivi.bot import ViviBot,StartupConfigurationError
from vivi.core.i18n import ViviTranslator,NAME_TRANSLATIONS,tr
from vivi.core.storage import Store

class NameTranslationTests(unittest.IsolatedAsyncioTestCase):
 async def test_timezone_names_are_identifiers_for_every_spanish_and_french_locale(self):
  translator=ViviTranslator();context=NS(location=app_commands.TranslationContextLocation.command_name)
  for locale in discord.Locale:
   language=locale.value.split('-')[0]
   if language not in {'es','fr'}:continue
   name=await translator.translate(app_commands.locale_str('timezone'),locale,context)
   self.assertEqual(name,'zona_horaria' if language=='es' else 'fuseau_horaire');self.assertEqual(validate_name(name),name)
  self.assertEqual(tr('es','timezone'),'zona horaria');self.assertEqual(tr('fr','timezone'),'fuseau horaire')
 async def test_ui_labels_are_not_reused_for_command_group_or_parameter_names(self):
  translator=ViviTranslator()
  for location in [app_commands.TranslationContextLocation.command_name,app_commands.TranslationContextLocation.group_name,app_commands.TranslationContextLocation.parameter_name]:
   value=await translator.translate(app_commands.locale_str('welcome text'),discord.Locale.french,NS(location=location));self.assertIsNone(value)
 async def test_invalid_explicit_translation_falls_back_instead_of_uploading(self):
  translator=ViviTranslator();context=NS(location=app_commands.TranslationContextLocation.command_name)
  for invalid in ['two words','Uppercase','bad:name','x'*33,'']:
   with patch.dict(NAME_TRANSLATIONS,{'timezone':(invalid,invalid)}):self.assertIsNone(await translator.translate(app_commands.locale_str('timezone'),discord.Locale.french,context))
 async def test_description_and_choice_labels_can_still_use_spaces(self):
  for location in [app_commands.TranslationContextLocation.command_description,app_commands.TranslationContextLocation.choice_name]:
   result=await ViviTranslator().translate(app_commands.locale_str('timezone'),discord.Locale.french,NS(location=location));self.assertEqual(result,'fuseau horaire')

class RegistrationPayloadTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'vivi.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
 async def asyncTearDown(self):await self.bot.close();self.store.close();self.tmp.cleanup()
 async def test_every_actual_command_group_and_parameter_translation_is_discord_valid(self):
  self.bot.sync_application_commands=AsyncMock(return_value=[]);self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock()
  await self.bot.setup_hook();translator=ViviTranslator()
  payloads=[await command.get_translated_payload(self.bot.tree,translator) for command in self.bot.tree.get_commands()]
  locales={locale.value for locale in discord.Locale};checked=[]
  def walk(nodes,path=''):
   for locale in locales:
    names=[node.get('name_localizations',{}).get(locale,node['name']) for node in nodes]
    self.assertEqual(len(names),len(set(names)),f'Duplicate siblings at {path} in {locale}')
   for node in nodes:
    full=path+'/'+node['name'];validate_name(node['name'])
    for locale,name in node.get('name_localizations',{}).items():
     with self.subTest(command=full,locale=locale):self.assertEqual(validate_name(name),name)
     checked.append((full,locale))
    for locale,description in node.get('description_localizations',{}).items():self.assertTrue(1<=len(description)<=100,(full,locale))
    walk(node.get('options',[]),full)
  walk(payloads)
  for path in ['/tools/timezone','/social/timezone']:
   self.assertTrue(any(name==path and locale=='fr' for name,locale in checked))
   self.assertTrue(any(name==path and locale=='es-ES' for name,locale in checked))
  self.assertGreater(len(checked),30)
 async def test_invalid_discord_payload_is_a_non_retryable_setup_error(self):
  original=discord.HTTPException(NS(status=400,reason='Bad Request'),dict(code=50035,message='Invalid Form Body'))
  self.bot.tree.sync=AsyncMock(side_effect=app_commands.CommandSyncFailure(original,[]))
  with self.assertRaises(StartupConfigurationError) as caught:await self.bot.sync_application_commands()
  self.assertIn('50035',str(caught.exception));self.assertIn('Update Vivi',str(caught.exception));self.assertEqual(self.bot.tree.sync.await_count,1)
