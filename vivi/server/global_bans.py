"""Operator-only global blocklist, explicit server-owner consent and durable ban jobs."""
import asyncio
import contextlib
import os
import json
import secrets
import time
import weakref
import discord
from vivi.core.features import enabled

DEFAULT_OPERATOR_ID=973054575076581456

def operator_id():
    value=os.getenv('GLOBAL_BAN_OPERATOR_ID','').strip() or str(DEFAULT_OPERATOR_ID)
    return int(value) if len(value)<=20 and value.isascii() and value.isdigit() and 0<int(value)<2**63 else 0

def is_operator(user):return bool(operator_id() and user.id==operator_id())
def user_id(text):
    text=str(text).strip()
    if len(text)>20 or not text.isascii() or not text.isdigit() or not 0<int(text)<2**63:raise ValueError('Enter a numeric Discord user ID, not a username or token.')
    return int(text)

class GlobalBans:
    def __init__(self,service):
        self.service=service;self.bot=service.bot;self.store=service.store;self.task=None;self.tick_lock=asyncio.Lock();self.reconciled=False;self.locks=weakref.WeakValueDictionary()
    def entry(self,target):return self.store.record(f'globalban:{target}')
    def active(self,target,generation=None):
        row=self.entry(target)
        return bool(row and row['kind']=='global_ban' and row['data'].get('active') and row['data'].get('operator')==operator_id() and (generation is None or row['data']['generation']==generation))
    def entries(self):return [r for r in self.store.records(0,'global_ban') if r['data'].get('active') and r['data'].get('operator')==operator_id()]
    def participating(self,guild):
        if not guild or not operator_id() or not enabled(self.store,guild.id,'global_bans'):return False
        row=self.store.record(f'globalconsent:{guild.id}');bot_id=getattr(getattr(self.bot,'user',None),'id',None)
        return bool(row and row['kind']=='global_ban_consent' and row['data'].get('owner')==getattr(guild,'owner_id',None) and row['data'].get('operator')==operator_id() and row['data'].get('bot')==bot_id)
    def set_participation(self,guild,actor,on,administrator=False,confirmed=False):
        if on and actor!=guild.owner_id:raise PermissionError('Only the server owner can opt in to global-ban enforcement.')
        if not on and actor!=guild.owner_id and not administrator:raise PermissionError('A server owner or Administrator must disable this feature.')
        if on and not confirmed:raise ValueError('Confirm that enabling this network may enforce existing global entries.')
        if on and not getattr(getattr(self.bot,'user',None),'id',None):raise ValueError('Wait until Vivi has logged in before opting in.')
        if on and not guild.me.guild_permissions.ban_members:raise ValueError('Grant Vivi Ban Members before opting in.')
        if on and not operator_id():raise ValueError('The host must configure a valid global-ban operator ID.')
        self.store.set_option(guild.id,'feature:global_bans',bool(on))
        if on:
            self.store.put_record(guild.id,'global_ban_consent',dict(owner=actor,operator=operator_id(),bot=self.bot.user.id,at=time.time(),acknowledged_existing=True),f'globalconsent:{guild.id}')
            for row in self.entries():self.queue(guild,row['data'],'ban',actor)
        return self.participating(guild)
    def queue(self,guild,entry,action,actor,force=False):
        ident=f'globaljob:{entry["generation"]}:{guild.id}:{action}'
        old=self.store.record(ident)
        if not force and old and old['data']['status'] in {'pending','running','success','preexisting'}:return ident
        self.store.put_record(guild.id,'global_ban_job',dict(target=entry['target'],generation=entry['generation'],action=action,actor=actor,guild_name=guild.name,status='pending',attempts=0,next=0,result='',created=time.time()),ident)
        return ident
    def add(self,target,reason,evidence,actor,guild_ids):
        if actor!=operator_id() or not actor:raise PermissionError('Only the configured operator can add global entries.')
        target=user_id(target)
        if target in {operator_id(),getattr(getattr(self.bot,'user',None),'id',None)}:raise ValueError('Vivi and its operator are protected accounts.')
        if not 10<=len(reason)<=500 or not 3<=len(evidence)<=1000:raise ValueError('Supply a reason (10–500 characters) and an evidence reference (3–1000).')
        if self.active(target):raise ValueError('This account already has an active global entry.')
        previous=self.entry(target);history=previous['data'].get('history',[]) if previous else []
        data=dict(target=target,reason=reason,evidence=evidence,operator=actor,generation=secrets.token_hex(12),active=True,created=time.time(),history=(history+[dict(action='add',actor=actor,reason=reason,at=time.time())])[-50:])
        self.store.put_record(0,'global_ban',data,f'globalban:{target}');count=0
        for ident in set(guild_ids):
            guild=self.bot.get_guild(ident)
            if self.participating(guild):self.queue(guild,data,'ban',actor);count+=1
        return count
    def remove(self,target,reason,undo,actor):
        if actor!=operator_id() or not actor:raise PermissionError('Only the configured operator can remove global entries.')
        row=self.entry(user_id(target))
        if not row or row['kind']!='global_ban':raise ValueError('No global entry exists for that user ID.')
        if not 10<=len(reason)<=500:raise ValueError('Supply a removal reason of 10–500 characters.')
        data=row['data'];data['active']=False;data['history']=(data.get('history',[])+[dict(action='remove',actor=actor,reason=reason,undo=bool(undo),at=time.time())])[-50:]
        self.store.put_record(0,'global_ban',data,row['id']);count=0
        if undo:
            # Include every guild the entry could be banning in, including in-flight requests.
            ids={r['guild'] for r in self.store.records(kind='global_ban_job') if r['data']['target']==data['target']}|{r['guild'] for r in self.store.records(kind='global_ban_ledger') if r['data']['target']==data['target']}
            for ident in ids:
                guild=self.bot.get_guild(ident)
                if guild:self.queue(guild,data,'unban',actor);count+=1
        return count
    def lock_for(self,guild,target):
        key=(guild,target);lock=self.locks.get(key)
        if lock is None:lock=asyncio.Lock();self.locks[key]=lock
        return lock
    async def ban(self,guild,data):
        target=data['target'];generation=data['generation']
        async with self.lock_for(guild.id,target):
            if not self.active(target,generation) or not self.participating(guild):return 'skipped','Entry inactive or server consent unavailable.'
            if target in {operator_id(),self.bot.user.id,guild.owner_id}:return 'skipped','Protected account or server owner.'
            if not guild.me.guild_permissions.ban_members:return 'failed','Missing Ban Members permission.'
            member=guild.get_member(target)
            if member and member.top_role>=guild.me.top_role:return 'failed','Vivi’s role is not above this member.'
            marker='Vivi global blocklist '+generation;ledger_id=f'globalledger:{guild.id}:{target}'
            try:existing=await guild.fetch_ban(discord.Object(id=target))
            except discord.NotFound:existing=None
            if existing:
                ledger=self.store.record(ledger_id)
                if existing.reason==marker or ledger and ledger['data'].get('issued') and existing.reason==ledger['data']['marker']:
                    if not ledger:self.store.put_record(guild.id,'global_ban_ledger',dict(target=target,issued=True,marker=marker,generation=generation,at=time.time()),ledger_id)
                    return 'success','Already banned by Vivi’s global system.'
                return 'preexisting','Existing server ban preserved; Vivi did not claim ownership.'
            # Consent and entry can change while waiting for Discord.
            if not self.active(target,generation) or not self.participating(guild):return 'skipped','Cancelled before applying the ban.'
            await guild.ban(discord.Object(id=target),reason=marker,delete_message_seconds=0)
            self.store.put_record(guild.id,'global_ban_ledger',dict(target=target,issued=True,marker=marker,generation=generation,at=time.time()),ledger_id)
            await self.service.case(guild,target,data['operator'],'global ban',f'Global entry {generation}: {data["reason"]}')
            return 'success','Banned by Vivi. No message history was deleted.'
    async def unban(self,guild,target):
        async with self.lock_for(guild.id,target):
            if not self.participating(guild):return 'skipped','Server consent was withdrawn; local staff must review existing bans.'
            if self.active(target):return 'skipped','An active global entry still exists.'
            ledger=self.store.record(f'globalledger:{guild.id}:{target}')
            if not ledger or not ledger['data'].get('issued'):return 'skipped','No Vivi-issued ban is recorded.'
            if not guild.me.guild_permissions.ban_members:return 'failed','Missing Ban Members permission.'
            try:current=await guild.fetch_ban(discord.Object(id=target))
            except discord.NotFound:return 'skipped','This account is not banned here.'
            if current.reason!=ledger['data']['marker']:return 'skipped','The current server ban differs; it was preserved.'
            if not guild.me.guild_permissions.view_audit_log:return 'skipped','View Audit Log is needed to verify ban ownership; server staff must review manually.'
            latest=None
            async for event in guild.audit_logs(limit=100,action=discord.AuditLogAction.ban):
                if getattr(event.target,'id',None)==target:latest=event;break
            if not latest or getattr(latest.user,'id',None)!=self.bot.user.id or latest.reason!=current.reason:return 'skipped','Latest ban ownership could not be verified; server ban preserved.'
            if self.active(target):return 'skipped','Entry was reactivated before unbanning.'
            try:verified=await guild.fetch_ban(discord.Object(id=target))
            except discord.NotFound:return 'skipped','The ban was already removed.'
            if verified.reason!=ledger['data']['marker']:return 'skipped','The server ban changed during verification; it was preserved.'
            if not self.participating(guild) or self.active(target):return 'skipped','Consent or entry state changed during verification.'
            await guild.unban(discord.Object(id=target),reason='Vivi global entry removed by its operator')
            ledger['data']['issued']=False;ledger['data']['removed']=time.time();self.store.put_record(guild.id,'global_ban_ledger',ledger['data'],ledger['id'])
            await self.service.case(guild,target,operator_id(),'global unban','Verified Vivi-issued global ban removed; independent bans are preserved.')
            return 'success','Verified Vivi-issued ban removed.'
    def retry(self,actor):
        if actor!=operator_id() or not actor:raise PermissionError('Only the operator can retry global jobs.')
        count=0
        for row in self.store.records(kind='global_ban_job'):
            data=row['data'];guild=self.bot.get_guild(row['guild'])
            if data['status'] not in {'failed','skipped'} or not self.participating(guild):continue
            if data['action']=='ban' and not self.active(data['target'],data['generation']):continue
            if data['action']=='unban' and self.active(data['target']):continue
            data.update(status='pending',attempts=0,next=0);self.store.put_record(row['guild'],'global_ban_job',data,row['id']);count+=1
        return count
    async def tick(self):
        async with self.tick_lock:
            jobs=[dict(row,data=json.loads(row['data'])) for row in self.store.db.execute("SELECT * FROM records WHERE kind='global_ban_job' AND json_extract(data,'$.status') IN ('pending','running') AND COALESCE(json_extract(data,'$.next'),0)<=? ORDER BY json_extract(data,'$.created') LIMIT 5",(time.time(),))]
            for job in jobs:
                data=job['data'];guild=self.bot.get_guild(job['guild']);data['attempts']+=1
                try:
                    if not guild:status,result='skipped','Vivi is no longer in this server.'
                    elif data['action']=='ban':
                        entry=self.entry(data['target'])
                        status,result=await self.ban(guild,entry['data']) if entry and self.active(data['target'],data['generation']) else ('skipped','Global entry was removed or replaced.')
                    else:status,result=await self.unban(guild,data['target'])
                    data.update(status=status,result=result)
                except discord.HTTPException as error:
                    retry=error.status in {429,500,502,503,504} and data['attempts']<3
                    data.update(status='pending' if retry else 'failed',result=f'Discord HTTP {error.status}, code {error.code}.',next=time.time()+30*2**data['attempts'])
                except Exception as error:
                    self.service.productivity.error('global-ban job',error);data.update(status='failed',result='Unexpected error; check the host error report.')
                data['updated']=time.time();self.store.put_record(job['guild'],'global_ban_job',data,job['id'])
    async def on_join(self,member):
        if not self.active(member.id) or not self.participating(member.guild):return False
        data=self.entry(member.id)['data'];self.queue(member.guild,data,'ban',data['operator'])
        try:
            status,result=await self.ban(member.guild,data)
            job=self.store.record(f'globaljob:{data["generation"]}:{member.guild.id}:ban')
            if job:
                job['data'].update(status=status,result=result,updated=time.time());self.store.put_record(member.guild.id,'global_ban_job',job['data'],job['id'])
        except discord.HTTPException as error:
            self.service.productivity.error('global ban on join',error)
            job=self.store.record(f'globaljob:{data["generation"]}:{member.guild.id}:ban')
            if job:
                job['data'].update(status='pending' if error.status in {429,500,502,503,504} else 'failed',result=f'Discord HTTP {error.status} during join enforcement.',attempts=1,next=time.time()+60,updated=time.time())
                self.store.put_record(member.guild.id,'global_ban_job',job['data'],job['id'])
        return True
    def reconcile(self):
        for row in self.store.records(kind='global_ban_consent'):
            if not self.bot.get_guild(row['guild']):self.store.set_option(row['guild'],'feature:global_bans',False)
        for guild in self.bot.guilds:
            if self.participating(guild):
                for row in self.entries():self.queue(guild,row['data'],'ban',row['data']['operator'],force=True)
    def start(self):
        if self.task is None:self.task=asyncio.create_task(self.run(),name='vivi-global-bans')
    async def run(self):
        while True:
            try:
                if self.bot.is_ready():
                    if not self.reconciled:self.reconcile();self.reconciled=True
                    await self.tick()
            except Exception as error:self.service.productivity.error('global-ban worker',error)
            await asyncio.sleep(2)
    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await self.task
            self.task=None
