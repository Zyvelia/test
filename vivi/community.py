"""Optional community features, persistent UI, timers, and integrations."""
import asyncio
import contextlib
import datetime as dt
import hashlib
import hmac
import io
import json
import logging
import os
import random
import re
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

from .bot import reply, audit, RoleView
from .features import (FEATURES, SHOP, TRIVIA, QUESTIONS, WORDS, enabled, validate_option,
                       validate_backup, suspicious_link, blocked_word, award_activity, unlock,
                       win_board, convert)
from .policy import safe_self_role, may_moderate

LOG=logging.getLogger('vivi.community')
UTC=dt.timezone.utc

def timestamp(): return time.time()

def safe_role(guild, store, role):
    config=store.settings(guild.id)
    return (role is not None and config is not None and role.id!=config['staff']
            and safe_self_role(role,guild.me))

def color(value): return int(value.lstrip('#'),16)

def card_bytes(name, server, text, accent, avatar=None, greeting=None, brand=None, layout=None):
    if layout:
        from .studio_layout import render_layout
        return render_layout(layout,name,server,text,avatar,greeting,brand or "Vivi")
    image=Image.new('RGB',(900,260),(18,24,38)); d=ImageDraw.Draw(image)
    d.rounded_rectangle((5,5,894,254),radius=22,outline=accent,width=4)
    font=ImageFont.load_default(size=26); small=ImageFont.load_default(size=18)
    if avatar:
        with Image.open(io.BytesIO(avatar)) as source:
            picture=source.convert('RGB').resize((160,160))
        mask=Image.new('L',(160,160)); ImageDraw.Draw(mask).ellipse((0,0,159,159),fill=255)
        image.paste(picture,(30,50),mask)
    d.text((220,40),greeting or f'Welcome, {name[:30]}!',font=font,fill=accent)
    d.text((220,90),server[:45],font=small,fill='white')
    # Wrap on character boundaries as a fallback for long unbroken text.
    lines=[text[x:x+48] for x in range(0,min(len(text),144),48)]
    d.multiline_text((220,130),'\n'.join(lines),font=small,fill=(200,210,230),spacing=7)
    if brand: d.text((20,232),brand[:90],font=ImageFont.load_default(size=12),fill=(170,180,200))
    out=io.BytesIO(); image.save(out,format='PNG'); return out.getvalue()


class FeatureView(discord.ui.View):
    def __init__(self, service, record):
        super().__init__(timeout=None)
        self.service=service; self.ident=record['id']; data=record['data']; kind=record['kind']
        if kind=='role_menu':
            options=[discord.SelectOption(label=x['name'][:100],value=str(x['id'])) for x in data['roles']]
            select=discord.ui.Select(placeholder=f'Choose {data["category"]} roles', min_values=0,
                                     max_values=len(options),options=options,custom_id=f'extra:{self.ident}:menu')
            select.callback=self.menu
            self.add_item(select)
        else:
            choices=data['choices'] if kind=='poll' else ['Enter giveaway'] if kind=='giveaway' else ['Agree to rules'] if kind=='rules' else ['👍 Support','👎 Oppose']
            for n,label in enumerate(choices):
                button=discord.ui.Button(label=label[:80],custom_id=f'extra:{self.ident}:{n}',
                    style=discord.ButtonStyle.secondary,disabled=data.get('closed',False),row=n//5)
                async def callback(i, choice=n): await self.click(i,choice)
                button.callback=callback; self.add_item(button)

    async def menu(self,i):
        record=self.service.store.record(self.ident)
        if not record or record['guild']!=i.guild_id or not await self.service.need(i,'roles'): return
        await i.response.defer(ephemeral=True)
        try:
            values={int(x) for x in i.data['values']}
            async with self.service.lock:
                member=await i.guild.fetch_member(i.user.id)
                for item in record['data']['roles']:
                    role=i.guild.get_role(item['id'])
                    if not safe_role(i.guild,self.service.store,role):
                        await reply(i,'One role is missing or no longer safe. Ask an admin to replace this menu.'); return
                for item in record['data']['roles']:
                    role=i.guild.get_role(item['id'])
                    if role.id in values and role not in member.roles: await member.add_roles(role,reason='Vivi role menu')
                    if role.id not in values and role in member.roles: await member.remove_roles(role,reason='Vivi role menu')
            await reply(i,'Your selections were saved. This menu replaces only the roles it lists.')
        except discord.HTTPException:
            await reply(i,'Could not update all roles. Check my role position and retry.')

    async def click(self,i,choice):
        record=self.service.store.record(self.ident)
        if not record or record['guild']!=i.guild_id: return await reply(i,'This panel is unavailable.')
        kind=record['kind']; feature={'poll':'polls','giveaway':'giveaways','suggestion':'suggestions','rules':'rules'}[kind]
        if not await self.service.need(i,feature): return
        data=record['data']
        if data.get('closed') or (data.get('ends') and timestamp()>=data['ends']):
            return await reply(i,'Entries/voting are closed.')
        await i.response.defer(ephemeral=True)
        if kind=='rules':
            role=i.guild.get_role(data['role'])
            if not safe_role(i.guild,self.service.store,role): return await reply(i,'The acceptance role is no longer available or safe.')
            await i.user.add_roles(role,reason='Accepted server rules')
            return await reply(i,'Rules accepted. Your member role has been added.')
        if kind=='giveaway':
            if not self.service.eligible(i.user,data): return await reply(i,'You do not meet the eligibility requirements shown on this giveaway.')
            self.service.store.vote(self.ident,i.user.id,1)
            return await reply(i,'Entry saved. Winners must still meet the requirements at draw time.')
        voter=str(i.user.id)
        if kind=='poll' and data.get('anonymous'):
            voter=hmac.new(bytes.fromhex(data['salt']),voter.encode(),hashlib.sha256).hexdigest()
        self.service.store.vote(self.ident,voter,choice if kind=='poll' else (1 if choice==0 else -1))
        await reply(i,'Vote saved. Voting again replaces your previous vote.')
        if kind=='suggestion':
            votes=self.service.store.votes(self.ident)
            try: await i.message.edit(content=f'Suggestion #{self.ident}\n{data["text"]}\n👍 {sum(x["value"]==1 for x in votes)} · 👎 {sum(x["value"]==-1 for x in votes)}')
            except discord.HTTPException: pass


class DeleteView(discord.ui.View):
    def __init__(self,service,user,guild):
        super().__init__(timeout=60); self.service=service; self.user=user; self.guild=guild
    @discord.ui.button(label='Request deletion now',style=discord.ButtonStyle.danger)
    async def confirm(self,i,button):
        if i.user.id!=self.user or i.guild_id!=self.guild: return await reply(i,'This confirmation is not yours.')
        if self.service.store.ticket_for_user(i.guild_id,i.user.id):
            return await reply(i,'Close your active support ticket first, then request deletion again.')
        await i.response.defer(ephemeral=True)
        self.service.profiles.delete_banners(self.guild,self.user)
        self.service.store.delete_personal(self.guild,self.user)
        for record in self.service.store.records(self.guild):
            data=record['data']
            if (record['kind'] in {'appeal','report'} and data.get('author')==self.user) or (record['kind'] in {'ticket_rating','afk','reminder','invite_source','puzzle_progress','team_invite','team_application'} and data.get('user')==self.user):
                self.service.store.delete_record(record['id'])
            elif record['kind']=='library_entry' and data.get('author')==self.user:
                self.service.store.delete_record(record['id'])
            elif record['kind']=='team':
                data['roster']=[x for x in data['roster'] if x['user']!=self.user]
                if data['captain']==self.user:
                    if data['roster']:data['captain']=data['roster'][0]['user']
                    else:self.service.store.delete_record(record['id']);continue
                self.service.store.put_record(self.guild,'team',data,record['id'])
            elif record['kind']=='lfg' and data.get('owner')==self.user:
                self.service.store.delete_record(record['id'])
            elif record['kind']=='lfg' and self.user in data.get('members',[]):
                data['members'].remove(self.user); self.service.store.put_record(self.guild,'lfg',data,record['id'])
            elif record['kind']=='report' and data.get('target')==self.user:
                data['target']=0; self.service.store.put_record(self.guild,record['kind'],data,record['id'])
        ident=self.service.store.put_record(self.guild,'privacy',dict(author=self.user,text='Delete remaining identifiable moderation and retained records',status='pending'))
        await audit(self.service.bot,i.guild,f'Privacy request #{ident}. Privacy deletion request from member {self.user}. Staff: review transcripts, logs, closed giveaways, suggestions, backups, and other retained text for this member.')
        await reply(i,'Deleted your profile, birthday, AI memory and attributable votes from the active database. Staff were asked to review moderation records, transcripts, public messages and backups. Discord bans/roles are unchanged. Open anonymous poll ballots were removed too; already published aggregate counts remain.')
        self.stop()


class GameView(discord.ui.View):
    def __init__(self, service, first, second=None, trivia=None):
        super().__init__(timeout=180); self.service=service; self.players=[first,second] if second else [first]
        self.trivia=trivia; self.board=['']*9; self.turn=0; self.done=False; self.message=None;self.text_only=False
        from .game_design import THEMES
        theme='velvet'
        self.theme=theme if theme in THEMES else 'velvet'
        labels=[f'{chr(65+n)} · {answer}'[:80] for n,answer in enumerate(trivia[1])] if trivia else ['·']*9
        for n,label in enumerate(labels):
            button=discord.ui.Button(label=label,style=discord.ButtonStyle.primary if trivia else discord.ButtonStyle.secondary,row=n//2 if trivia else n//3)
            async def callback(i, pos=n): await self.play(i,pos)
            button.callback=callback; self.add_item(button)

    async def play(self,i,pos):
        if not await self.service.need(i,'games'): return
        if self.done: return await reply(i,'This game has ended.')
        if self.trivia:
            if i.user.id!=self.players[0]: return await reply(i,'Start your own game with /games trivia.')
            self.done=True;self.selected=pos;self.stop()
            won=pos==self.trivia[2]
            if won: self.service.reward(i.guild_id,i.user.id,10,'Trivia winner')
            for n,child in enumerate(self.children):
                child.disabled=True;child.style=discord.ButtonStyle.success if n==self.trivia[2] else discord.ButtonStyle.danger if n==pos else discord.ButtonStyle.secondary
            return await self.edit(i,'Correct! +10 coins if economy is enabled.' if won else f'Answer: {self.trivia[1][self.trivia[2]]}')
        if i.user.id!=self.players[self.turn]: return await reply(i,'It is not your turn.')
        if self.board[pos]: return await reply(i,'That square is occupied.')
        self.board[pos]='X' if self.turn==0 else 'O'; self.children[pos].label=self.board[pos]
        result=win_board(self.board)
        if result:
            self.done=True
            for child in self.children: child.disabled=True
            if result!='draw': self.service.reward(i.guild_id,i.user.id,0,'Tic-tac-toe winner')
            text='Draw!' if result=='draw' else f'{i.user.display_name} wins!'
        else:
            self.turn=1-self.turn; text=f'Tic-tac-toe · turn: <@{self.players[self.turn]}> (X starts)'
        await self.edit(i,text)

    async def edit(self,i,text):
        if not self.text_only:
            from .game_design import legacy_presentation,payload
            try:
                options=await payload(legacy_presentation(self,text),self.players);file=options.pop('file')
                return await i.response.edit_message(content=text,attachments=[file],view=self,**options)
            except (discord.HTTPException,OSError):self.text_only=True
        await i.response.edit_message(content=text,embed=None,attachments=[],view=self)

    async def on_timeout(self):
        if self.done:return
        self.done=True
        for child in self.children: child.disabled=True
        if self.message:
            from .game_design import legacy_presentation,payload
            with contextlib.suppress(discord.HTTPException,OSError):
                options=await payload(legacy_presentation(self,'Time is up. Start a new game.'),self.players);file=options.pop('file')
                await self.message.edit(content='Game timed out. Start a new one with /games.',attachments=[file],view=self,**options)


class Community:
    def __init__(self,bot):
        self.bot=bot; self.store=bot.store; self.lock=asyncio.Lock(); self.spam=defaultdict(deque); self.automod_last={}; self.ai_busy=set()
        self.session=None; self.task=None; self.dashboard=None; self.notification_task=None
        from .operations import Operations
        from .music import VoiceTools
        self.operations=Operations(self); self.voice=VoiceTools(self)
        from .productivity import Productivity
        self.productivity=Productivity(self)
        from .webhooks import Webhooks
        self.webhooks=Webhooks(self)
        from .suite import Suite
        from .game_hub import GameHub
        self.suite=Suite(self); self.games=GameHub(self)
        from .invites import InviteTracker
        from .profiles import ProfileCards
        self.invites=InviteTracker(self); self.profiles=ProfileCards(self)
        self.bot.add_listener(self.on_message,'on_message')
        self.bot.add_listener(self.on_message_edit,'on_message_edit')
        self.bot.add_listener(self.on_member_remove,'on_member_remove')

    async def start(self):
        self.session=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25),trust_env=True)
        for record in self.store.records():
            if record['kind'] in {'poll','giveaway','suggestion','role_menu','rules'} and not record['data'].get('closed'):
                self.bot.add_view(FeatureView(self,record))
        from .operations import RatingView
        for record in self.store.records(kind='ticket_rating'):
            if not record['data'].get('rating') and record['data']['expires']>time.time(): self.bot.add_view(RatingView(self.operations,record['id']))
        if os.getenv('DASHBOARD_ENABLED','').lower()=='true':
            from .dashboard import Dashboard
            try:
                self.dashboard=Dashboard(self)
                await self.dashboard.start()
            except Exception:
                LOG.error('Dashboard could not start. Check OAuth settings and whether its local port is in use.')
        try: await self.webhooks.start()
        except Exception as error:
            self.productivity.error('webhook startup',error)
            LOG.error('Webhook listener not started; check its signing secret, bind and port.')
        self.task=asyncio.create_task(self.scheduler(),name='vivi-scheduler')
        self.notification_task=asyncio.create_task(self.notification_scheduler(),name='vivi-notifications')
        self.suite.start(); self.games.start_task()
        from .guild_library import restore_team_panels
        restore_team_panels(self)

    async def close(self):
        await self.suite.close(); await self.games.close()
        await self.webhooks.close()
        if self.notification_task:
            self.notification_task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.notification_task
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                try: await self.task
                except Exception: LOG.exception('Scheduler stopped unexpectedly')
        await self.voice.close()
        if self.dashboard: await self.dashboard.close()
        if self.session: await self.session.close()

    async def need(self,i,feature):
        if not i.guild or not enabled(self.store,i.guild.id,feature):
            await reply(i,f'{feature} is disabled here. An admin can use /admin feature.'); return False
        return True

    async def case(self,guild,user,moderator,action,reason,member=None):
        ident=self.store.add_case(guild.id,user,moderator,action,reason)
        await audit(self.bot,guild,f'Case #{ident} · {action} · member {user} · moderator {moderator}: {reason}')
        if member and self.store.option(guild.id,'dm_explanations',False):
            try: await member.send(f'**{guild.name}** · case #{ident}\nAction: {action}\nReason: {reason}\nYou may use /community appeal if enabled and you still share a server with this bot. If banned, use the server\'s external appeal contact.')
            except discord.HTTPException: pass
        return ident

    def reward(self,guild,user,coins,achievement):
        p=self.store.profile(guild,user)
        if enabled(self.store,guild,'economy'): p['coins']+=coins
        unlock(p,achievement); self.store.save_profile(guild,user,p)

    def eligible(self,member,data):
        now=discord.utils.utcnow()
        return (not member.bot and (now-member.created_at).total_seconds()>=data['account_days']*86400
                and member.joined_at is not None and (now-member.joined_at).total_seconds()>=data['member_days']*86400
                and (not data['role'] or any(r.id==data['role'] for r in member.roles))
                and self.store.profile(member.guild.id,member.id)['xp']//100>=data['level'])

    async def publish(self,i,kind,data,text,channel=None):
        channel=channel or i.channel
        if not isinstance(channel,discord.TextChannel): raise ValueError('Choose a server text channel.')
        ident=self.store.put_record(i.guild_id,kind,data)
        record=self.store.record(ident)
        try:
            message=await channel.send(text,view=FeatureView(self,record))
        except Exception:
            self.store.delete_record(ident); raise
        data.update(channel=channel.id,message=message.id)
        self.store.put_record(i.guild_id,kind,data,ident)
        return ident

    async def on_join(self,member):
        guild=member.guild
        await self.operations.on_join(member)
        if enabled(self.store,guild.id,'autorole') and (not enabled(self.store,guild.id,'raid_protection') or self.store.option(guild.id,'internal_raid_until',0)<=time.time()):
            role=guild.get_role(self.store.option(guild.id,'autorole',0))
            if safe_role(guild,self.store,role):
                try: await member.add_roles(role,reason='Vivi automatic newcomer role')
                except discord.HTTPException: LOG.warning('Automatic role failed in %s',guild.id)
        if not enabled(self.store,guild.id,'welcome'): return
        config=self.store.settings(guild.id); channel=guild.get_channel(config['welcome']) if config else None
        if not channel: return
        from .i18n import tr
        language=self.store.option(guild.id,'language','en')
        text=self.store.option(guild.id,'welcome_text',tr(language,'Welcome {member} to {server}!')+' '+tr(language,'Please read the rules and choose your roles.'))
        text=text.replace('{member}',member.mention).replace('{server}',guild.name)
        try:
            if enabled(self.store,guild.id,'welcome_cards'):
                avatar=await member.display_avatar.with_size(256).with_format('png').read()
                data=await asyncio.to_thread(card_bytes,member.display_name,guild.name,
                    text.replace(member.mention,member.display_name),self.store.option(guild.id,'welcome_color','#87CEEB'),avatar,tr(language,'Welcome, {name}!',name=member.display_name[:30]),self.store.option(guild.id,'branding',{}).get('name','Vivi'),self.store.option(guild.id,'welcome_layout',None))
                await channel.send(text,file=discord.File(io.BytesIO(data),filename='welcome.png'),
                                   allowed_mentions=discord.AllowedMentions(users=[member],roles=False,everyone=False))
            else: await channel.send(text,allowed_mentions=discord.AllowedMentions(users=[member],roles=False,everyone=False))
        except (discord.HTTPException,OSError): LOG.warning('Welcome message/card failed in %s',guild.id)

    async def on_member_remove(self,member):
        if not enabled(self.store,member.guild.id,'goodbye'): return
        channel=member.guild.get_channel(self.store.option(member.guild.id,'goodbye_channel',0))
        if channel:
            from .i18n import tr
            text=self.store.option(member.guild.id,'goodbye_text',tr(self.store.option(member.guild.id,'language','en'),'Goodbye {member}.'))
            with contextlib.suppress(discord.HTTPException):
                await channel.send(text.replace('{member}',member.display_name).replace('{server}',member.guild.name))

    async def on_message_edit(self,before,after):
        if before.content!=after.content: await self.on_message(after,edited=True)

    async def on_message(self,message,edited=False):
        if not message.guild or message.author.bot or not isinstance(message.author,discord.Member): return
        guild=message.guild; p=None
        if (enabled(self.store,guild.id,'automod') or enabled(self.store,guild.id,'mention_protection')) and not message.author.guild_permissions.manage_messages:
            now=timestamp(); key=(guild.id,message.author.id); recent=self.spam[key]
            while recent and now-recent[0]>8: recent.popleft()
            recent.append(now)
            mentions=len({u.id for u in message.mentions})+len({r.id for r in message.role_mentions}) if enabled(self.store,guild.id,'mention_protection') else 0
            mention_limit=self.store.option(guild.id,'mention_limit',5)
            reason='mention spam' if enabled(self.store,guild.id,'mention_protection') and (mentions>mention_limit or message.mention_everyone) else ''
            if not reason and enabled(self.store,guild.id,'automod'):
                reason=('spam' if len(recent)>self.store.option(guild.id,'spam_limit',6) else
                        'blocked words' if blocked_word(message.content,self.store.option(guild.id,'blocked_words',[])) else
                        'suspicious link' if suspicious_link(message.content,self.store.option(guild.id,'blocked_domains',[])) else '')
            if reason:
                try:
                    await message.delete()
                    # Audit rate-limit avoids generating a case for every spam packet.
                    cooldown=self.automod_last.get(key,0)
                    if now-cooldown>30:
                        self.automod_last[key]=now
                        await self.case(guild,message.author.id,self.bot.user.id,'automod delete',reason,message.author)
                except discord.HTTPException: LOG.warning('AutoMod needs message deletion permission in %s',guild.id)
                return
        if not edited and enabled(self.store,guild.id,'afk'):
            try: await self.productivity.on_message(message)
            except discord.HTTPException as error: self.productivity.error('afk reply',error)
        if not edited and enabled(self.store,guild.id,'xp'):
            xp_channel=message.channel.parent_id if isinstance(message.channel,discord.Thread) else message.channel.id
            rule=self.store.option(guild.id,'xp_channels',{}).get(str(xp_channel),dict(enabled=True,amount=10,cooldown=60))
            if not rule['enabled']: return
            p=self.store.profile(guild.id,message.author.id)
            before=p['coins']
            if award_activity(p,message.content,timestamp(),amount=rule['amount'],cooldown=rule['cooldown'],channel=xp_channel):
                if not enabled(self.store,guild.id,'economy'): p['coins']=before
                self.store.save_profile(guild.id,message.author.id,p)

    async def finish_poll(self,record):
        data=record['data']; votes=self.store.votes(record['id'])
        counts=[sum(v['value']==n for v in votes) for n in range(len(data['choices']))]
        guild=self.bot.get_guild(record['guild']); channel=guild.get_channel(data['channel']) if guild else None
        if not channel: raise RuntimeError('Poll channel unavailable')
        text=data['question']+'\n**Final results**\n'+'\n'.join(f'{choice}: {count}' for choice,count in zip(data['choices'],counts))
        try:
            message=await channel.fetch_message(data['message'])
            await message.edit(content=text,view=None)
        except discord.NotFound: pass
        data.update(closed=True,counts=counts)
        self.store.put_record(record['guild'],'poll',data,record['id'])
        with self.store.db: self.store.db.execute('DELETE FROM ballots WHERE item=?',(record['id'],))

    async def draw(self,record,moderator=0):
        data=record['data']; guild=self.bot.get_guild(record['guild'])
        if not guild: raise RuntimeError('Server unavailable')
        channel=guild.get_channel(data['channel'])
        if not channel: raise RuntimeError('Giveaway channel unavailable')
        pool=[]; prior={x for draw in data.get('draws',[]) for x in draw['winners']}
        for ballot in self.store.votes(record['id']):
            uid=int(ballot['voter'])
            if uid in prior: continue
            try: member=await guild.fetch_member(uid)
            except discord.NotFound: continue
            if self.eligible(member,data): pool.append(uid)
        winners=random.SystemRandom().sample(pool,min(data['winners'],len(pool)))
        draw={'winners':winners,'at':timestamp(),'moderator':moderator}
        # Persist selection before publishing; retries reuse the same pending draw.
        pending=data.get('pending_draw') or draw
        data['pending_draw']=pending
        self.store.put_record(guild.id,'giveaway',data,record['id'])
        names=', '.join(f'<@{x}>' for x in pending['winners']) or 'No eligible entrants remain.'
        await channel.send(f'**Giveaway result #{record["id"]}** · {data["prize"]}\n{names}\n'
                           f'Draw #{len(data.get("draws",[]))+1} · requested by {pending["moderator"] or "automatic timer"}. '
                           'The full draw history is available through /community giveaway_history.')
        data.setdefault('draws',[]).append(pending); data.pop('pending_draw',None); data['closed']=True
        self.store.put_record(guild.id,'giveaway',data,record['id'])

    async def run_due(self):
        await self.productivity.tick()
        await self.voice.maintenance()
        now=timestamp()
        for key,recent in list(self.spam.items()):
            if not recent or now-recent[-1]>60: self.spam.pop(key,None)
        self.automod_last={k:v for k,v in self.automod_last.items() if now-v<60}
        for record in self.store.records():
            d=record['data']; kind=record['kind']; guild=self.bot.get_guild(record['guild'])
            if not guild: continue
            try:
                if kind=='tempban' and d['until']<=now:
                    try:
                        ban=await guild.fetch_ban(discord.Object(id=d['user']))
                        if f'Vivi tempban {record["id"]}:' not in (ban.reason or ''):
                            self.store.delete_record(record['id']); continue
                        await guild.unban(discord.Object(id=d['user']),reason='Vivi temporary ban expired')
                    except discord.NotFound: pass
                    await self.case(guild,d['user'],self.bot.user.id,'automatic unban','Temporary ban expired')
                    self.store.delete_record(record['id'])
                elif kind=='lockdown' and d['until']<=now:
                    channel=guild.get_channel(d['channel'])
                    if not channel: self.store.delete_record(record['id']); continue
                    ow=channel.overwrites_for(guild.default_role)
                    if ow.send_messages is not False:
                        self.store.delete_record(record['id']); continue
                    ow.send_messages=d['previous']
                    await channel.set_permissions(guild.default_role,overwrite=ow,reason='Vivi timed lockdown expired')
                    self.store.delete_record(record['id'])
                elif kind in {'poll','giveaway'} and not d.get('closed') and d['ends']<=now:
                    if kind=='poll': await self.finish_poll(record)
                    else: await self.draw(record)
            except Exception as error:
                self.productivity.error('scheduled '+kind,error)
                LOG.exception('Scheduled %s operation failed; retained for retry',kind)
        for guild in self.bot.guilds:
            zone=ZoneInfo(self.store.option(guild.id,'timezone','UTC'))
            local=dt.datetime.now(zone); day=local.date().isoformat()
            if local.hour>=self.store.option(guild.id,'daily_hour',9):
                for feature,key in [('daily_questions','daily_channel'),('birthdays','birthday_channel')]:
                    if not enabled(self.store,guild.id,feature): continue
                    marker=f'internal_daily:{feature}'
                    if self.store.option(guild.id,marker,'')==day: continue
                    channel=guild.get_channel(self.store.option(guild.id,key,0))
                    if not channel: continue
                    try:
                        if feature=='daily_questions': await channel.send('**Question of the day**\n'+QUESTIONS[local.date().toordinal()%len(QUESTIONS)])
                        else:
                            users=[uid for uid,p in self.store.profiles(guild.id) if p['birthday']==local.strftime('%m-%d') and guild.get_member(uid)]
                            for uid in users: await channel.send(f'🎂 Happy birthday, <@{uid}>!')
                        self.store.set_option(guild.id,marker,day)
                    except discord.HTTPException: LOG.warning('Daily announcement failed in %s',guild.id)
            # Expire opt-in AI memory independently of feature switches.
            for uid,p in self.store.profiles(guild.id):
                if p.get('turns') and now-p.get('memory_at',0)>86400:
                    p['turns']=[]; self.store.save_profile(guild.id,uid,p)

    async def scheduler(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                async with self.lock: await self.run_due()
            except Exception as error:
                self.productivity.error('timer scheduler',error)
                LOG.exception('Scheduler iteration failed; retrying in 30 seconds')
            await asyncio.sleep(30)

    async def notification_scheduler(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try: await self.operations.poll_notifications()
            except Exception as error:
                self.productivity.error('notification scheduler',error)
                LOG.exception('Notification scheduler failed; retrying')
            await asyncio.sleep(30)


def register_extra(bot):
    service=bot.community; store=bot.store
    admin=app_commands.Group(name='admin',description='Server features and configuration',guild_only=True,
                             default_permissions=discord.Permissions(administrator=True))
    mod=app_commands.Group(name='mod',description='Additional moderation and case history',guild_only=True,
                           default_permissions=discord.Permissions(moderate_members=True))
    community=app_commands.Group(name='community',description='Community activities, roles, polls, and support',guild_only=True)
    games=app_commands.Group(name='games',description='Trivia, word games, and multiplayer games',guild_only=True)
    economy=app_commands.Group(name='economy',description='Profiles, achievements, levels, and cosmetic shop',guild_only=True)
    tools=app_commands.Group(name='tools',description='Search, timezones, units, translation, and privacy',guild_only=True)
    ai=app_commands.Group(name='ai',description='Optional AI: off by default, channel restricted, with opt-in memory',guild_only=True)

    async def administrator(i):
        if not i.user.guild_permissions.administrator: raise app_commands.MissingPermissions(['administrator'])
        return True

    def admin_command(name,description):
        def decorate(func):
            func=app_commands.check(administrator)(func)
            return admin.command(name=name,description=description)(func)
        return decorate

    async def permission(i,name):
        if not getattr(i.user.guild_permissions,name): raise app_commands.MissingPermissions([name])
        if not await service.need(i,'moderation'): return False
        return True

    async def feature_choices(i,current):
        return [app_commands.Choice(name=x,value=x) for x in FEATURES if current.lower() in x][:25]

    @admin_command('feature','Enable or disable one feature for this server. AI starts disabled.')
    @app_commands.autocomplete(name=feature_choices)
    async def feature(i:discord.Interaction,name:str,enabled:bool):
        if name not in FEATURES: return await reply(i,'Unknown feature. Use the suggestions.')
        store.set_option(i.guild_id,'feature:'+name,enabled)
        if name=='invite_tracking':service.invites.cache.pop(i.guild_id,None)
        await reply(i,f'{name}: {"ON" if enabled else "OFF"}.')

    @admin_command('verify','Check this server’s bot permissions without posting test messages.')
    async def verify(i:discord.Interaction):
        from .verify import guild_checks
        checks=guild_checks(store,i.guild)
        await reply(i,'\n'.join(f'{c["status"]}: {c["name"]} — {c["detail"]}' for c in checks))

    @admin_command('features','Show all per-server feature switches.')
    async def features(i:discord.Interaction):
        await reply(i,'\n'.join(f'{name}: {"ON" if enabled(store,i.guild_id,name) else "OFF"}' for name in FEATURES))

    async def setting_choices(i,current):
        from .features import OPTION_TYPES
        return [app_commands.Choice(name=x,value=x) for x in OPTION_TYPES if current.lower() in x][:25]

    @admin_command('setting','Set a validated setting. Lists use commas; channel/role values use numeric IDs.')
    @app_commands.autocomplete(name=setting_choices)
    async def setting(i:discord.Interaction,name:str,value:app_commands.Range[str,1,1800]):
        from .features import OPTION_TYPES
        if name not in OPTION_TYPES or name=='faq': return await reply(i,'Unknown setting; use /admin faq_add for FAQ entries.')
        from .settings import parse_value, validate_resources
        try:
            parsed=parse_value(name,value); validate_resources(store,i.guild,name,parsed)
            store.set_option(i.guild_id,name,parsed)
        except (ValueError,KeyError) as e: return await reply(i,str(e))
        if name=='aliases':
            await i.response.defer(ephemeral=True)
            await service.productivity.refresh_aliases(i.guild_id)
        await reply(i,f'Saved {name}.')

    @admin_command('faq_add','Add or replace an FAQ answer; members search using /community faq.')
    async def faq_add(i:discord.Interaction,question:app_commands.Range[str,1,150],answer:app_commands.Range[str,1,1200]):
        items=store.option(i.guild_id,'faq',{})
        if len(items)>=50 and question not in items: return await reply(i,'Maximum 50 FAQs; remove an old entry first.')
        items[question]=answer; store.set_option(i.guild_id,'faq',items)
        await reply(i,'FAQ saved.')

    @admin_command('faq_remove','Remove an FAQ by its exact question.')
    async def faq_remove(i:discord.Interaction,question:str):
        items=store.option(i.guild_id,'faq',{}); existed=items.pop(question,None)
        store.set_option(i.guild_id,'faq',items)
        await reply(i,'FAQ removed.' if existed else 'That exact question was not found.')

    @admin_command('backup','Download server configuration only; excludes tokens, profiles and transcripts.')
    async def backup(i:discord.Interaction):
        data=json.dumps(store.export_config(i.guild_id),indent=2).encode()
        await i.response.send_message(file=discord.File(io.BytesIO(data),filename=f'vivi-config-{i.guild_id}.json'),ephemeral=True)

    @admin_command('restore','Restore this server configuration from a backup. Explicit confirmation required.')
    async def restore(i:discord.Interaction,file:discord.Attachment,confirm:bool=False):
        if not confirm: return await reply(i,'This replaces configuration. Set confirm:true only after checking your backup.')
        if file.size>131072: return await reply(i,'Backup must be under 128 KiB.')
        await i.response.defer(ephemeral=True)
        try:
            data=json.loads(await file.read())
            from .settings import validate_restore
            validate_restore(store,i.guild,data)
            store.restore_config(i.guild_id,data)
            for row in store.roles():
                if row['guild']==i.guild_id: bot.add_view(RoleView(bot,i.guild_id,row['role']))
        except (ValueError,KeyError,TypeError) as e: return await reply(i,f'Backup not restored: {e}')
        await service.productivity.refresh_configuration(i.guild_id)
        await reply(i,'Configuration restored atomically. Personal data and live panels were not restored; check channel permissions and repost panels as needed.')

    @community.command(name='faq',description='Search this server’s FAQ questions and answers.')
    async def faq(i:discord.Interaction,search:app_commands.Range[str,1,100]):
        if not await service.need(i,'faq'): return
        matches=[(q,a) for q,a in store.option(i.guild_id,'faq',{}).items() if search.casefold() in (q+' '+a).casefold()]
        await reply(i,('\n\n'.join(f'**{q}**\n{a}' for q,a in matches[:5])[:1900]) or 'No matching FAQ found.')

    @community.command(name='rules',description='Post server rules with a persistent acceptance button. Admin only.')
    async def rules(i:discord.Interaction,channel:discord.TextChannel):
        await administrator(i)
        if not await service.need(i,'rules'): return
        role=i.guild.get_role(store.option(i.guild_id,'rules_role',0)); text=store.option(i.guild_id,'rules_text','')
        if not text or not safe_role(i.guild,store,role): return await reply(i,'Set rules_text and a safe rules_role using /admin setting first.')
        await i.response.defer(ephemeral=True)
        ident=await service.publish(i,'rules',dict(role=role.id),text,channel)
        await reply(i,f'Rules panel posted: {ident}. Keep the automatic newcomer role separate from the rules acceptance role.')

    @community.command(name='role_menu',description='Post a role dropdown for games, platforms or notifications. Admin only.')
    @app_commands.choices(category=[app_commands.Choice(name=x,value=x) for x in ['Games','Platforms','Notifications']])
    async def role_menu(i:discord.Interaction,channel:discord.TextChannel,category:str,role_ids:str):
        await administrator(i)
        if not await service.need(i,'roles'): return
        try: roles=[i.guild.get_role(int(x.strip('<@&> '))) for x in role_ids.split(',')]
        except ValueError: return await reply(i,'Enter 1–25 role IDs separated by commas.')
        if not 1<=len(roles)<=25 or any(not safe_role(i.guild,store,r) for r in roles): return await reply(i,'Use 1–25 existing safe, non-staff roles below the bot role.')
        if len({r.id for r in roles})!=len(roles): return await reply(i,'Remove duplicate roles.')
        await i.response.defer(ephemeral=True)
        await service.publish(i,'role_menu',dict(category=category,roles=[dict(id=r.id,name=r.name) for r in roles]),f'**Choose your {category.lower()} roles**\nSelecting replaces your previous choices from this menu.',channel)
        await reply(i,'Role menu posted.')

    @community.command(name='role_preview',description='Show permissions granted by a role before you choose it.')
    async def role_preview(i:discord.Interaction,role:discord.Role):
        permissions=', '.join(name.replace('_',' ') for name,value in role.permissions if value) or 'No server-wide permissions.'
        await reply(i,f'**{role.name}**\n{permissions[:1500]}\nChannel overrides and your other roles can change effective access. This does not assign the role.')

    @community.command(name='appeal',description='Privately submit an appeal for one of your moderation cases.')
    @app_commands.checks.cooldown(1,300,key=lambda i:(i.guild_id,i.user.id))
    async def appeal(i:discord.Interaction,case_id:int,text:app_commands.Range[str,10,1500]):
        if not await service.need(i,'appeals'): return
        case=store.db.execute('SELECT * FROM cases WHERE id=? AND guild=? AND user=?',(case_id,i.guild_id,i.user.id)).fetchone()
        if not case: return await reply(i,'That case does not belong to you in this server. Banned members need the server’s external appeal contact.')
        config=store.settings(i.guild_id)
        if not config or not i.guild.get_channel(config['logs']): return await reply(i,'Staff logging is not configured yet.')
        ident=store.put_record(i.guild_id,'appeal',dict(author=i.user.id,case=case_id,text=text,status='pending'))
        await audit(bot,i.guild,f'**Appeal #{ident}** · case #{case_id} · member {i.user.id}\n{text}')
        await reply(i,f'Appeal #{ident} submitted privately to staff. It does not automatically reverse moderation.')

    @community.command(name='report',description='Privately report a member to staff, without a public accusation.')
    @app_commands.checks.cooldown(1,300,key=lambda i:(i.guild_id,i.user.id))
    async def report(i:discord.Interaction,member:discord.Member,details:app_commands.Range[str,10,1500]):
        if not await service.need(i,'reports'): return
        config=store.settings(i.guild_id)
        if not config or not i.guild.get_channel(config['logs']): return await reply(i,'Staff logging is not configured yet.')
        ident=store.put_record(i.guild_id,'report',dict(author=i.user.id,target=member.id,text=details,status='pending'))
        await audit(bot,i.guild,f'**Private report #{ident}** · reporter {i.user.id} · target {member.id}\n{details}')
        await reply(i,f'Report #{ident} sent to staff. Your identity is visible to staff, not posted publicly.')

    @mod.command(name='history',description='Search numbered moderation cases by member or reason.')
    async def history(i:discord.Interaction,member:discord.Member=None,search:str=''):
        if not await permission(i,'moderate_members'): return
        rows=store.search_cases(i.guild_id,member.id if member else None,search)
        await reply(i,('\n'.join(f'#{r["id"]} {r["action"]} · {r["user"]} · {r["created"]} · {r["reason"][:70]}' for r in rows))[:1900] or 'No matching cases.')

    @mod.command(name='inbox',description='List pending private reports, appeals, and privacy requests for staff.')
    async def inbox(i:discord.Interaction):
        if not await permission(i,'moderate_members'): return
        records=[r for r in store.records(i.guild_id) if r['kind'] in {'report','appeal','privacy'} and r['data'].get('status')=='pending']
        await reply(i,('\n'.join(f'{r["kind"]} #{r["id"]} · author {r["data"]["author"]} · {r["data"].get("text","")[:70]}' for r in records[:15]))[:1900] or 'No pending requests.')

    @mod.command(name='review',description='Review an appeal or report and record a staff response.')
    async def review(i:discord.Interaction,ident:str,response:app_commands.Range[str,1,1200],accepted:bool):
        if not await permission(i,'moderate_members'): return
        record=store.record(ident)
        if not record or record['guild']!=i.guild_id or record['kind'] not in {'appeal','report','privacy'}: return await reply(i,'Request not found in this server.')
        if record['kind']=='privacy':
            await administrator(i)
            if accepted: store.erase_moderation(i.guild_id,record['data']['author'])
        data=record['data']; data.update(status='accepted' if accepted else 'declined',response=response,reviewer=i.user.id)
        store.put_record(i.guild_id,record['kind'],data,ident)
        await i.response.defer(ephemeral=True)
        try:
            member=await i.guild.fetch_member(data['author'])
            await member.send(f'Your {record["kind"]} #{ident}: {data["status"]}\n{response}\nStaff apply any moderation changes separately.')
        except discord.HTTPException: pass
        await audit(bot,i.guild,f'{record["kind"]} #{ident} reviewed by {i.user.id}: {data["status"]}\n{response}')
        await reply(i,'Review saved. Any change to a ban or timeout must be made explicitly.')

    @mod.command(name='tempban',description='Ban a member temporarily; expiry survives restarts.')
    async def tempban(i:discord.Interaction,member:discord.Member,hours:app_commands.Range[int,1,8760],reason:app_commands.Range[str,1,500]):
        if not await permission(i,'ban_members'): return
        if not may_moderate(i.user,member,i.guild.me,i.guild.owner_id): return await reply(i,'Role hierarchy prevents this moderation action.')
        await i.response.defer(ephemeral=True)
        async with service.lock:
            if any(r['data']['user']==member.id for r in store.records(i.guild_id,'tempban')):
                return await reply(i,'This member already has a scheduled temporary ban.')
            ident=store.put_record(i.guild_id,'tempban',dict(user=member.id,until=timestamp()+hours*3600))
            try: await member.ban(reason=f'Vivi tempban {ident}: {reason}'[:512],delete_message_seconds=0)
            except discord.HTTPException:
                store.delete_record(ident); raise
        case=await service.case(i.guild,member.id,i.user.id,'temporary ban',f'{hours} hours: {reason}',member)
        await reply(i,f'Temporary ban applied. Case #{case}. Expiry is processed when the bot is online.')

    @mod.command(name='unban',description='Unban a user by numeric ID and cancel any scheduled temporary ban.')
    async def unban(i:discord.Interaction,user_id:str,reason:app_commands.Range[str,1,500]):
        if not await permission(i,'ban_members'): return
        if not user_id.isdigit(): return await reply(i,'Enter a numeric Discord user ID.')
        await i.response.defer(ephemeral=True)
        try: await i.guild.unban(discord.Object(id=int(user_id)),reason=f'{i.user.id}: {reason}'[:512])
        except discord.NotFound: return await reply(i,'That user is not banned.')
        for record in store.records(i.guild_id,'tempban'):
            if record['data']['user']==int(user_id): store.delete_record(record['id'])
        case=await service.case(i.guild,int(user_id),i.user.id,'unban',reason)
        await reply(i,f'User unbanned. Case #{case}.')

    @mod.command(name='lockdown',description='Temporarily deny @everyone Send Messages in this text channel.')
    async def lockdown(i:discord.Interaction,minutes:app_commands.Range[int,1,1440]):
        if not await permission(i,'manage_channels'): return
        if not isinstance(i.channel,discord.TextChannel): return await reply(i,'Use this in a server text channel.')
        async with service.lock:
            if any(r['data']['channel']==i.channel_id for r in store.records(i.guild_id,'lockdown')): return await reply(i,'This channel already has an active lockdown.')
            await i.response.defer(ephemeral=True)
            ow=i.channel.overwrites_for(i.guild.default_role)
            ident=store.put_record(i.guild_id,'lockdown',dict(channel=i.channel_id,previous=ow.send_messages,until=timestamp()+minutes*60))
            ow.send_messages=False
            try: await i.channel.set_permissions(i.guild.default_role,overwrite=ow,reason=f'Vivi lockdown by {i.user.id}')
            except discord.HTTPException: store.delete_record(ident); raise
        await service.case(i.guild,0,i.user.id,'channel lockdown',f'{i.channel_id}, {minutes} minutes')
        await reply(i,f'@everyone cannot send messages here for {minutes} minutes. Explicit role/member overrides and administrators can still speak.')

    @mod.command(name='unlock',description='End this bot’s active lockdown early and restore the saved permission.')
    async def unlock_channel(i:discord.Interaction):
        if not await permission(i,'manage_channels'): return
        await i.response.defer(ephemeral=True)
        async with service.lock:
            matches=[r for r in store.records(i.guild_id,'lockdown') if r['data']['channel']==i.channel_id]
            if not matches: return await reply(i,'No bot-managed lockdown is active here.')
            record=matches[0]; ow=i.channel.overwrites_for(i.guild.default_role)
            ow.send_messages=record['data']['previous']
            await i.channel.set_permissions(i.guild.default_role,overwrite=ow,reason=f'Vivi early unlock by {i.user.id}')
            store.delete_record(record['id'])
        await reply(i,'Previous @everyone Send Messages setting restored.')

    @mod.command(name='slowmode',description='Set channel slowmode in seconds; zero disables it.')
    async def slowmode(i:discord.Interaction,seconds:app_commands.Range[int,0,21600]):
        if not await permission(i,'manage_channels'): return
        if not isinstance(i.channel,discord.TextChannel): return await reply(i,'Choose a server text channel.')
        await i.response.defer(ephemeral=True)
        await i.channel.edit(slowmode_delay=seconds,reason=f'Vivi slowmode by {i.user.id}')
        await service.case(i.guild,0,i.user.id,'slowmode',f'{i.channel_id}: {seconds} seconds')
        await reply(i,f'Slowmode set to {seconds} seconds.')

    @community.command(name='poll',description='Create a timed button poll; voters can replace their choice.')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll(i:discord.Interaction,question:app_commands.Range[str,1,500],choices:str,
                   minutes:app_commands.Range[int,1,10080]=60,anonymous:bool=False):
        if not await service.need(i,'polls'): return
        values=[x.strip() for x in choices.split('|') if x.strip()]
        if not 2<=len(values)<=10 or any(len(x)>80 for x in values): return await reply(i,'Use 2–10 choices separated by |, each at most 80 characters.')
        await i.response.defer(ephemeral=True)
        ident=await service.publish(i,'poll',dict(question=question,choices=values,ends=timestamp()+minutes*60,
            anonymous=anonymous,salt=secrets.token_hex(32),closed=False),f'**{question}**\n'+('Anonymous poll: no voter names are published.' if anonymous else 'Poll: votes are stored with member IDs; no public voter list.')+f'\nCloses <t:{int(timestamp()+minutes*60)}:R>.')
        await reply(i,f'Poll #{ident} created.')

    @community.command(name='poll_close',description='Close a poll early and publish totals.')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def poll_close(i:discord.Interaction,ident:str):
        if not await service.need(i,'polls'): return
        record=store.record(ident)
        if not record or record['guild']!=i.guild_id or record['kind']!='poll': return await reply(i,'Poll not found.')
        if record['data'].get('closed'): return await reply(i,'This poll is already closed.')
        await i.response.defer(ephemeral=True)
        async with service.lock:
            current=store.record(ident)
            if not current['data'].get('closed'): await service.finish_poll(current)
        await reply(i,'Poll closed; totals published and individual ballots removed.')

    @community.command(name='giveaway',description='Create a giveaway with account, membership, role and level requirements.')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def giveaway(i:discord.Interaction,prize:app_commands.Range[str,1,300],minutes:app_commands.Range[int,1,43200],
                       winners:app_commands.Range[int,1,10]=1,account_days:app_commands.Range[int,0,3650]=0,
                       member_days:app_commands.Range[int,0,3650]=0,required_role:discord.Role=None,
                       minimum_level:app_commands.Range[int,0,1000]=0):
        if not await service.need(i,'giveaways'): return
        await i.response.defer(ephemeral=True)
        data=dict(prize=prize,ends=timestamp()+minutes*60,winners=winners,account_days=account_days,
                  member_days=member_days,role=required_role.id if required_role else 0,level=minimum_level,closed=False,draws=[])
        text=(f'**Giveaway: {prize}**\n{winners} winner(s) · closes <t:{int(data["ends"])}:R>\n'
              f'Account age: {account_days} days · membership: {member_days} days · level: {minimum_level}\n'
              f'Required role: {required_role.name if required_role else "none"}. No purchase or real money involved.')
        ident=await service.publish(i,'giveaway',data,text)
        await reply(i,f'Giveaway #{ident} created. Timers are processed while the bot is online.')

    @community.command(name='giveaway_reroll',description='Select replacement winners and publish a permanent draw record.')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def reroll(i:discord.Interaction,ident:str):
        if not await service.need(i,'giveaways'): return
        record=store.record(ident)
        if not record or record['guild']!=i.guild_id or record['kind']!='giveaway' or not record['data'].get('closed'):
            return await reply(i,'Choose an already finished giveaway in this server.')
        await i.response.defer(ephemeral=True)
        async with service.lock:
            await service.draw(store.record(ident),i.user.id)
        await reply(i,'Reroll published. Previous winners remain in the public history and are excluded from new draws.')

    @community.command(name='giveaway_history',description='Show the public draw history for a giveaway.')
    async def giveaway_history(i:discord.Interaction,ident:str):
        if not await service.need(i,'giveaways'): return
        record=store.record(ident)
        if not record or record['guild']!=i.guild_id or record['kind']!='giveaway': return await reply(i,'Giveaway not found.')
        rows=[f'Draw {n}: '+(', '.join(str(x) for x in d['winners']) or 'no eligible entrants')+f' · by {d["moderator"] or "timer"}' for n,d in enumerate(record['data'].get('draws',[]),1)]
        await reply(i,('\n'.join(rows))[-1800:] or 'No draws yet.')

    @community.command(name='suggest',description='Post a suggestion to the current channel with one vote per member.')
    @app_commands.checks.cooldown(1,60,key=lambda i:(i.guild_id,i.user.id))
    async def suggest(i:discord.Interaction,text:app_commands.Range[str,10,1200]):
        if not await service.need(i,'suggestions'): return
        await i.response.defer(ephemeral=True)
        ident=await service.publish(i,'suggestion',dict(text=text,author=i.user.id,closed=False),f'**Suggestion**\n{text}\n👍 0 · 👎 0')
        await reply(i,f'Suggestion #{ident} posted. Staff can review it using /community suggestion_decide.')

    @community.command(name='suggestion_decide',description='Accept or decline a suggestion and publish a staff explanation.')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def suggestion_decide(i:discord.Interaction,ident:str,accepted:bool,reason:app_commands.Range[str,1,500]):
        if not await service.need(i,'suggestions'): return
        record=store.record(ident)
        if not record or record['guild']!=i.guild_id or record['kind']!='suggestion': return await reply(i,'Suggestion not found.')
        await i.response.defer(ephemeral=True)
        data=record['data']; channel=i.guild.get_channel(data['channel'])
        if not channel: return await reply(i,'Suggestion channel no longer exists.')
        message=await channel.fetch_message(data['message'])
        await message.edit(content=f'Suggestion #{ident}: **{"Accepted" if accepted else "Declined"}**\n{data["text"]}\nStaff: {reason}',view=None)
        data.update(closed=True,decision=accepted,reason=reason,moderator=i.user.id)
        store.put_record(i.guild_id,'suggestion',data,ident)
        await reply(i,'Decision published.')

    @community.command(name='birthday',description='Opt into birthday announcements with MM-DD and a timezone, or clear your date.')
    async def birthday(i:discord.Interaction,date:str=''):
        if not await service.need(i,'birthdays'): return
        p=store.profile(i.guild_id,i.user.id)
        try:
            if date:
                if not re.fullmatch(r'\d{2}-\d{2}',date): raise ValueError('Use MM-DD, for example 07-23. No birth year is stored.')
                dt.date.fromisoformat('2000-'+date)
        except (ValueError,KeyError) as e: return await reply(i,f'Invalid date/timezone: {e}')
        p.update(birthday=date); store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'Birthday saved (no year). Announcements follow the server timezone.' if date else 'Birthday announcement opt-in removed.')

    @community.command(name='spotlight_optin',description='Consent to a public member spotlight, or opt out.')
    async def spotlight_optin(i:discord.Interaction,opt_in:bool):
        if not await service.need(i,'spotlight'): return
        p=store.profile(i.guild_id,i.user.id); p['spotlight']=opt_in; store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'You are eligible for a spotlight.' if opt_in else 'You have opted out.')

    @community.command(name='spotlight',description='Feature a randomly selected consenting member. Staff only.')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def spotlight(i:discord.Interaction,channel:discord.TextChannel):
        if not await service.need(i,'spotlight'): return
        pool=[uid for uid,p in store.profiles(i.guild_id) if p['spotlight'] and i.guild.get_member(uid) and not i.guild.get_member(uid).bot]
        if not pool: return await reply(i,'Nobody has opted in through /community spotlight_optin yet.')
        member=i.guild.get_member(secrets.choice(pool)); p=store.profile(i.guild_id,member.id)
        await i.response.defer(ephemeral=True)
        embed=discord.Embed(title='Community member spotlight',description=f'Celebrating {member.display_name}!\nLevel {p["xp"]//100} · {len(p["achievements"])} achievements',color=0x87CEEB)
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)
        await reply(i,'Spotlight posted. Only members who opted in were eligible.')

    @games.command(name='trivia',description='Answer a multiple-choice trivia question; a correct answer earns coins.')
    @app_commands.checks.cooldown(1,60,key=lambda i:(i.guild_id,i.user.id))
    async def trivia(i:discord.Interaction):
        if not await service.need(i,'games'): return
        question=secrets.choice(TRIVIA); view=GameView(service,i.user.id,trivia=question)
        from .game_design import THEMES,legacy_presentation,payload
        theme=store.profile(i.guild_id,i.user.id).get('game_theme','velvet');view.theme=theme if theme in THEMES else 'velvet'
        try:await i.response.send_message(view=view,**await payload(legacy_presentation(view),view.players))
        except (discord.HTTPException,OSError):
            view.text_only=True;await i.response.send_message(question[0],view=view)
        view.message=await i.original_response()

    @games.command(name='word',description='Start a scrambled-word challenge; use /games guess to answer.')
    @app_commands.checks.cooldown(1,60,key=lambda i:(i.guild_id,i.user.id))
    async def word(i:discord.Interaction):
        if not await service.need(i,'games'): return
        answer=secrets.choice(WORDS); letters=list(answer)
        random.SystemRandom().shuffle(letters)
        if ''.join(letters)==answer: letters=letters[1:]+letters[:1]
        p=store.profile(i.guild_id,i.user.id); p.update(word=answer,word_until=timestamp()+120,word_attempts=0)
        store.save_profile(i.guild_id,i.user.id,p)
        from .game_design import payload
        data=dict(kind='anagram',title='Word Scramble',round=1,rounds=1,letters=''.join(letters),scores=[],previous='',done=False,turn=0,theme=store.profile(i.guild_id,i.user.id).get('game_theme','velvet'),help='Use /games guess within two minutes. You get five attempts.')
        try:
            options=await payload(data);options['embed'].set_footer(text='Answer with /games guess · Five attempts · Two minutes')
            options['file'].description='Word scramble: '+', '.join(letters)+'. Answer with /games guess.'
            await i.response.send_message(ephemeral=True,**options)
        except (discord.HTTPException,OSError):await reply(i,f'Unscramble **{" ".join(letters)}**. Use /games guess within two minutes. You get five attempts.')

    @games.command(name='guess',description='Submit an answer to your current scrambled-word challenge.')
    async def guess(i:discord.Interaction,answer:str):
        if not await service.need(i,'games'): return
        p=store.profile(i.guild_id,i.user.id)
        if not p.get('word') or p.get('word_until',0)<timestamp(): return await reply(i,'Start a new challenge with /games word.')
        p['word_attempts']=p.get('word_attempts',0)+1
        won=answer.strip().casefold()==p['word']
        if won or p['word_attempts']>=5: p.pop('word',None)
        store.save_profile(i.guild_id,i.user.id,p)
        if won: service.reward(i.guild_id,i.user.id,10,'Word solver')
        await reply(i,'Correct! +10 coins if economy is enabled.' if won else 'Nope. Start a new word game.' if p['word_attempts']>=5 else 'Not quite. Try again.')

    @games.command(name='tictactoe',description='Play turn-based tic-tac-toe against another server member.')
    @app_commands.checks.cooldown(1,30,key=lambda i:(i.guild_id,i.user.id))
    async def tictactoe(i:discord.Interaction,opponent:discord.Member):
        await service.games.start(i,'tictactoe',opponent)

    @economy.command(name='profile',description='Show levels, currency, achievements, and your cosmetic profile title.')
    async def profile(i:discord.Interaction,member:discord.Member=None):
        await service.profiles.show(i,member)

    @economy.command(name='leaderboard',description='Show the top ten members who have not opted out.')
    async def leaderboard(i:discord.Interaction):
        if not await service.need(i,'xp'): return
        people=[(uid,p) for uid,p in store.profiles(i.guild_id) if p['visible'] and p.get('card_visibility',{}).get('xp',True) and i.guild.get_member(uid)]
        people.sort(key=lambda pair:pair[1]['xp'],reverse=True)
        await reply(i,'\n'.join(f'{n}. {i.guild.get_member(uid).display_name} — {p["xp"]} XP' for n,(uid,p) in enumerate(people[:10],1)) or 'No public profiles yet.')

    @economy.command(name='visibility',description='Opt out of public leaderboards and profile lookup, or opt back in.')
    async def visibility(i:discord.Interaction,public:bool):
        p=store.profile(i.guild_id,i.user.id); p['visible']=public; store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'Profile and leaderboard visibility: '+('public' if public else 'private'))

    @economy.command(name='daily',description='Claim 50 virtual coins once per UTC day.')
    async def daily(i:discord.Interaction):
        if not await service.need(i,'economy'): return
        p=store.profile(i.guild_id,i.user.id); day=dt.datetime.now(UTC).date().isoformat()
        if p.get('daily')==day: return await reply(i,'You already claimed today. Resets at midnight UTC.')
        p['daily']=day; p['coins']+=50; unlock(p,'Daily visitor'); store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'+50 virtual coins. They have no real-money value.')

    @economy.command(name='shop',description='List cosmetic profile titles and colors. No paid purchases.')
    async def shop(i:discord.Interaction):
        if not await service.need(i,'economy'): return
        await reply(i,'\n'.join(f'{key}: {item[1]} — {item[0]} coins' for key,item in SHOP.items())+'\nBuy with /economy buy; equip with /economy equip.')

    @economy.command(name='buy',description='Buy a profile cosmetic using virtual coins.')
    async def buy(i:discord.Interaction,item:str):
        if not await service.need(i,'economy'): return
        if item not in SHOP: return await reply(i,'Unknown item. See /economy shop.')
        p=store.profile(i.guild_id,i.user.id); price=SHOP[item][0]
        if item in p['owned']: return await reply(i,'You already own that item.')
        if p['coins']<price: return await reply(i,f'You need {price} coins.')
        p['coins']-=price; p['owned'].append(item); unlock(p,'Collector'); store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'Purchased! Use /economy equip to display it.')

    @economy.command(name='equip',description='Equip an owned cosmetic, or enter none to clear it.')
    async def equip(i:discord.Interaction,item:str):
        if not await service.need(i,'economy'): return
        p=store.profile(i.guild_id,i.user.id)
        if item!='none' and item not in p['owned']: return await reply(i,'You do not own that cosmetic.')
        p['equipped']='' if item=='none' else item; store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'Profile cosmetic updated. This changes bot profile cards, not Discord account appearance.')

    @tools.command(name='commands',description='Search the slash command menu by name or description.')
    async def commands_menu(i:discord.Interaction,search:str=''):
        rows=[]
        for command in bot.tree.walk_commands():
            if isinstance(command,app_commands.Group): continue
            parent=command.parent; perms=command.default_permissions or (parent.default_permissions if parent else None)
            if perms and not i.permissions.is_superset(perms): continue
            text=f'/{command.qualified_name} — {command.description}'
            if search.casefold() in text.casefold(): rows.append(text)
        await reply(i,('\n'.join(rows[:15]))[:1900] or 'No matching commands. Try a feature name like poll or role.')

    @tools.command(name='timezone',description='Convert an ISO local date/time between IANA timezones; reject DST ambiguity.')
    async def timezone(i:discord.Interaction,date_time:str,source:str,target:str):
        try:
            start=dt.datetime.fromisoformat(date_time)
            if start.tzinfo is not None: raise ValueError('Enter a local time without an offset: 2026-11-20T18:30.')
            zone=ZoneInfo(source); dest=ZoneInfo(target)
            a=start.replace(tzinfo=zone,fold=0); b=start.replace(tzinfo=zone,fold=1)
            if a.utcoffset()!=b.utcoffset(): raise ValueError('That local time is ambiguous or nonexistent due to daylight saving; choose a different time.')
            if a.astimezone(UTC).astimezone(zone).replace(tzinfo=None)!=start: raise ValueError('That time does not exist in the source timezone.')
            await reply(i,f'{a.isoformat()} ({source}) → {a.astimezone(dest).isoformat()} ({target})')
        except (ValueError,KeyError) as e: await reply(i,f'Invalid date/time or timezone: {e}. Use names such as America/New_York or Europe/London.')

    @tools.command(name='units',description='Convert compatible length, mass, volume, or temperature units.')
    async def units(i:discord.Interaction,value:float,source:str,target:str):
        import math
        try:
            if not math.isfinite(value): raise ValueError('Enter a finite number.')
            result=convert(value,source,target)
            await reply(i,f'{value:g} {source} = {result:g} {target}')
        except ValueError as e: await reply(i,str(e)+'\nSupported: m km cm ft in mi · kg g lb oz · l ml gal_us · C F K')

    @tools.command(name='translate',description='Translate supplied text using the configured external LibreTranslate service.')
    @app_commands.checks.cooldown(1,10,key=lambda i:(i.guild_id,i.user.id))
    async def translate(i:discord.Interaction,text:app_commands.Range[str,1,1000],target:str,source:str='auto'):
        if not await service.need(i,'translation'): return
        url=os.getenv('TRANSLATE_URL','').strip()
        if not url: return await reply(i,'The host must configure TRANSLATE_URL for a LibreTranslate-compatible service first.')
        if not re.fullmatch(r'[a-zA-Z-]{2,12}',target) or not re.fullmatch(r'[a-zA-Z-]{2,12}',source): return await reply(i,'Use language codes such as en, es, fr, or auto for source.')
        await i.response.defer(ephemeral=True)
        payload=dict(q=text,source=source,target=target,format='text')
        if os.getenv('TRANSLATE_API_KEY'): payload['api_key']=os.environ['TRANSLATE_API_KEY']
        try:
            async with service.session.post(url,json=payload,allow_redirects=False) as response:
                if response.status!=200: return await reply(i,'Translation provider rejected the request. Check its URL, supported languages and quota.')
                body=await response.json(); translated=body.get('translatedText')
                if not isinstance(translated,str): raise ValueError('Missing translation')
                await reply(i,translated[:1900])
        except (aiohttp.ClientError,asyncio.TimeoutError,ValueError):
            await reply(i,'Translation service is unavailable. No messages other than your supplied text are sent.')

    @tools.command(name='delete_data',description='Request deletion of your bot-held data; requires confirmation.')
    @app_commands.checks.cooldown(1,3600,key=lambda i:(i.guild_id,i.user.id))
    async def delete_data(i:discord.Interaction):
        await i.response.send_message('Delete your profile, birthday, AI memory and attributable votes, and ask staff to review moderation and other retained records? '
            'Staff will be asked to review retained transcripts, public messages, and backups. This does not undo Discord moderation.',
            view=DeleteView(service,i.user.id,i.guild_id),ephemeral=True)

    @ai.command(name='ask',description='Ask the optional AI in an approved channel. Text is sent to the configured model provider.')
    @app_commands.checks.cooldown(1,5,key=lambda i:(i.guild_id,i.user.id))
    async def ask(i:discord.Interaction,prompt:app_commands.Range[str,1,2000]):
        if not await service.need(i,'ai'): return
        if i.channel_id not in store.option(i.guild_id,'ai_channels',[]): return await reply(i,'AI is not allowed in this channel. An admin must set ai_channels.')
        base=os.getenv('AI_BASE_URL','').strip().rstrip('/'); model=os.getenv('AI_MODEL','').strip()
        if not base or not model: return await reply(i,'The host must set AI_BASE_URL and AI_MODEL. AI is optional; normal bot features need no AI key.')
        await i.response.defer(ephemeral=True)
        request_key=(i.guild_id,i.user.id)
        if request_key in service.ai_busy: return await reply(i,'Wait for your previous AI request to finish.')
        # Reserve quota before awaiting the provider so simultaneous requests cannot exceed it.
        day=dt.datetime.now(UTC).date().isoformat(); p=store.profile(i.guild_id,i.user.id)
        if p.get('ai_day')!=day: p.update(ai_day=day,ai_used=0)
        limit=store.option(i.guild_id,'ai_limit',20)
        if p.get('ai_used',0)>=limit: return await reply(i,f'AI daily limit reached ({limit} attempts). Resets at midnight UTC.')
        p['ai_used']=p.get('ai_used',0)+1
        turns=p['turns'] if p['memory'] and timestamp()-p.get('memory_at',0)<86400 else []
        store.save_profile(i.guild_id,i.user.id,p)
        service.ai_busy.add(request_key)
        generation=p.get('memory_generation',0)
        headers={}
        if os.getenv('AI_API_KEY'): headers['Authorization']='Bearer '+os.environ['AI_API_KEY']
        payload=dict(model=model,messages=[{'role':'system','content':'You are a helpful Discord community assistant. Do not claim to perform server actions.'}]+turns[-6:]+[{'role':'user','content':prompt}],max_tokens=500)
        try:
            async with service.session.post(base+'/chat/completions',json=payload,headers=headers,allow_redirects=False) as response:
                if response.status!=200: return await reply(i,'AI provider rejected the request. Check its model, credentials and quota.')
                data=await response.json(); answer=data['choices'][0]['message']['content']
                if not isinstance(answer,str): raise ValueError('Empty AI response')
        except (aiohttp.ClientError,asyncio.TimeoutError,ValueError,KeyError,IndexError,TypeError):
            return await reply(i,'AI provider unavailable. This attempt counts toward the daily limit; staff can disable AI at any time.')
        finally:
            service.ai_busy.discard(request_key)
        # Recheck switches/consent after the network call. Never recreate data after a deletion request.
        fresh=store.profile(i.guild_id,i.user.id)
        if not enabled(store,i.guild_id,'ai'): return await reply(i,'AI was disabled while the request was running. Response discarded.')
        if fresh['memory'] and fresh.get('memory_generation',0)==generation:
            fresh['turns']=(turns+[{'role':'user','content':prompt},{'role':'assistant','content':answer[:2000]}])[-6:]
            fresh['memory_at']=timestamp(); store.save_profile(i.guild_id,i.user.id,fresh)
        await reply(i,answer[:1900] or 'The model returned an empty answer.')

    @ai.command(name='memory',description='Opt into up to three AI conversation turns for 24 hours, or disable and erase them.')
    async def memory(i:discord.Interaction,enabled:bool):
        if enabled and not await service.need(i,'ai'): return
        p=store.profile(i.guild_id,i.user.id); p['memory']=enabled; p['memory_generation']=secrets.token_hex(8)
        if not enabled: p['turns']=[]; p['memory_at']=0; p['memory_generation']=secrets.token_hex(8)
        store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'AI memory enabled for your requests only; up to three turns, expiring after 24 hours.' if enabled else 'AI memory disabled and erased.')

    @ai.command(name='clear',description='Erase your stored AI conversation without changing other profile settings.')
    async def clear(i:discord.Interaction):
        p=store.profile(i.guild_id,i.user.id); p['turns']=[]; p['memory_at']=0; p['memory_generation']=secrets.token_hex(8)
        store.save_profile(i.guild_id,i.user.id,p)
        await reply(i,'Stored AI conversation cleared.')

    for group in [admin,mod,community,games,economy,tools,ai]: bot.tree.add_command(group)
