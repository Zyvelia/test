"""Invite attribution is an estimate: missing baselines and ambiguous counters remain unknown."""
import asyncio
import time
import discord
from discord import app_commands
from .bot import reply
from .features import enabled


def estimate(previous,current):
    if previous is None:return dict(status='unknown',reason='No prior snapshot was available.')
    increments=[]
    for code,entry in current.items():
        before=previous.get(code)
        if before is None:
            if entry['uses']:return dict(status='unknown',reason='A used invite appeared without a baseline.')
            continue
        delta=entry['uses']-before['uses']
        if delta<0:return dict(status='unknown',reason='An invite counter changed unexpectedly.')
        if delta:increments.append((code,delta,entry))
    if set(previous)-set(current):return dict(status='unknown',reason='An invite disappeared; a one-use invite may have been consumed.')
    if len(increments)==1 and increments[0][1]==1:
        code,delta,entry=increments[0];return dict(status='estimated',code=code,inviter=entry['inviter'],reason='Exactly one observed invite use increased by one.')
    return dict(status='unknown',reason='Counters were unchanged or multiple joins/invites made attribution ambiguous. Vanity and discovery joins cannot be identified from these counters.')

class InviteTracker:
    def __init__(self,service):
        self.service=service;self.bot=service.bot;self.store=service.store;self.cache={};self.locks={};self.generations={}
        self.bot.add_listener(self.on_ready,'on_ready');self.bot.add_listener(self.on_invite_change,'on_invite_create');self.bot.add_listener(self.on_invite_change,'on_invite_delete');self.bot.add_listener(self.on_join,'on_member_join')
    def generation(self,guild):
        return self.store.db.execute("SELECT COALESCE(MAX(id),0) FROM config_history WHERE guild=? AND action IN ('setting: feature:invite_tracking','restore')",(guild,)).fetchone()[0]
    async def snapshot(self,guild):
        rows=await guild.invites()
        return {x.code:dict(uses=int(x.uses or 0),inviter=x.inviter.id if x.inviter else 0) for x in rows}
    async def refresh(self,guild):
        try:self.cache[guild.id]=await self.snapshot(guild)
        except discord.HTTPException:self.cache.pop(guild.id,None);return False
        self.generations[guild.id]=self.generation(guild.id);return True
    async def on_ready(self):
        for guild in self.bot.guilds:
            if enabled(self.store,guild.id,'invite_tracking'):
                async with self.locks.setdefault(guild.id,asyncio.Lock()):await self.refresh(guild)
            else:self.cache.pop(guild.id,None)
    async def on_invite_change(self,invite):
        if invite.guild:self.cache.pop(invite.guild.id,None)
    async def on_join(self,member):
        guild=member.guild
        if member.bot or not enabled(self.store,guild.id,'invite_tracking'):self.cache.pop(guild.id,None);return
        async with self.locks.setdefault(guild.id,asyncio.Lock()):
            generation=self.generation(guild.id)
            previous=self.cache.get(guild.id) if self.generations.get(guild.id,generation)==generation else None
            try:current=await self.snapshot(guild)
            except discord.HTTPException:
                self.cache.pop(guild.id,None);data=dict(status='unknown',reason='Invite counters could not be read. Vivi needs Manage Server permission.')
            else:self.cache[guild.id]=current;data=estimate(previous,current)
            self.generations[guild.id]=generation
            data.update(user=member.id,joined=time.time());self.store.put_record(guild.id,'invite_source',data,f'invite_source:{guild.id}:{member.id}')


def register_invites(bot):
    tracker=bot.community.invites
    group=app_commands.Group(name='invites',description='Private, best-effort invite source estimates',guild_only=True)
    @group.command(name='refresh',description='Create a fresh invite counter baseline; requires Manage Server.')
    @app_commands.default_permissions(manage_guild=True)
    async def refresh(i:discord.Interaction):
        if not i.user.guild_permissions.manage_guild:return await reply(i,'Manage Server permission is required.')
        if not await tracker.service.need(i,'invite_tracking'):return
        await i.response.defer(ephemeral=True)
        async with tracker.locks.setdefault(i.guild_id,asyncio.Lock()):ok=await tracker.refresh(i.guild)
        await reply(i,'Invite baseline refreshed. Future joins may be attributed when counters are unambiguous.' if ok else 'Could not read invites. Grant Vivi Manage Server, then retry.')
    @group.command(name='source',description='Privately inspect your estimated invite source; staff can inspect other members.')
    async def source(i:discord.Interaction,member:discord.Member=None):
        target=member or i.user
        if target.id!=i.user.id and not i.user.guild_permissions.manage_guild:return await reply(i,'Manage Server permission is required to inspect another member’s invite source.')
        row=tracker.store.record(f'invite_source:{i.guild_id}:{target.id}')
        if not row:return await reply(i,'No invite estimate is stored for this member. Tracking must be enabled before they join.')
        data=row['data'];await reply(i,f'Source: {data["status"]}\n'+(f'Invite code: `{data["code"]}` · inviter ID: {data["inviter"]}\n' if data['status']=='estimated' else '')+data['reason']+'\nThis is an estimate, not verified proof of who invited someone.')
    bot.tree.add_command(group)
