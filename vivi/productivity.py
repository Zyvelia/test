"""AFK, configuration history, private scheduled backups, health, and safe aliases."""
import asyncio
from collections import deque
import datetime as dt
import inspect
import json
import math
import os
from pathlib import Path
import re
import secrets
import time

import discord
from discord import app_commands
from .bot import ROOT,reply
from .features import enabled
from .i18n import interaction_language,tr,NAME_TRANSLATIONS

ALIAS_TARGETS={'ping':('ping',{}),'help':('help',{}),
               'commands':('tools commands',{'search':None}),'profile':('economy profile',{}),
               'queue':('music queue',{}),'ticket':('ticket status',{})}
RESERVED={'ping','help','setup','role_button','ticket_panel','warn','warnings','timeout','untimeout','kick','ban','purge',
          'admin','mod','community','games','economy','tools','ai','music','room','ticket','notify','alias'}
RESERVED.update(name for values in NAME_TRANSLATIONS.values() for name in values)
BACKUP_NAME=re.compile(r'^config-\d{8}T\d{6}-[a-f0-9]{8}\.json$')

def validate_aliases(aliases):
    if not isinstance(aliases,dict) or len(aliases)>25: raise ValueError('Use at most 25 aliases per server.')
    for name,value in aliases.items():
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,19}',name) or name in RESERVED: raise ValueError('Alias names must be new lowercase command names (1–20 characters).')
        if not isinstance(value,dict) or set(value)!={'target','argument'} or value['target'] not in set(ALIAS_TARGETS)|{'faq'}:
            raise ValueError('Alias target must be ping, help, commands, profile, queue or ticket.')
        if not isinstance(value['argument'],str) or len(value['argument'])>100: raise ValueError('Alias arguments must be at most 100 characters.')
        if value['target'] not in {'faq','commands'} and value['argument']: raise ValueError('This shortcut takes no fixed argument.')


def atomic_private(path,body):
    """Never expose a partially written backup; exclude credentials by construction."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+secrets.token_hex(4)+'.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as handle: handle.write(body);handle.flush();os.fsync(handle.fileno())
        os.replace(tmp,path)
    finally: tmp.unlink(missing_ok=True)


class Productivity:
    def __init__(self,service):
        self.service=service;self.bot=service.bot;self.store=service.store
        self.started=time.monotonic();self.last_tick=0;self.errors=deque(maxlen=20)
        self.afk_notices={};self.alias_names={};self.last_backups={}

    def error(self,job,error):
        self.errors.append(dict(at=int(time.time()),job=job,error=type(error).__name__))

    async def on_message(self,message):
        if not enabled(self.store,message.guild.id,'afk'): return
        now=time.time();gid=message.guild.id
        record=self.store.record(f'afk:{gid}:{message.author.id}')
        language=self.store.option(gid,'language','en')
        if record:
            self.store.delete_record(record['id'])
            await message.reply(tr(language,'Welcome back, {name}. Your AFK status is cleared.',name=discord.utils.escape_markdown(message.author.display_name)),
                                allowed_mentions=discord.AllowedMentions.none(),mention_author=False)
        lines=[]
        for user in {m.id:m for m in message.mentions}.values():
            record=self.store.record(f'afk:{gid}:{user.id}')
            key=(gid,message.channel.id,user.id)
            if not record or now-self.afk_notices.get(key,0)<60: continue
            self.afk_notices[key]=now
            lines.append(tr(language,'{name} is AFK: {reason}',name=discord.utils.escape_markdown(user.display_name),
                            reason=discord.utils.escape_markdown(record['data']['reason'])))
            if len(lines)>=5: break
        if lines: await message.reply('\n'.join(lines)[:1900],allowed_mentions=discord.AllowedMentions.none(),mention_author=False)
        self.afk_notices={k:v for k,v in self.afk_notices.items() if now-v<120}

    def backup(self,guild):
        now=dt.datetime.now(dt.timezone.utc)
        folder=ROOT/'data'/'backups'/str(guild)
        path=folder/f'config-{now:%Y%m%dT%H%M%S}-{secrets.token_hex(4)}.json'
        atomic_private(path,json.dumps(self.store.export_config(guild),indent=2).encode())
        files=sorted([p for p in folder.iterdir() if BACKUP_NAME.fullmatch(p.name)],key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True)
        for old in files[self.store.option(guild,'backup_keep',7):]: old.unlink()
        self.store.set_option(guild,'internal_backup_last',time.time())
        self.last_backups[guild]='passed'
        return path

    async def tick(self):
        self.last_tick=time.time()
        for guild in self.bot.guilds:
            if enabled(self.store,guild.id,'scheduled_backups'):
                last=self.store.option(guild.id,'internal_backup_last',0)
                if time.time()-last>=self.store.option(guild.id,'backup_hours',24)*3600:
                    try: self.backup(guild.id)
                    except Exception as error: self.error('scheduled backup',error);self.last_backups[guild.id]='failed'
        # A private, credential-free heartbeat supports Docker's health check.
        atomic_private(ROOT/'data'/'heartbeat.json',json.dumps(dict(at=time.time(),ready=self.bot.is_ready())).encode())

    def health(self,guild):
        latency=self.bot.latency
        counts={kind:len(self.store.records(guild,kind)) for kind in ['poll','giveaway','notification','voice_room','reminder','lfg']}
        tickets=self.store.db.execute('SELECT COUNT(*) FROM tickets WHERE guild=?',(guild,)).fetchone()[0]
        task=self.service.task;notifications=self.service.notification_task
        return dict(gateway='connected' if self.bot.is_ready() else 'not connected',
                    uptime_seconds=int(time.monotonic()-self.started),
                    latency_ms=round(latency*1000) if math.isfinite(latency) else None,
                    timer_loop='running' if task and not task.done() else 'not running',
                    notification_loop='running' if notifications and not notifications.done() else 'not running',
                    personal_timer_loop='running' if self.service.suite.task and not self.service.suite.task.done() else 'not running',
                    game_timer_loop='running' if self.service.games.task and not self.service.games.task.done() else 'not running',
                    active_games=sum(key[0]==guild for key in self.service.games.sessions),
                    last_timer_tick=self.last_tick or None,open_tickets=tickets,records=counts,
                    audio_queue=len(self.service.voice.queues.get(guild,[])),
                    webhook_jobs=[dict(id=r['id'],attempts=r['data']['attempts'],error=r['data'].get('error','')) for r in self.store.records(guild,'webhook_job')],
                    database_bytes=self.store.path.stat().st_size if self.store.path.exists() else 0,
                    last_backup=self.store.option(guild,'internal_backup_last',None),
                    notifications=[dict(id=r['id'],error=r['data'].get('error',''),next_poll=r['data'].get('next_poll')) for r in self.store.records(guild,'notification')],
                    recent_errors=list(self.errors))

    async def run_alias(self,i,name):
        if not await self.service.need(i,'custom_aliases'): return
        aliases=self.store.option(i.guild_id,'aliases',{});definition=aliases.get(name)
        if not definition: return await reply(i,'That alias does not exist in this server.')
        validate_aliases({name:definition})
        if definition['target']=='faq':return await reply(i,'FAQ commands were removed. Remove or retarget this legacy shortcut.')
        target,arguments=ALIAS_TARGETS[definition['target']]
        parts=target.split();command=self.bot.tree.get_command(parts[0])
        for part in parts[1:]: command=command.get_command(part) if command else None
        if not command or isinstance(command,app_commands.Group): return await reply(i,'The target command is unavailable.')
        permissions=command.default_permissions or (command.parent.default_permissions if command.parent else None)
        if permissions and not i.permissions.is_superset(permissions): raise app_commands.MissingPermissions([p for p,v in permissions if v])
        for check in command.checks:
            result=check(i)
            if inspect.isawaitable(result): result=await result
            if not result: return await reply(i,'The target command check denied this shortcut.')
        values={k:definition['argument'] if value is None else value for k,value in arguments.items()}
        await command.callback(i,**values)

    async def refresh_aliases(self,guild_id,sync=True):
        definitions=self.store.option(guild_id,'aliases',{});validate_aliases(definitions)
        guild=discord.Object(id=guild_id)
        for name in self.alias_names.get(guild_id,set()): self.bot.tree.remove_command(name,guild=guild)
        for name in definitions:
            if definitions[name]['target']=='faq':continue
            if self.bot.tree.get_command(name) is not None: raise ValueError('Alias conflicts with a built-in command.')
            def make(alias_name):
                async def execute(i:discord.Interaction): await self.run_alias(i,alias_name)
                return execute
            command=app_commands.Command(name=name,description='Vivi shortcut: '+definitions[name]['target'],callback=make(name))
            command.guild_only=True
            self.bot.tree.add_command(command,guild=guild)
        self.alias_names[guild_id]=set(definitions)
        self.store.set_option(guild_id,'internal_alias_registered',True)
        if sync: await self.bot.tree.sync(guild=guild)

    async def refresh_configuration(self,guild):
        from .bot import RoleView
        for row in self.store.roles():
            if row['guild']==guild: self.bot.add_view(RoleView(self.bot,guild,row['role']))
        if self.store.option(guild,'aliases',{}) or guild in self.alias_names or self.store.option(guild,'internal_alias_registered',False):
            try: await self.refresh_aliases(guild)
            except Exception as error:
                self.error('alias sync',error)
                return False
        return True

    async def start_aliases(self):
        rows=self.store.db.execute("SELECT DISTINCT guild FROM options WHERE key IN ('aliases','internal_alias_registered')").fetchall()
        for row in rows:
            try: await self.refresh_aliases(row['guild'])
            except Exception as error: self.error('alias startup sync',error)


def register_productivity(bot):
    service=bot.community;p=service.productivity;store=bot.store
    tools=bot.tree.get_command('tools');admin=bot.tree.get_command('admin')
    aliases=app_commands.Group(name='alias',description='Custom read-only command shortcuts',guild_only=True)
    async def administrator(i):
        if not i.user.guild_permissions.administrator: raise app_commands.MissingPermissions(['administrator'])
        return True

    @tools.command(name='afk',description='Set an AFK status; returning to chat clears it. Leave reason blank to clear.')
    async def afk(i:discord.Interaction,reason:app_commands.Range[str,0,200]=''):
        if not await service.need(i,'afk'): return
        ident=f'afk:{i.guild_id}:{i.user.id}'
        if not reason.strip():
            store.delete_record(ident);return await reply(i,tr(interaction_language(i),'AFK status cleared.'))
        store.put_record(i.guild_id,'afk',dict(user=i.user.id,reason=reason.strip(),at=time.time()),ident)
        await reply(i,tr(interaction_language(i),'You are now AFK: {reason}',reason=discord.utils.escape_markdown(reason.strip())))

    @tools.command(name='language',description='Choose English, Spanish or French for supported Vivi responses, or inherit the server.')
    @app_commands.choices(language=[app_commands.Choice(name=n,value=v) for n,v in [('Server default','default'),('English','en'),('Español','es'),('Français','fr')]])
    async def language(i:discord.Interaction,language:str):
        if language not in {'default','en','es','fr'}: return await reply(i,'Choose en, es, fr or default.')
        profile=store.profile(i.guild_id,i.user.id);profile['language']='' if language=='default' else language
        store.save_profile(i.guild_id,i.user.id,profile)
        await reply(i,tr(language if language!='default' else store.option(i.guild_id,'language','en'),'Language saved.'))

    @admin.command(name='health',description='Show Vivi connection, jobs, queues and recent error classes for this server.')
    @app_commands.check(administrator)
    async def health(i:discord.Interaction):
        await reply(i,'```json\n'+json.dumps(p.health(i.guild_id),indent=2)[:1850]+'\n```')

    @admin.command(name='history',description='Show the most recent configuration revisions and their actors.')
    @app_commands.check(administrator)
    async def history(i:discord.Interaction):
        await reply(i,'\n'.join(f'#{r["id"]} · {r["created"]} · {r["actor"]} · {r["action"]}' for r in store.history(i.guild_id)[:15]) or 'No configuration changes recorded yet.')

    @admin.command(name='rollback',description='Restore a past configuration revision after resource validation.')
    @app_commands.check(administrator)
    async def rollback(i:discord.Interaction,revision:int,confirm:bool=False):
        if not confirm: return await reply(i,'Set confirm:true to restore this revision. Personal data is not rolled back.')
        row=store.revision(i.guild_id,revision)
        if not row: return await reply(i,'Revision not found in this server.')
        from .settings import validate_restore
        validate_restore(store,i.guild,row['after'])
        await i.response.defer(ephemeral=True);store.restore_config(i.guild_id,row['after'])
        await p.refresh_configuration(i.guild_id)
        await reply(i,'Configuration revision restored and recorded as a new change.')

    @admin.command(name='backup_now',description='Write a private configuration backup on the host immediately.')
    @app_commands.check(administrator)
    async def backup_now(i:discord.Interaction):
        path=p.backup(i.guild_id);await reply(i,f'Private configuration backup created: {path.name}')

    @aliases.command(name='add',description='Create a safe named shortcut; it also registers as a server slash command.')
    @app_commands.check(administrator)
    @app_commands.choices(target=[app_commands.Choice(name=x,value=x) for x in ALIAS_TARGETS])
    async def add(i:discord.Interaction,name:str,target:str,argument:app_commands.Range[str,0,100]=''):
        if target not in ALIAS_TARGETS:return await reply(i,'Choose a supported shortcut target. FAQ commands were removed.')
        values=store.option(i.guild_id,'aliases',{});values[name]=dict(target=target,argument=argument)
        validate_aliases(values)
        if bot.tree.get_command(name): raise ValueError('That name belongs to a built-in command.')
        await i.response.defer(ephemeral=True);store.set_option(i.guild_id,'aliases',values)
        try: await p.refresh_aliases(i.guild_id)
        except Exception as error:
            p.error('alias sync',error);return await reply(i,'Alias saved, but Discord registration failed. Use /alias run for now; it retries on restart.')
        await reply(i,f'Alias /{name} saved. Enable custom_aliases to use it.')

    @aliases.command(name='remove',description='Remove an alias from this server and Discord command registration.')
    @app_commands.check(administrator)
    async def remove(i:discord.Interaction,name:str):
        values=store.option(i.guild_id,'aliases',{})
        if name not in values: return await reply(i,'Alias not found.')
        del values[name];await i.response.defer(ephemeral=True);store.set_option(i.guild_id,'aliases',values)
        await p.refresh_aliases(i.guild_id);await reply(i,'Alias removed.')

    @aliases.command(name='list',description='List the safe command shortcuts configured in this server.')
    async def list_aliases(i:discord.Interaction):
        await reply(i,'\n'.join(f'/{name} → {definition["target"]}' for name,definition in store.option(i.guild_id,'aliases',{}).items()) or 'No aliases yet.')

    @aliases.command(name='run',description='Run one of this server’s configured read-only shortcuts.')
    async def run(i:discord.Interaction,name:str): await p.run_alias(i,name)

    bot.tree.add_command(aliases)
