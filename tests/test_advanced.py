from contextlib import closing
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock,patch
import zipfile

import discord
from aiohttp import web
from aiohttp.test_utils import TestServer,TestClient
from cryptography.exceptions import InvalidTag
from vivi.backup import generate_key,create,restore,encrypt_file,key_bytes
from vivi.bot import ViviBot
from vivi.server.customization import validate_brand,validate_xp,accepts,filters_for,UI_BRAND
from vivi.site.dashboard import Dashboard
from vivi.core.features import award_activity
from vivi.server.operations import subscription
from vivi.core.storage import Store
from vivi.server.webhooks import signing_secret

class PolicyTests(unittest.TestCase):
 def test_xp_channel_amount_and_cooldown_keep_antispam(self):
  p=dict(last_xp=0,last_hash='',xp=0,coins=0,achievements=[])
  self.assertTrue(award_activity(p,'First message',100,amount=25,cooldown=120,channel=1))
  self.assertFalse(award_activity(p,'Second message',170,amount=25,cooldown=120,channel=1))
  self.assertFalse(award_activity(p,'Channel hopping',110,amount=25,cooldown=30,channel=2))
  self.assertTrue(award_activity(p,'Channel hopping',170,amount=5,cooldown=30,channel=2))
  self.assertEqual(p['xp'],30)
  self.assertFalse(award_activity(p,'No rewards',500,amount=0,cooldown=30,channel=3))
 def test_xp_override_validation(self):
  validate_xp({'123':dict(enabled=False,amount=10,cooldown=60)})
  for value in [{'123':dict(enabled=True,amount=10,cooldown=0)},{'x':dict(enabled=True,amount=10,cooldown=60)}]:
   with self.assertRaises(ValueError):validate_xp(value)
 def test_branding_prevents_css_injection(self):
  validate_brand(dict(name='<My server>',theme='velvet',accent='#123456',tagline='Hello'))
  for value in [dict(theme='unknown'),dict(accent='#123456;display:none'),dict(name='x'*41)]:
   with self.assertRaises(ValueError):validate_brand(value)
 def test_provider_filters_and_unsupported_metadata(self):
  data=subscription('github_releases','owner/repo',1,dict(tags=['v2.*'],categories=['release']))
  self.assertTrue(accepts(data,dict(tag='v2.1',category='release')))
  self.assertFalse(accepts(data,dict(tag='v1.9',category='release')))
  self.assertFalse(accepts(data,dict(tag='v2.1',category='prerelease')))
  self.assertTrue(accepts(subscription('twitch','person',1,dict(categories=['Just Chat*'])),dict(category='Just Chatting')))
  with self.assertRaises(ValueError):filters_for('youtube',dict(categories=['Gaming']))
  with self.assertRaises(ValueError):filters_for('github_commits',dict(branch='main',tags=['v*']))
 def test_branch_filter_is_exact(self):
  data=subscription('github_commits','owner/repo',1,dict(branch='main'))
  self.assertTrue(accepts(data,dict(branch='main')));self.assertFalse(accepts(data,dict(branch='other')))

class EncryptionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'project';(self.root/'data/transcripts').mkdir(parents=True)
  self.store=Store(self.root/'data/vivi.sqlite3');self.store.configure(1,2,3,4,5)
  self.store.warn(1,7,8,'Persisted warning');self.store.save_profile(1,7,dict(self.store.profile(1,7),coins=120))
  (self.root/'data/transcripts/one.txt').write_text('A private sample transcript')
  (self.root/'.env').write_text('DISCORD_TOKEN=example-not-a-real-token')
  (self.root/'data/.env').write_text('EXAMPLE=not-a-real-secret')
  (self.root/'data/audio').mkdir();(self.root/'data/audio/cache.wav').write_bytes(b'ephemeral')
  self.key=generate_key(self.base/'keys/key.bin')
 def tearDown(self):self.store.close();self.tmp.cleanup()
 def test_full_backup_round_trip_and_exclusions(self):
  path=create(self.root,self.store.path,self.key)
  self.assertNotIn(b'private sample',path.read_bytes())
  destination=restore(path,self.key,self.base/'restored',self.root)
  self.assertEqual((destination/'data/transcripts/one.txt').read_text(),'A private sample transcript')
  with closing(sqlite3.connect(destination/'data/vivi.sqlite3')) as db:
   self.assertEqual(db.execute('SELECT COUNT(*) FROM warnings').fetchone()[0],1)
   self.assertEqual(json.loads(db.execute('SELECT data FROM profiles').fetchone()[0])['coins'],120)
  self.assertFalse((destination/'data/.env').exists());self.assertFalse((destination/'data/audio').exists())
  self.assertFalse((destination/'.env').exists());self.assertFalse((destination/'data/encrypted-backups').exists())
 def test_wrong_key_or_tampering_does_not_restore_partial_data(self):
  path=create(self.root,self.store.path,self.key);wrong=generate_key(self.base/'keys/wrong.bin')
  with self.assertRaises(InvalidTag):restore(path,wrong,self.base/'wrong',self.root)
  self.assertFalse((self.base/'wrong').exists())
  body=bytearray(path.read_bytes());body[len(body)//2]^=1;path.write_bytes(body)
  with self.assertRaises(InvalidTag):restore(path,self.key,self.base/'tampered',self.root)
  self.assertFalse((self.base/'tampered').exists())
 def test_restore_refuses_live_or_nonempty_directories_and_in_repo_keys(self):
  path=create(self.root,self.store.path,self.key)
  with self.assertRaises(ValueError):restore(path,self.key,self.root/'data',self.root)
  target=self.base/'occupied';target.mkdir();(target/'keep.txt').write_text('Keep')
  with self.assertRaises(ValueError):restore(path,self.key,target,self.root)
  self.assertEqual((target/'keep.txt').read_text(),'Keep')
  inside=self.root/'bad.key';inside.write_bytes(self.key.read_bytes())
  with self.assertRaises(ValueError):key_bytes(inside,self.root)
 def test_authenticated_but_unsafe_archive_paths_are_rejected(self):
  raw=self.base/'bad.zip';name='data/../../outside.txt'
  with zipfile.ZipFile(raw,'w') as z:
   z.writestr(name,b'bad');z.writestr('manifest.json',json.dumps(dict(version=1,database=name,files={name:dict(size=3,sha256=hashlib.sha256(b'bad').hexdigest())})))
  encrypted=self.base/'bad.vbackup';encrypt_file(raw,encrypted,self.key.read_bytes())
  with self.assertRaises(ValueError):restore(encrypted,self.key,self.base/'bad-target',self.root)
  self.assertFalse((self.base/'outside.txt').exists())
 def test_creation_rejects_data_larger_than_supported_restore_limit(self):
  with patch('vivi.backup.LIMIT',1):
   with self.assertRaises(ValueError):create(self.root,self.store.path,self.key)
  self.assertEqual(list((self.root/'data/encrypted-backups').glob('*.vbackup')),[])
 def test_backup_format_requires_256_bit_keys(self):
  raw=self.base/'plain';raw.write_bytes(b'Example')
  with self.assertRaises(ValueError):encrypt_file(raw,self.base/'bad-key.vbackup',b'x'*16)
  self.assertFalse((self.base/'bad-key.vbackup').exists())
 def test_key_generation_never_overwrites(self):
  before=self.key.read_bytes()
  with self.assertRaises(FileExistsError):generate_key(self.key)
  self.assertEqual(self.key.read_bytes(),before)

class AsyncTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
  self.bot._connection.user=NS(id=99);self.service=self.bot.community;self.hooks=self.service.webhooks
  self.channel=NS(send=AsyncMock());self.guild=NS(id=1,name='Server',me=NS(id=99),get_channel=lambda ident:self.channel,
      text_channels=[],channels=[],categories=[],voice_channels=[],roles=[],get_member=lambda ident:None,voice_client=None)
  self.bot.get_guild=lambda gid:self.guild if gid==1 else None
  for feature in ['notifications','instant_webhooks']:self.store.set_option(1,'feature:'+feature,True)
  self.store.put_record(1,'notification',subscription('github_commits','owner/repo',20),'watch')
  self.env=patch.dict(os.environ,{'WEBHOOK_SECRET':'example-master-not-a-real-secret-123456'});self.env.start()
 async def asyncTearDown(self):self.env.stop();await self.bot.close();self.store.close();self.tmp.cleanup()
 def body(self,branch='main'):
  return dict(repository=dict(full_name='owner/repo'),ref='refs/heads/'+branch,after='a'*40,head_commit=dict(message='A new update'))
 def request(self,body,watch='watch',signature=True,event='push'):
  raw=json.dumps(body).encode();secret=signing_secret(os.environ['WEBHOOK_SECRET'],watch)
  digest='sha256='+hmac.new(secret,raw,hashlib.sha256).hexdigest() if signature else 'sha256='+'0'*64
  return NS(match_info={'watch':watch},read=AsyncMock(return_value=raw),headers={'X-Hub-Signature-256':digest,'X-GitHub-Event':event})
 async def test_xp_excluded_channel_does_not_award_or_create_profile(self):
  self.store.set_option(1,'feature:xp',True)
  self.store.set_option(1,'xp_channels',{'20':dict(enabled=False,amount=25,cooldown=60)})
  author=MagicMock(spec=discord.Member);author.id=7;author.bot=False
  message=NS(guild=self.guild,author=author,channel=NS(id=20),content='A normal chat message')
  await self.service.on_message(message)
  self.assertEqual(self.store.profiles(1),[])
 async def test_thread_inherits_parent_xp_rule(self):
  self.store.set_option(1,'feature:xp',True)
  self.store.set_option(1,'xp_channels',{'20':dict(enabled=True,amount=25,cooldown=60)})
  author=MagicMock(spec=discord.Member);author.id=7;author.bot=False
  thread=MagicMock(spec=discord.Thread);thread.id=21;thread.parent_id=20
  await self.service.on_message(NS(guild=self.guild,author=author,channel=thread,content='A new message in a thread'))
  self.assertEqual(self.store.profile(1,7)['xp'],25)
 async def test_branch_filter_is_used_in_github_api_request(self):
  response=AsyncMock();response.status=200;response.json.return_value=[dict(sha='abc',commit=dict(message='Update'),html_url='https://github.com/owner/repo/commit/abc')]
  cm=MagicMock();cm.__aenter__=AsyncMock(return_value=response);cm.__aexit__=AsyncMock()
  self.service.session=NS(get=MagicMock(return_value=cm),close=AsyncMock())
  data=subscription('github_commits','owner/repo',20,dict(branch='release/v2'))
  events=await self.service.operations.events(data,1)
  self.assertIn('sha=release%2Fv2',self.service.session.get.call_args.args[0]);self.assertEqual(events[0]['branch'],'release/v2')
 async def test_signed_delivery_is_queued_and_deduplicated(self):
  response=await self.hooks.receive(self.request(self.body()));self.assertEqual(response.status,202)
  await self.hooks.process();self.channel.send.assert_awaited_once()
  self.assertEqual(len(self.store.records(kind='webhook_job')),0)
  response=await self.hooks.receive(self.request(self.body()));self.assertIn('duplicate',response.text)
  await self.hooks.process();self.channel.send.assert_awaited_once()
  self.assertFalse(self.channel.send.call_args.kwargs['allowed_mentions'].everyone)
 async def test_bad_signature_wrong_source_and_cross_watch_keys_are_rejected(self):
  with self.assertRaises(web.HTTPUnauthorized):await self.hooks.receive(self.request(self.body(),signature=False))
  other=self.body();other['repository']['full_name']='another/repo'
  with self.assertRaises(web.HTTPBadRequest):await self.hooks.receive(self.request(other))
  self.store.put_record(1,'notification',subscription('github_commits','owner/repo',20),'other')
  request=self.request(self.body());request.match_info={'watch':'other'}
  with self.assertRaises(web.HTTPUnauthorized):await self.hooks.receive(request)
  self.assertEqual(self.store.records(kind='webhook_job'),[])
 async def test_filters_and_disabled_switch_prevent_delivery(self):
  watch=self.store.record('watch');watch['data']['filters']=filters_for('github_commits',dict(branch='release'));self.store.put_record(1,'notification',watch['data'],'watch')
  response=await self.hooks.receive(self.request(self.body()));self.assertIn('ignored',response.text)
  self.assertEqual(self.store.records(kind='webhook_job'),[])
  self.store.set_option(1,'feature:instant_webhooks',False)
  with self.assertRaises(web.HTTPForbidden):await self.hooks.receive(self.request(self.body('release')))
 async def test_failed_delivery_retries_without_storing_secret_error_text(self):
  await self.hooks.receive(self.request(self.body()));self.channel.send.side_effect=RuntimeError('example-sensitive-error')
  await self.hooks.process();job=self.store.records(kind='webhook_job')[0]
  self.assertEqual(job['data']['attempts'],1);self.assertEqual(job['data']['error'],'RuntimeError')
  self.assertNotIn('example-sensitive',json.dumps(job['data']))
 async def test_deleted_subscription_cannot_deliver_queued_event(self):
  await self.hooks.receive(self.request(self.body()));self.store.delete_record('watch')
  await self.hooks.process();self.channel.send.assert_not_awaited();self.assertEqual(self.store.records(kind='webhook_job'),[])
 async def test_generic_hook_and_replay_after_restart(self):
  self.store.put_record(1,'notification',subscription('webhook','builds',20),'custom')
  body=dict(id='job-1',title='Build complete',url='https://example.com/build',tag='v1',category='success')
  request=self.request(body,watch='custom',event='custom');request.headers['X-Vivi-Signature']=request.headers.pop('X-Hub-Signature-256')
  await self.hooks.receive(request);await self.hooks.process()
  from vivi.server.webhooks import Webhooks
  restarted=Webhooks(self.service)
  response=await restarted.receive(self.request(body,watch='custom',event='custom'))
  self.assertIn('duplicate',response.text);self.channel.send.assert_awaited_once()
 async def test_receiver_real_http_rejects_unsigned_payload(self):
  client=TestClient(TestServer(self.hooks.app))
  try:
   await client.start_server();response=await client.post('/hooks/watch',json=self.body())
   self.assertEqual(response.status,401)
  finally:await client.close()
 async def test_branding_is_escaped_and_theme_css_is_validated(self):
  d=Dashboard(self.service)
  token=UI_BRAND.set(dict(name='<script>brand</script>',theme='velvet',accent='#123456',tagline='<img>'))
  try:
   response=d.page('<p>Content</p>');self.assertIn('&lt;script&gt;',response.text);self.assertNotIn('<script>',response.text)
   self.assertIn('background:#180f22',response.text);self.assertIn('#123456',response.text)
  finally:UI_BRAND.reset(token)
 async def test_filter_changes_are_audited_and_backed_up(self):
  row=self.store.record('watch');row['data']['filters']=filters_for('github_commits',dict(branch='main'))
  self.store.put_record(1,'notification',row['data'],'watch')
  exported=self.store.export_config(1);self.assertEqual(exported['subscriptions'][0]['filters']['branch'],'main')
  self.assertIn('notification',self.store.history(1)[0]['action'])

if __name__=='__main__':unittest.main()
