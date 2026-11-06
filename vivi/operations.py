"""Advanced moderation, ticket staff tools, and scheduled external notifications."""
import asyncio
import contextlib
import datetime as dt
import logging
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict, deque

import discord
from discord import app_commands
from .bot import reply, audit
from .features import enabled
from .policy import may_moderate

LOG=logging.getLogger('vivi.operations')


def subscription(provider,source,channel,filters=None):
    source=source.strip()
    patterns={'steam':r'[1-9][0-9]{0,9}', 'webhook':r'[A-Za-z0-9_-]{1,64}', 'twitch':r'[A-Za-z0-9_]{1,25}', 'youtube':r'UC[A-Za-z0-9_-]{22}',
              'github_releases':r'[A-Za-z0-9_-]{1,39}/[A-Za-z0-9_.-]{1,100}',
              'github_commits':r'[A-Za-z0-9_-]{1,39}/[A-Za-z0-9_.-]{1,100}'}
    if provider not in patterns or not re.fullmatch(patterns[provider],source) or source.split('/')[-1] in {'.','..'}:
        raise ValueError('Use a Twitch login, YouTube UC channel ID, or GitHub owner/repository (no URLs).')
    from .customization import filters_for
    return dict(provider=provider,source=source,channel=channel,filters=filters_for(provider,filters),initialized=False,last=None,next_poll=0)


class TicketCategoryView(discord.ui.View):
    def __init__(self,bot,categories):
        super().__init__(timeout=120); self.bot=bot
        menu=discord.ui.Select(placeholder='Choose your support category',options=[discord.SelectOption(label=x,value=x) for x in categories])
        menu.callback=self.choose; self.add_item(menu)
    async def choose(self,i):
        from .bot import OpenTicketView
        await OpenTicketView(self.bot).create_ticket(i,i.data['values'][0])
        self.stop()


class RatingView(discord.ui.View):
    def __init__(self,ops,ident):
        super().__init__(timeout=None); self.ops=ops; self.ident=ident
        for score in range(1,6):
            button=discord.ui.Button(label=f'{score} ★',custom_id=f'vivi:rating:{ident}:{score}')
            async def callback(i,value=score): await self.rate(i,value)
            button.callback=callback; self.add_item(button)
    async def rate(self,i,score):
        record=self.ops.store.record(self.ident)
        if not record or i.user.id!=record['data']['user']: return await reply(i,'This feedback request belongs to another member.')
        data=record['data']
        if data.get('rating'): return await reply(i,'Your rating is already recorded. Thank you!')
        if data['expires']<time.time(): return await reply(i,'This rating request has expired.')
        data['rating']=score; self.ops.store.put_record(record['guild'],'ticket_rating',data,self.ident)
        await reply(i,f'Thank you! Your {score}/5 rating was shared with support staff.')
        guild=self.ops.bot.get_guild(record['guild'])
        if guild: await audit(self.ops.bot,guild,f'Ticket {data["channel"]}: {score}/5 from owner {data["user"]}; claimed by {data.get("claimed",0)}.')


class Operations:
    def __init__(self,service):
        self.service=service; self.bot=service.bot; self.store=service.store
        self.joins=defaultdict(deque); self.twitch_token=None; self.twitch_expiry=0

    def ticket_meta(self,channel):
        record=self.store.record(f'ticket:{channel}')
        data=record['data'] if record else dict(category='General',priority='normal',claimed=0)
        data.setdefault('tags',[])
        return data

    def save_ticket_meta(self,guild,channel,data,actor=0):
        from .suite import ticket_event
        old=self.store.record(f'ticket:{channel}')
        changes={key:value for key,value in data.items() if not old or old['data'].get(key)!=value}
        if changes: ticket_event(self.store,guild,channel,actor,'updated' if old else 'opened',json.dumps(changes))
        self.store.put_record(guild,'ticket_meta',data,f'ticket:{channel}')

    def staff(self,i):
        config=self.store.settings(i.guild_id)
        return config and (i.user.guild_permissions.manage_channels or any(r.id==config['staff'] for r in i.user.roles))

    async def closed(self,guild,ticket):
        from .suite import ticket_event
        ticket_event(self.store,guild.id,ticket['channel'],0,'closed','Channel deleted; transcript retained')
        data=self.ticket_meta(ticket['channel']); self.store.delete_record(f'ticket:{ticket["channel"]}')
        if not enabled(self.store,guild.id,'ticket_tools'): return
        data.update(user=ticket['user'],channel=ticket['channel'],expires=time.time()+7*86400,rating=0)
        ident=self.store.put_record(guild.id,'ticket_rating',data)
        try:
            member=await guild.fetch_member(ticket['user'])
            await member.send('Your support ticket has closed. How was your experience? (1 = poor, 5 = excellent.) '
                              'Your rating is visible to staff, not anonymous. This request expires in seven days.',view=RatingView(self,ident))
        except discord.HTTPException: LOG.info('Ticket rating DM unavailable for ticket %s',ticket['channel'])

    async def on_join(self,member):
        guild=member.guild
        if not enabled(self.store,guild.id,'raid_protection'): return
        now=time.time(); window=self.store.option(guild.id,'raid_window',30); recent=self.joins[guild.id]
        while recent and now-recent[0]>window: recent.popleft()
        recent.append(now)
        if len(recent)<self.store.option(guild.id,'raid_limit',8) or self.store.option(guild.id,'internal_raid_until',0)>now: return
        self.store.set_option(guild.id,'internal_raid_until',now+300)
        await self.service.case(guild,0,self.bot.user.id,'raid alert',f'{len(recent)} joins in {window}s. Automatic newcomer roles paused for five minutes.')
        if self.store.option(guild.id,'raid_action','alert')=='lockdown':
            channel=guild.get_channel(self.store.option(guild.id,'raid_channel',0))
            if not isinstance(channel,discord.TextChannel): return
            async with self.service.lock:
                if any(r['data']['channel']==channel.id for r in self.store.records(guild.id,'lockdown')): return
                overwrite=channel.overwrites_for(guild.default_role)
                ident=self.store.put_record(guild.id,'lockdown',dict(channel=channel.id,previous=overwrite.send_messages,
                    until=now+self.store.option(guild.id,'raid_lock_minutes',5)*60))
                overwrite.send_messages=False
                try: await channel.set_permissions(guild.default_role,overwrite=overwrite,reason='Vivi optional raid protection')
                except discord.HTTPException:
                    self.store.delete_record(ident); LOG.warning('Raid lockdown lacked channel permission in %s',guild.id)

    async def warning_threshold(self,guild,member,moderator):
        if not enabled(self.store,guild.id,'warning_thresholds'): return
        count=self.store.db.execute("SELECT COUNT(*),MAX(id) FROM warnings WHERE guild=? AND user=? AND created>=datetime('now',?)",
            (guild.id,member.id,f'-{self.store.option(guild.id,"warning_window_days",30)} days')).fetchone()
        limit=self.store.option(guild.id,'warning_count',3)
        if count[0]<limit or count[0]%limit: return
        key=f'internal_warning:{member.id}'
        if self.store.option(guild.id,key,0)==count[1]: return
        actor=guild.get_member(moderator)
        if not actor or not may_moderate(actor,member,guild.me,guild.owner_id): return
        minutes=self.store.option(guild.id,'warning_timeout_minutes',10)
        try:
            await member.timeout(dt.timedelta(minutes=minutes),reason=f'Vivi warning threshold: {count[0]} recent warnings')
            self.store.set_option(guild.id,key,count[1])
            await self.service.case(guild,member.id,self.bot.user.id,'warning threshold timeout',f'{count[0]} recent warnings; {minutes} minutes',member)
        except discord.HTTPException: await audit(self.bot,guild,f'Warning threshold reached for {member.id}, but Discord refused the timeout. Check role hierarchy and Moderate Members permission.')

    async def events(self,data,guild_id=None):
        """Fetch provider metadata from fixed hosts only. Never follow credential-bearing redirects."""
        session=self.service.session; provider=data['provider']; source=data['source']
        if provider=='steam':
            async with session.get('https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/',params={'appid':source,'count':5,'maxlength':0},allow_redirects=False) as response:
                if response.status!=200: raise ValueError(f'Steam returned HTTP {response.status}.')
                payload=await response.json()
            return [dict(id=str(x['gid']),title=x.get('title','Steam news'),url=x['url']) for x in payload.get('appnews',{}).get('newsitems',[])][:5]
        if provider.startswith('github_'):
            headers={'Accept':'application/vnd.github+json','User-Agent':'Vivi-Discord-Bot'}
            bindings=json.loads(os.getenv('NOTIFY_GITHUB_ACCESS','{}'))
            allowed=bindings.get(str(guild_id),[]) if isinstance(bindings,dict) else []
            if os.getenv('NOTIFY_GITHUB_TOKEN') and source.lower() in [str(x).lower() for x in allowed]:
                headers['Authorization']='Bearer '+os.environ['NOTIFY_GITHUB_TOKEN']
            path='releases?per_page=5' if provider=='github_releases' else 'commits?per_page=5'
            from urllib.parse import urlencode
            if provider=='github_commits' and data.get('filters',{}).get('branch'): path+='&'+urlencode({'sha':data['filters']['branch']})
            async with session.get(f'https://api.github.com/repos/{source}/{path}',headers=headers,allow_redirects=False) as response:
                if response.status!=200: raise ValueError(f'GitHub returned HTTP {response.status}; check source, credentials or API limits.')
                rows=await response.json()
            if provider=='github_releases':
                return [dict(id=str(x['id']),title=x.get('name') or x['tag_name'],url=x['html_url'],tag=x['tag_name'],category='prerelease' if x.get('prerelease') else 'release') for x in rows if not x.get('draft')]
            return [dict(id=x['sha'],title=x['commit']['message'].split('\n')[0],url=x['html_url'],branch=data.get('filters',{}).get('branch','')) for x in rows]
        if provider=='youtube':
            async with session.get('https://www.youtube.com/feeds/videos.xml',params={'channel_id':source},allow_redirects=False) as response:
                if response.status!=200: raise ValueError(f'YouTube returned HTTP {response.status}. Check the UC channel ID.')
                body=await response.content.read(1_048_577)
                if len(body)>1_048_576: raise ValueError('YouTube feed exceeded the size limit.')
            root=ET.fromstring(body); ns={'a':'http://www.w3.org/2005/Atom','yt':'http://www.youtube.com/xml/schemas/2015'}
            return [dict(id=x.findtext('yt:videoId',namespaces=ns),title=x.findtext('a:title',default='New upload',namespaces=ns),
                         url='https://www.youtube.com/watch?v='+x.findtext('yt:videoId',default='',namespaces=ns))
                    for x in root.findall('a:entry',ns)][:5]
        if provider=='twitch':
            if not os.getenv('TWITCH_CLIENT_ID') or not os.getenv('TWITCH_CLIENT_SECRET'): raise ValueError('Twitch client ID and secret are not configured.')
            if not self.twitch_token or time.time()>=self.twitch_expiry:
                async with session.post('https://id.twitch.tv/oauth2/token',data={'client_id':os.environ['TWITCH_CLIENT_ID'],
                        'client_secret':os.environ['TWITCH_CLIENT_SECRET'],'grant_type':'client_credentials'},allow_redirects=False) as response:
                    if response.status!=200: raise ValueError('Twitch app authentication failed.')
                    token=await response.json()
                self.twitch_token=token['access_token']; self.twitch_expiry=time.time()+int(token['expires_in'])-60
            headers={'Client-ID':os.environ['TWITCH_CLIENT_ID'],'Authorization':'Bearer '+self.twitch_token}
            async with session.get('https://api.twitch.tv/helix/streams',params={'user_login':source},headers=headers,allow_redirects=False) as response:
                if response.status==401: self.twitch_expiry=0
                if response.status!=200: raise ValueError(f'Twitch returned HTTP {response.status}.')
                body=await response.json()
            return [dict(id=x['id'],title=x['title'],url='https://www.twitch.tv/'+source,category=x.get('game_name','')) for x in body['data']]
        raise ValueError('Unsupported provider.')

    async def poll_notifications(self):
        for record in self.store.records(kind='notification'):
            guild=self.bot.get_guild(record['guild']); data=record['data']
            if data['provider']=='webhook': continue
            if not guild or not enabled(self.store,guild.id,'notifications') or data.get('next_poll',0)>time.time(): continue
            try:
                events=await self.events(data,guild.id)
                if not self.store.record(record['id']) or not enabled(self.store,guild.id,'notifications'): continue
                complete=True
                if data.get('initialized'):
                    fresh=[]
                    for event in events:
                        if event['id']==data.get('last'): break
                        fresh.append(event)
                    channel=guild.get_channel(data['channel'])
                    if not channel: raise ValueError('Notification destination is missing.')
                    for event in reversed(fresh):
                        from .customization import accepts
                        if not accepts(data,event): continue
                        if not self.store.record(record['id']) or not enabled(self.store,guild.id,'notifications'): complete=False; break
                        await channel.send(f'**{data["provider"]}: {data["source"]}**\n{event["title"][:300]}\n{event["url"]}',
                                           allowed_mentions=discord.AllowedMentions.none())
                        data['last']=event['id']
                        if self.store.record(record['id']): self.store.put_record(record['guild'],'notification',data,record['id'])
                data.update(initialized=True,last=(events[0]['id'] if events else None) if complete else data.get('last'),next_poll=time.time()+300,error='')
            except Exception as error:
                # Store only a bounded diagnostic class, never HTTP bodies or credential-bearing request objects.
                data.update(next_poll=time.time()+600,error=type(error).__name__)
                LOG.warning('Notification %s failed (%s); retry in 10 minutes',record['id'],type(error).__name__)
            if self.store.record(record['id']): self.store.put_record(record['guild'],'notification',data,record['id'])


def register_operations(bot):
    service=bot.community; ops=service.operations; store=bot.store
    tickets=app_commands.Group(name='ticket',description='Ticket claiming, category and priority',guild_only=True)
    notify=app_commands.Group(name='notify',description='External notifications',guild_only=True,
                              default_permissions=discord.Permissions(administrator=True))
    async def staff(i):
        if not await service.need(i,'ticket_tools'): return False
        if not ops.staff(i): raise app_commands.MissingPermissions(['manage_channels or configured support role'])
        if not store.ticket_for_channel(i.channel_id): await reply(i,'Run this inside an open support ticket.'); return False
        return True
    async def admin(i):
        if not i.user.guild_permissions.administrator: raise app_commands.MissingPermissions(['administrator'])
        return True

    @tickets.command(name='claim',description='Claim this ticket for yourself; another staff member cannot steal the claim.')
    async def claim(i:discord.Interaction):
        if not await staff(i): return
        await i.response.defer(ephemeral=True)
        async with bot.ticket_lock:
            data=ops.ticket_meta(i.channel_id)
            if data['claimed'] and data['claimed']!=i.user.id: return await reply(i,f'Already claimed by <@{data["claimed"]}>. They can release it, or a channel manager can use /ticket release.')
            data['claimed']=i.user.id; ops.save_ticket_meta(i.guild_id,i.channel_id,data,actor=i.user.id)
        await reply(i,'Ticket claimed.'); await audit(bot,i.guild,f'Ticket {i.channel_id} claimed by {i.user.id}.')

    @tickets.command(name='release',description='Release your claim, or override a claim with Manage Channels.')
    async def release(i:discord.Interaction):
        if not await staff(i): return
        async with bot.ticket_lock:
            data=ops.ticket_meta(i.channel_id)
            if data['claimed'] not in {0,i.user.id} and not i.user.guild_permissions.manage_channels: return await reply(i,'Only the claimant or a channel manager can release this ticket.')
            data['claimed']=0; ops.save_ticket_meta(i.guild_id,i.channel_id,data,actor=i.user.id)
        await reply(i,'Ticket released.')

    @tickets.command(name='priority',description='Set this ticket’s staff priority.')
    @app_commands.choices(value=[app_commands.Choice(name=x,value=x) for x in ['low','normal','high','urgent']])
    async def priority(i:discord.Interaction,value:str):
        if not await staff(i): return
        if value not in {'low','normal','high','urgent'}: return await reply(i,'Invalid priority.')
        async with bot.ticket_lock:
            data=ops.ticket_meta(i.channel_id); data['priority']=value; ops.save_ticket_meta(i.guild_id,i.channel_id,data,actor=i.user.id)
        await reply(i,f'Priority: {value}.'); await audit(bot,i.guild,f'Ticket {i.channel_id} priority set to {value} by {i.user.id}.')

    @tickets.command(name='category',description='Move this ticket to a configured support category, preserving its privacy overwrites.')
    async def category(i:discord.Interaction,label:str):
        if not await staff(i): return
        categories=store.option(i.guild_id,'ticket_categories',{})
        target=i.guild.get_channel(categories.get(label,0))
        if not isinstance(target,discord.CategoryChannel): return await reply(i,'Choose a configured ticket_categories label.')
        await i.response.defer(ephemeral=True)
        async with bot.ticket_lock:
            await i.channel.edit(category=target,sync_permissions=False,reason=f'Vivi ticket category by {i.user.id}')
            data=ops.ticket_meta(i.channel_id); data['category']=label; ops.save_ticket_meta(i.guild_id,i.channel_id,data,actor=i.user.id)
        await reply(i,'Category updated; ticket privacy permissions were preserved.')

    @tickets.command(name='status',description='Show this ticket’s category, priority and claimant.')
    async def status(i:discord.Interaction):
        ticket=store.ticket_for_channel(i.channel_id); config=store.settings(i.guild_id)
        if not ticket or not config or (ticket['user']!=i.user.id and not ops.staff(i)): return await reply(i,'Only the ticket owner or staff can inspect this ticket.')
        data=ops.ticket_meta(i.channel_id)
        await reply(i,f'Category: {data["category"]}\nPriority: {data["priority"]}\nClaimed by: {data["claimed"] or "unclaimed"}')

    @notify.command(name='add',description='Watch a Twitch login, YouTube UC channel ID, or GitHub owner/repository.')
    @app_commands.check(admin)
    @app_commands.choices(provider=[app_commands.Choice(name=x,value=x) for x in ['twitch','youtube','github_releases','github_commits','webhook','steam']])
    async def add(i:discord.Interaction,provider:str,source:str,channel:discord.TextChannel):
        if not await service.need(i,'notifications'): return
        if len(store.records(i.guild_id,'notification'))>=20: return await reply(i,'Maximum 20 subscriptions per server.')
        data=subscription(provider,source,channel.id)
        ident=store.put_record(i.guild_id,'notification',data)
        await reply(i,f'Subscription {ident} saved. The first successful poll establishes a baseline; future events trigger notifications.')

    @notify.command(name='list',description='List subscriptions, destination channels, and last polling status.')
    @app_commands.check(admin)
    async def list_subscriptions(i:discord.Interaction):
        await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["provider"]} {r["data"]["source"]} → {r["data"]["channel"]}; {r["data"].get("error") or "no recorded error"}' for r in store.records(i.guild_id,'notification')) or 'No subscriptions yet.')

    @notify.command(name='remove',description='Remove one external notification subscription.')
    @app_commands.check(admin)
    async def remove(i:discord.Interaction,ident:str):
        record=store.record(ident)
        if not record or record['guild']!=i.guild_id or record['kind']!='notification': return await reply(i,'Subscription not found in this server.')
        store.delete_record(ident); await reply(i,'Subscription removed.')

    bot.tree.add_command(tickets); bot.tree.add_command(notify)
