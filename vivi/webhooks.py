"""Optional signed incoming GitHub/custom notifications, separate from the dashboard."""
import argparse
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote,urlsplit

from aiohttp import web
import discord
from .customization import accepts
from .features import enabled

def signing_secret(master,watch):
 return hmac.new(master.encode(),('vivi:'+watch).encode(),hashlib.sha256).hexdigest().encode()

class Webhooks:
 def __init__(self,service):
  self.service=service;self.bot=service.bot;self.store=service.store;self.runner=None;self.task=None;self.signal=asyncio.Event();self.cleaned=0
  self.app=web.Application(client_max_size=262144)
  self.app.add_routes([web.post('/hooks/{watch}',self.receive)])
  self.store.db.execute('CREATE TABLE IF NOT EXISTS webhook_receipts(watch TEXT,digest TEXT,at REAL,PRIMARY KEY(watch,digest))')
  self.store.db.execute('CREATE INDEX IF NOT EXISTS webhook_receipt_time ON webhook_receipts(at)');self.store.db.commit()

 def event(self,watch,body,kind):
  data=watch['data'];provider=data['provider']
  if provider.startswith('github_'):
   if str(body.get('repository',{}).get('full_name','')).lower()!=data['source'].lower():raise ValueError('Repository mismatch.')
   if kind=='ping':return None
   if provider=='github_releases' and kind=='release' and body.get('action')=='published':
    release=body['release'];tag=str(release['tag_name'])
    return dict(id=str(release['id']),title=str(release.get('name') or tag)[:300],tag=tag,
                category='prerelease' if release.get('prerelease') else 'release',url=f'https://github.com/{data["source"]}/releases/tag/{quote(tag,safe="")}')
   if provider=='github_commits' and kind=='push' and not body.get('deleted'):
    sha=str(body['after']);ref=str(body['ref'])
    if not re.fullmatch(r'[a-fA-F0-9]{40,64}',sha):raise ValueError('Invalid commit ID.')
    branch=ref.removeprefix('refs/heads/') if ref.startswith('refs/heads/') else ''
    tag=ref.removeprefix('refs/tags/') if ref.startswith('refs/tags/') else ''
    if not branch and not tag:return None
    title=str((body.get('head_commit') or {}).get('message') or f'Push to {ref}').split('\n')[0][:300]
    return dict(id=f'tag:{tag}:{sha}' if tag else sha,title=title,branch=branch,tag=tag,url=f'https://github.com/{data["source"]}/commit/{sha}')
   return None
  if provider=='webhook':
   if set(body)-{'id','title','url','tag','category'}:raise ValueError('Unknown custom fields.')
   if any(not isinstance(body.get(k),str) or not 1<=len(body[k])<=n for k,n in [('id',200),('title',300),('url',1000)]):raise ValueError('Invalid custom event.')
   url=urlsplit(body['url'])
   if url.scheme!='https' or not url.hostname or url.username is not None:raise ValueError('Custom URLs must use HTTPS without user info.')
   for key in ['tag','category']:
    if not isinstance(body.get(key,''),str) or len(body.get(key,''))>100:raise ValueError('Invalid custom filter metadata.')
   return {key:body.get(key,'') for key in ['id','title','url','tag','category']}
  raise ValueError('Instant delivery currently supports GitHub and custom watches.')

 async def receive(self,request):
  watch=self.store.record(request.match_info['watch'])
  if not watch or watch['kind']!='notification':raise web.HTTPNotFound()
  gid=watch['guild']
  if not enabled(self.store,gid,'instant_webhooks') or not enabled(self.store,gid,'notifications'):raise web.HTTPForbidden(text='Incoming notifications are disabled.')
  secret=os.getenv('WEBHOOK_SECRET','').encode()
  if len(secret)<32:raise web.HTTPServiceUnavailable(text='Webhook signing is not configured.')
  raw=await request.read();signature=request.headers.get('X-Hub-Signature-256',request.headers.get('X-Vivi-Signature',''))
  expected='sha256='+hmac.new(signing_secret(secret.decode(),watch['id']),raw,hashlib.sha256).hexdigest()
  if not re.fullmatch(r'sha256=[0-9a-f]{64}',signature) or not hmac.compare_digest(expected,signature):raise web.HTTPUnauthorized(text='Invalid signature.')
  digest=hashlib.sha256(raw).hexdigest();ident=f'hook:{watch["id"]}:{digest}'
  if self.store.record(ident) or self.store.db.execute('SELECT 1 FROM webhook_receipts WHERE watch=? AND digest=?',(watch['id'],digest)).fetchone():return web.json_response({'status':'duplicate'})
  try:
   body=json.loads(raw)
   if not isinstance(body,dict):raise ValueError('Expected object.')
   event=self.event(watch,body,request.headers.get('X-GitHub-Event','custom'))
  except (ValueError,KeyError,TypeError) as error:raise web.HTTPBadRequest(text='Event does not match this source or supported schema.')
  if not event or not accepts(watch['data'],event):return web.json_response({'status':'ignored'})
  if len(self.store.records(kind='webhook_job'))>=100:raise web.HTTPServiceUnavailable(text='Delivery queue is full; retry later.')
  self.store.put_record(gid,'webhook_job',dict(watch=watch['id'],digest=digest,event=event,attempts=0,next_attempt=0),ident)
  self.signal.set();return web.json_response({'status':'queued'},status=202)

 async def process(self):
  for job in self.store.records(kind='webhook_job'):
   data=job['data']
   if data['attempts']>=8 or data['next_attempt']>time.time():continue
   watch=self.store.record(data['watch']);guild=self.bot.get_guild(job['guild'])
   if not watch or not guild or not enabled(self.store,job['guild'],'instant_webhooks') or not enabled(self.store,job['guild'],'notifications'):
    self.store.delete_record(job['id']);continue
   if not accepts(watch['data'],data['event']):self.store.delete_record(job['id']);continue
   try:
    channel=guild.get_channel(watch['data']['channel'])
    if not channel:raise ValueError('Destination missing.')
    event=data['event']
    if watch['data'].get('last')!=event['id']:
     await channel.send(f'**{watch["data"]["provider"]}: {watch["data"]["source"]}**\n{discord.utils.escape_markdown(event["title"])}\n{event["url"]}',allowed_mentions=discord.AllowedMentions.none())
    current=self.store.record(watch['id'])
    if current:
     current['data'].update(last=event['id'],initialized=True)
     self.store.put_record(job['guild'],'notification',current['data'],watch['id'])
    with self.store.db:
     self.store.db.execute('INSERT OR IGNORE INTO webhook_receipts VALUES (?,?,?)',(watch['id'],data['digest'],time.time()))
     self.store.db.execute('DELETE FROM records WHERE id=?',(job['id'],))
   except Exception as error:
    data.update(attempts=data['attempts']+1,next_attempt=time.time()+min(600,10*2**data['attempts']),error=type(error).__name__)
    if self.store.record(job['id']):self.store.put_record(job['guild'],'webhook_job',data,job['id'])
    self.service.productivity.error('webhook delivery',error)
  if time.time()-self.cleaned>3600:
   with self.store.db:
    self.store.db.execute('DELETE FROM webhook_receipts WHERE at<?',(time.time()-30*86400,))
    self.store.db.execute('DELETE FROM webhook_receipts WHERE rowid NOT IN (SELECT rowid FROM webhook_receipts ORDER BY at DESC LIMIT 100000)')
   self.cleaned=time.time()

 async def run(self):
  await self.bot.wait_until_ready()
  while not self.bot.is_closed():
   self.signal.clear()
   try:await self.process()
   except Exception as error:self.service.productivity.error('webhook worker',error)
   try:await asyncio.wait_for(self.signal.wait(),timeout=1)
   except asyncio.TimeoutError:pass

 async def start(self):
  if os.getenv('WEBHOOK_ENABLED','').lower()!='true':return
  if len(os.getenv('WEBHOOK_SECRET','').encode())<32:raise ValueError('Set a webhook secret of at least 32 bytes.')
  host=os.getenv('WEBHOOK_BIND_HOST','127.0.0.1')
  if host not in {'127.0.0.1','localhost'} and not(host=='0.0.0.0' and os.getenv('VIVI_CONTAINER')=='1'):raise ValueError('Native webhook listener must use loopback; expose only this service through your HTTPS reverse proxy.')
  self.runner=web.AppRunner(self.app,access_log=None);await self.runner.setup()
  await web.TCPSite(self.runner,host,int(os.getenv('WEBHOOK_PORT','8766'))).start()
  self.task=asyncio.create_task(self.run(),name='vivi-webhooks')

 async def close(self):
  if self.task:
   self.task.cancel()
   with contextlib.suppress(asyncio.CancelledError):await self.task
  if self.runner:await self.runner.cleanup()


def main():
 from dotenv import load_dotenv
 from .bot import ROOT
 from .storage import Store,database_path
 load_dotenv(ROOT/'.env')
 parser=argparse.ArgumentParser(description='Export a per-watch signing secret to a private file; never prints key material.')
 parser.add_argument('watch');parser.add_argument('--output',required=True);args=parser.parse_args()
 output=Path(args.output).expanduser().resolve()
 master=os.getenv('WEBHOOK_SECRET','')
 if len(master.encode())<32:raise SystemExit('Configure WEBHOOK_SECRET with at least 32 bytes in the private .env first.')
 if output.is_relative_to(ROOT.resolve()):raise SystemExit('Export secrets outside the checkout.')
 db=database_path(ROOT)
 if not db.exists():raise SystemExit('Run/configure Vivi and create the subscription first.')
 store=Store(db)
 try:
  watch=store.record(args.watch)
  if not watch or watch['kind']!='notification':raise SystemExit('Subscription not found.')
  output.parent.mkdir(parents=True,exist_ok=True)
  fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as handle:handle.write(signing_secret(master,args.watch))
  print('Per-watch signing secret exported privately to:',output)
 finally:store.close()

if __name__=='__main__':main()
