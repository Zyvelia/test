"""Private case reviews, support timelines, opt-in directories and durable reminders."""
import asyncio
import contextlib
import datetime as dt
import hashlib
import io
import json
import re
import secrets
import time
from pathlib import Path
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from .bot import reply, audit
from .features import enabled
from .policy import may_moderate

UTC=dt.timezone.utc

def reminder_time(text,zone='UTC',now=None):
    now=now or dt.datetime.now(UTC)
    match=re.fullmatch(r'(?:in\s+)?([1-9][0-9]{0,5})([mhd])',text.strip().lower())
    if match: due=now+dt.timedelta(seconds=int(match[1])*{'m':60,'h':3600,'d':86400}[match[2]])
    else:
        try: due=dt.datetime.fromisoformat(text.strip().replace('Z','+00:00'))
        except ValueError: raise ValueError('Use 10m, 2h, 3d or an ISO date/time, preferably with UTC offset.') from None
        if due.tzinfo is None:
            tz=ZoneInfo(zone); first=due.replace(tzinfo=tz,fold=0); second=due.replace(tzinfo=tz,fold=1)
            if first.utcoffset()!=second.utcoffset() or first.astimezone(UTC).astimezone(tz).replace(tzinfo=None)!=due:
                raise ValueError('This local time is ambiguous or nonexistent. Include a UTC offset.')
            due=first
    seconds=(due.astimezone(UTC)-now).total_seconds()
    if not 60<=seconds<=365*86400: raise ValueError('Choose a time from one minute to one year in the future.')
    return due.timestamp()

def remove_warning(store,guild,warning,actor,reason):
    if not 3<=len(reason.strip())<=1000: raise ValueError('Give an audit reason of 3–1,000 characters.')
    with store.db:
        row=store.db.execute('SELECT * FROM warnings WHERE guild=? AND id=?',(guild,warning)).fetchone()
        if row is None: raise ValueError('Warning not found in this server.')
        cursor=store.db.execute('INSERT INTO cases(guild,user,moderator,action,reason) VALUES (?,?,?,?,?)',(guild,row['user'],actor,'warning removed',f'Warning #{warning}; original moderator {row["moderator"]}; original reason: {row["reason"]}; removal reason: {reason.strip()}'))
        store.db.execute('DELETE FROM warnings WHERE guild=? AND id=?',(guild,warning))
    return cursor.lastrowid

def review_access(member,record,store):
    data=record['data']
    if member.id in {data['author'],data.get('target')}: return False
    role=store.option(record['guild'],'reviewer_role',0)
    return member.guild_permissions.administrator or bool(role and any(r.id==role for r in member.roles))

def ticket_event(store,guild,channel,actor,action,details):
    ticket=store.ticket_for_channel(channel)
    previous=store.db.execute('SELECT owner FROM ticket_events WHERE guild=? AND channel=? ORDER BY id DESC LIMIT 1',(guild,channel)).fetchone()
    owner=ticket['user'] if ticket and ticket['guild']==guild else previous['owner'] if previous else 0
    with store.db:
        store.db.execute('INSERT INTO ticket_events(guild,channel,owner,actor,action,details,at) VALUES (?,?,?,?,?,?,?)',(guild,channel,owner,actor,action,str(details)[:1500],time.time()))
        store.db.execute('DELETE FROM ticket_events WHERE guild=? AND channel=? AND id NOT IN (SELECT id FROM ticket_events WHERE guild=? AND channel=? ORDER BY id DESC LIMIT 200)',(guild,channel,guild,channel))

def timeline(store,guild,channel,user,staff=False):
    rows=store.db.execute('SELECT * FROM ticket_events WHERE guild=? AND channel=? ORDER BY id',(guild,channel)).fetchall()
    if not rows or not staff and rows[0]['owner']!=user: raise ValueError('This ticket timeline is unavailable to you.')
    return '\n'.join(f'{dt.datetime.fromtimestamp(r["at"],UTC).isoformat()} · {r["actor"]} · {r["action"]}: {r["details"]}' for r in rows)

class ReviewForm(discord.ui.Modal,title='Private staff review'):
    incident=discord.ui.TextInput(label='What happened?',style=discord.TextStyle.paragraph,min_length=10,max_length=1500)
    context=discord.ui.TextInput(label='When, where, and optional evidence links',style=discord.TextStyle.paragraph,max_length=1000)
    def __init__(self,suite,user,target,kind): super().__init__(); self.suite=suite; self.user=user; self.target=target; self.kind=kind
    async def on_submit(self,i):
        if i.user.id!=self.user or not await self.suite.service.need(i,'staff_reviews'): return
        if self.kind=='blocklist_appeal':
            listing=self.suite.store.record(f'blocklist:{i.guild_id}:{i.user.id}')
            if not listing or not listing['data'].get('active'): return await reply(i,'You do not have an active internal blocklist entry.')
        pending=[r for r in self.suite.store.records(i.guild_id,self.kind) if r['data']['author']==i.user.id and r['data']['status'] in {'pending','under_review'}]
        if len(pending)>=3: return await reply(i,'You already have three open submissions. Wait for a review.')
        ident=self.suite.store.put_record(i.guild_id,self.kind,dict(author=i.user.id,target=self.target,incident=str(self.incident),context=str(self.context),status='pending',created=time.time(),history=[]))
        await reply(i,f'Submission {ident} saved privately. Track it with /cases my_reviews.')
        channel=i.guild.get_channel(self.suite.store.option(i.guild_id,'review_channel',0))
        if isinstance(channel,discord.TextChannel) and not channel.permissions_for(i.guild.default_role).view_channel:
            with contextlib.suppress(discord.HTTPException): await channel.send(f'Private review awaiting an independent reviewer. Reference: `{ident}`. Use /cases review.',allowed_mentions=discord.AllowedMentions.none())

class LFGView(discord.ui.View):
    def __init__(self,suite,ident):
        super().__init__(timeout=None); self.suite=suite; self.ident=ident
        for action in ['Join','Leave','Close']:
            button=discord.ui.Button(label=action,custom_id=f'vivi:lfg:{ident}:{action}')
            async def callback(i,choice=action): await self.click(i,choice)
            button.callback=callback; self.add_item(button)
    async def click(self,i,action):
        if not await self.suite.service.need(i,'lfg'): return
        async with self.suite.lock:
            record=self.suite.store.record(self.ident)
            if not record or record['guild']!=i.guild_id: return await reply(i,'Board not found.')
            data=record['data']
            if data.get('closed') or data['expires']<=time.time(): return await reply(i,'This board is closed.')
            if action=='Close':
                if i.user.id!=data['owner'] and not i.user.guild_permissions.manage_messages: return await reply(i,'Only the host or staff may close this board.')
                data['closed']=True
            elif action=='Leave':
                if i.user.id==data['owner']: return await reply(i,'Use Close to end your board.')
                if i.user.id in data['members']: data['members'].remove(i.user.id)
            elif i.user.id not in data['members']:
                if len(data['members'])>=data['slots']: return await reply(i,'This group is full.')
                data['members'].append(i.user.id)
            self.suite.store.put_record(i.guild_id,'lfg',data,self.ident)
        await i.response.edit_message(content=self.suite.board_text(data),view=None if data.get('closed') else self,allowed_mentions=discord.AllowedMentions.none())

class Suite:
    def __init__(self,service): self.service=service; self.bot=service.bot; self.store=service.store; self.lock=asyncio.Lock(); self.task=None
    @staticmethod
    def board_text(data): return f'**LFG: {discord.utils.escape_markdown(data["game"])}**\n{discord.utils.escape_markdown(data["description"])}\nAvailability: {discord.utils.escape_markdown(data["availability"])}\n{len(data["members"])}/{data["slots"]} members: '+', '.join(f'<@{u}>' for u in data['members'])+f'\nExpires <t:{int(data["expires"])}:R>'+('\nClosed.' if data.get('closed') else '')
    def start(self):
        for row in self.store.records(kind='lfg'):
            if not row['data'].get('closed'): self.bot.add_view(LFGView(self,row['id']))
        self.task=asyncio.create_task(self.run(),name='vivi-personal-timers')
    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.task
    async def run(self):
        await self.bot.wait_until_ready()
        while True:
            try: await self.tick()
            except Exception as error: self.service.productivity.error('personal timers',error)
            await asyncio.sleep(15)
    async def tick(self):
        now=time.time(); delivered=0
        for row in self.store.records(kind='reminder'):
            data=row['data']
            if data.get('status')!='pending' or max(data['due'],data.get('retry',0))>now or not enabled(self.store,row['guild'],'reminders'): continue
            guild=self.bot.get_guild(row['guild'])
            if not guild: continue
            if delivered>=10: break
            delivered+=1
            try:
                member=await guild.fetch_member(data['user'])
                await member.send(f'Vivi reminder from {guild.name}:\n{data["text"]}',allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                data['attempts']=data.get('attempts',0)+1; data['retry']=now+300*data['attempts']
                if data['attempts']>=3: data['status']='failed'
                self.store.put_record(row['guild'],'reminder',data,row['id'])
            else: self.store.delete_record(row['id'])
        for row in self.store.records(kind='lfg'):
            data=row['data']
            if data.get('closed') and now>data['expires']+7*86400: self.store.delete_record(row['id']); continue
            if data.get('closed') or data['expires']>now: continue
            data['closed']=True; self.store.put_record(row['guild'],'lfg',data,row['id'])
            guild=self.bot.get_guild(row['guild']); channel=guild.get_channel(data['channel']) if guild else None
            if channel:
                with contextlib.suppress(discord.HTTPException): await (await channel.fetch_message(data['message'])).edit(content=self.board_text(data),view=None,allowed_mentions=discord.AllowedMentions.none())


def register_suite(bot):
    service=bot.community; suite=service.suite; store=bot.store
    cases=app_commands.Group(name='cases',description='Case evidence, independent reviews and internal blocklist appeals',guild_only=True)
    support=app_commands.Group(name='support',description='Ticket labels, activity and support availability',guild_only=True)
    social=app_commands.Group(name='social',description='Groups, timezones, reminders and command favorites',guild_only=True)
    async def moderate(i,permission='moderate_members'):
        if not getattr(i.user.guild_permissions,permission,False): await reply(i,'You lack the required moderation permission.'); return False
        return await service.need(i,'moderation')
    @cases.command(name='warning_remove',description='Remove a warning while keeping its reason and removal audit case.')
    @app_commands.default_permissions(moderate_members=True)
    async def warning_remove(i:discord.Interaction,warning_id:int,reason:str):
        if not await moderate(i): return
        row=store.db.execute('SELECT user FROM warnings WHERE guild=? AND id=?',(i.guild_id,warning_id)).fetchone()
        if row:
            target=i.guild.get_member(row['user'])
            if target and not may_moderate(i.user,target,i.guild.me,i.guild.owner_id): return await reply(i,'Role hierarchy prevents this action.')
        try: ident=remove_warning(store,i.guild_id,warning_id,i.user.id,reason)
        except ValueError as error: return await reply(i,str(error))
        await reply(i,f'Warning removed. Audit case #{ident} retains the original warning and removal reason.')
        await audit(bot,i.guild,f'Case #{ident}: warning #{warning_id} removed by {i.user.id}; reason: {reason[:1000]}')
    @cases.command(name='evidence_add',description='Save a private attachment against an existing case (max 8 MiB).')
    @app_commands.default_permissions(moderate_members=True)
    async def evidence_add(i:discord.Interaction,case_id:int,attachment:discord.Attachment,note:str=''):
        if not await moderate(i): return
        if not store.db.execute('SELECT 1 FROM cases WHERE guild=? AND id=?',(i.guild_id,case_id)).fetchone(): return await reply(i,'Case not found in this server.')
        suffix=Path(attachment.filename).suffix.lower()
        if suffix not in {'.png','.jpg','.jpeg','.webp','.txt','.pdf','.json'} or attachment.size>8*1024*1024 or len(note)>1000: return await reply(i,'Use PNG, JPEG, WebP, TXT, PDF or JSON under 8 MiB; note limit 1,000 characters.')
        await i.response.defer(ephemeral=True)
        async with suite.lock:
            if sum(r['data']['case']==case_id for r in store.records(i.guild_id,'case_evidence'))>=10: return await reply(i,'This case already has ten attachments.')
            data=await attachment.read()
            if len(data)>8*1024*1024: return await reply(i,'Attachment exceeds 8 MiB.')
            ident=secrets.token_hex(16); folder=store.path.parent/'evidence'/str(i.guild_id)/str(case_id); folder.mkdir(parents=True,exist_ok=True)
            path=folder/(ident+suffix)
            with path.open('xb') as file: file.write(data)
            path.chmod(0o600)
            store.put_record(i.guild_id,'case_evidence',dict(case=case_id,filename=attachment.filename[:120],suffix=suffix,note=note,actor=i.user.id,sha256=hashlib.sha256(data).hexdigest(),size=len(data)),ident)
        await reply(i,f'Evidence {ident} saved privately. Use /cases evidence_get.')
    @cases.command(name='evidence_list',description='List private evidence IDs for a case.')
    @app_commands.default_permissions(moderate_members=True)
    async def evidence_list(i:discord.Interaction,case_id:int):
        if not await moderate(i): return
        await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["filename"]} · {r["data"]["note"][:100]}' for r in store.records(i.guild_id,'case_evidence') if r['data']['case']==case_id) or 'No evidence in this server’s case.')
    @cases.command(name='evidence_get',description='Retrieve one case attachment privately after a permission check.')
    @app_commands.default_permissions(moderate_members=True)
    async def evidence_get(i:discord.Interaction,evidence_id:str):
        if not await moderate(i): return
        row=store.record(evidence_id)
        if not row or row['guild']!=i.guild_id or row['kind']!='case_evidence': return await reply(i,'Evidence not found.')
        data=row['data']; path=store.path.parent/'evidence'/str(i.guild_id)/str(data['case'])/(row['id']+data['suffix'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=data['sha256']: return await reply(i,'Evidence is missing or failed its integrity check. Ask the host administrator.')
        await i.response.send_message(f'Case #{data["case"]} · {data["note"][:1000]}',file=discord.File(path,filename=data['filename']),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    @cases.command(name='conduct',description='Submit a private staff conduct review form.')
    async def conduct(i:discord.Interaction,member:discord.Member):
        if not await service.need(i,'staff_reviews'): return
        config=store.settings(i.guild_id)
        if not (member.guild_permissions.manage_messages or member.guild_permissions.administrator or config and any(r.id==config['staff'] for r in member.roles)): return await reply(i,'Choose a staff member.')
        await i.response.send_modal(ReviewForm(suite,i.user.id,member.id,'staff_conduct'))
    @cases.command(name='blocklist',description='Manage Vivi’s internal member blocklist; this does not ban or unban.')
    @app_commands.default_permissions(ban_members=True)
    @app_commands.choices(action=[app_commands.Choice(name=x,value=x) for x in ['add','remove','view']])
    async def blocklist(i:discord.Interaction,member:discord.Member,action:str,reason:str=''):
        if not await moderate(i,'ban_members'): return
        ident=f'blocklist:{i.guild_id}:{member.id}'; row=store.record(ident)
        if action=='view': return await reply(i,str(row['data']) if row else 'No internal blocklist entry.')
        if len(reason.strip())<3 or len(reason)>1000: return await reply(i,'A reason of 3–1,000 characters is required.')
        if not may_moderate(i.user,member,i.guild.me,i.guild.owner_id): return await reply(i,'Role hierarchy prevents this action.')
        history=row['data'].get('history',[]) if row else []
        history.append(dict(action=action,actor=i.user.id,reason=reason,at=time.time()))
        store.put_record(i.guild_id,'blocklist',dict(user=member.id,active=action=='add',reason=reason,history=history[-50:]),ident)
        await reply(i,'Internal blocklist updated. Discord ban status is unchanged.')
    @cases.command(name='blocklist_appeal',description='Appeal your own active internal blocklist entry.')
    async def blocklist_appeal(i:discord.Interaction):
        if not await service.need(i,'staff_reviews'): return
        row=store.record(f'blocklist:{i.guild_id}:{i.user.id}')
        if not row or not row['data']['active']: return await reply(i,'You have no active internal blocklist entry.')
        await i.response.send_modal(ReviewForm(suite,i.user.id,i.user.id,'blocklist_appeal'))
    @cases.command(name='reviews',description='List pending reviews accessible to you as an independent reviewer.')
    async def reviews(i:discord.Interaction):
        rows=[r for r in store.records(i.guild_id) if r['kind'] in {'staff_conduct','blocklist_appeal'} and review_access(i.user,r,store)]
        await reply(i,'\n'.join(f'{r["id"]}: {r["kind"]} · {r["data"]["status"]}' for r in rows[-20:]) or 'No accessible reviews.')
    @cases.command(name='review',description='Read a private review or record a review decision with a reason.')
    @app_commands.choices(status=[app_commands.Choice(name=x,value=x) for x in ['read','under_review','accepted','declined']])
    async def review(i:discord.Interaction,review_id:str,status:str='read',reason:str=''):
        row=store.record(review_id)
        if not row or row['guild']!=i.guild_id or row['kind'] not in {'staff_conduct','blocklist_appeal'} or not review_access(i.user,row,store): return await reply(i,'This review is unavailable to you. Authors and subjects cannot review their own case.')
        data=row['data']
        if status!='read':
            if not 3<=len(reason.strip())<=1000: return await reply(i,'Give a review reason of 3–1,000 characters.')
            if data['status'] in {'accepted','declined'}: return await reply(i,'This review has a final decision.')
            data['status']=status; data['response']=reason; data['history'].append(dict(actor=i.user.id,status=status,reason=reason,at=time.time()))
            store.put_record(i.guild_id,row['kind'],data,row['id'])
            if status=='accepted' and row['kind']=='blocklist_appeal':
                listing=store.record(f'blocklist:{i.guild_id}:{data["author"]}')
                if listing:
                    listing['data']['active']=False; listing['data']['history'].append(dict(action='appeal accepted',actor=i.user.id,reason=reason,at=time.time())); store.put_record(i.guild_id,'blocklist',listing['data'],listing['id'])
        await i.response.send_message(f'Review {review_id} · {data["status"]}',file=discord.File(io.BytesIO(json.dumps(data,indent=2).encode()),filename='private-review.json'),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    @cases.command(name='my_reviews',description='Privately check your own submissions and review responses.')
    async def my_reviews(i:discord.Interaction):
        rows=[r for r in store.records(i.guild_id) if r['kind'] in {'staff_conduct','blocklist_appeal'} and r['data']['author']==i.user.id]
        await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["status"]} · {r["data"].get("response","Awaiting review")[:300]}' for r in rows[-10:]) or 'No submissions.')
    @support.command(name='tags',description='Set up to eight ticket labels, separated by commas.')
    async def tags(i:discord.Interaction,labels:str=''):
        if not await service.need(i,'ticket_tools'): return
        if not service.operations.staff(i) or not store.ticket_for_channel(i.channel_id): return await reply(i,'Use this in a ticket as support staff.')
        tags=list(dict.fromkeys(x.strip() for x in labels.split(',') if x.strip()))
        if len(tags)>8 or any(not re.fullmatch(r'[\w -]{1,24}',x) for x in tags): return await reply(i,'Use up to eight labels of 1–24 letters, digits, spaces, dashes or underscores.')
        data=service.operations.ticket_meta(i.channel_id); data['tags']=tags; service.operations.save_ticket_meta(i.guild_id,i.channel_id,data,actor=i.user.id)
        await reply(i,'Ticket labels saved: '+', '.join(tags))
    @support.command(name='timeline',description='Download a ticket activity timeline as its owner or support staff.')
    async def ticket_timeline(i:discord.Interaction,ticket_id:str=''):
        try: channel=int(ticket_id) if ticket_id else i.channel_id; text=timeline(store,i.guild_id,channel,i.user.id,service.operations.staff(i))
        except (ValueError,TypeError) as error: return await reply(i,str(error))
        await i.response.send_message(file=discord.File(io.BytesIO(text.encode()),filename='ticket-timeline.txt'),ephemeral=True)
    @support.command(name='availability',description='Set your support availability; hidden removes you from the directory.')
    @app_commands.choices(status=[app_commands.Choice(name=x,value=x) for x in ['available','busy','away','hidden']])
    async def availability(i:discord.Interaction,status:str):
        if not service.operations.staff(i): return await reply(i,'This command is for current support staff.')
        profile=store.profile(i.guild_id,i.user.id); profile['support_availability']=status; store.save_profile(i.guild_id,i.user.id,profile)
        await reply(i,'Support availability saved.')
    @support.command(name='staff',description='Show current support staff who opted to share availability.')
    async def staff(i:discord.Interaction):
        config=store.settings(i.guild_id); lines=[]
        for user,profile in store.profiles(i.guild_id):
            member=i.guild.get_member(user); status=profile.get('support_availability','hidden')
            if member and status!='hidden' and (member.guild_permissions.manage_channels or config and any(r.id==config['staff'] for r in member.roles)): lines.append(f'{member.display_name}: {status}')
        await reply(i,'\n'.join(lines[:30]) or 'No staff availability shared.')
    @social.command(name='timezone',description='Set an IANA timezone; directory sharing is explicitly opt-in.')
    async def timezone(i:discord.Interaction,zone:str,public:bool=False):
        try: ZoneInfo(zone)
        except (KeyError,ValueError): return await reply(i,'Use an IANA timezone such as Europe/London or America/New_York.')
        if public and not await service.need(i,'timezone_directory'): return
        profile=store.profile(i.guild_id,i.user.id); profile.update(timezone_selected=zone,directory_optin=public); store.save_profile(i.guild_id,i.user.id,profile)
        await reply(i,'Timezone saved. Directory visibility: '+('opted in.' if public else 'private.'))
    @social.command(name='timezones',description='Browse consenting current members’ local times, without exact locations.')
    async def timezones(i:discord.Interaction,search:str=''):
        if not await service.need(i,'timezone_directory'): return
        lines=[]
        for user,profile in store.profiles(i.guild_id):
            member=i.guild.get_member(user)
            if member and profile.get('directory_optin') and search.lower() in member.display_name.lower(): lines.append(f'{member.display_name}: {dt.datetime.now(ZoneInfo(profile["timezone_selected"])).strftime("%a %H:%M %Z")}')
        await reply(i,'\n'.join(lines[:20]) or 'No matching members have opted in.')
    @social.command(name='remind',description='Create a private reminder: 10m, 2h, 3d or ISO date/time.')
    async def remind(i:discord.Interaction,when:str,text:str):
        if not await service.need(i,'reminders'): return
        if not 1<=len(text)<=1000: return await reply(i,'Reminder text must be 1–1,000 characters.')
        if sum(r['data']['user']==i.user.id for r in store.records(i.guild_id,'reminder'))>=10: return await reply(i,'You already have ten reminders; cancel one first.')
        try: due=reminder_time(when,store.profile(i.guild_id,i.user.id).get('timezone_selected',store.option(i.guild_id,'timezone','UTC')))
        except ValueError as error: return await reply(i,str(error))
        ident=store.put_record(i.guild_id,'reminder',dict(user=i.user.id,text=text,due=due,status='pending',attempts=0))
        await reply(i,f'Reminder {ident} scheduled for <t:{int(due)}:F>. Enable DMs from this server. Delivery may be delayed while Vivi is offline.')
    @social.command(name='reminders',description='Privately list your pending and failed reminders.')
    async def reminders(i:discord.Interaction): await reply(i,'\n'.join(f'{r["id"]}: <t:{int(r["data"]["due"])}:F> · {r["data"]["status"]} · {r["data"]["text"][:100]}' for r in store.records(i.guild_id,'reminder') if r['data']['user']==i.user.id) or 'No reminders.')
    @social.command(name='reminder_cancel',description='Cancel one of your own reminders.')
    async def reminder_cancel(i:discord.Interaction,reminder_id:str):
        row=store.record(reminder_id)
        if not row or row['kind']!='reminder' or row['guild']!=i.guild_id or row['data']['user']!=i.user.id: return await reply(i,'Reminder not found.')
        store.delete_record(reminder_id); await reply(i,'Reminder cancelled.')
    @social.command(name='favorite',description='Add or remove a private command shortcut reference.')
    async def favorite(i:discord.Interaction,command:str,remove:bool=False):
        name=command.strip().lstrip('/'); known={' '.join(c.qualified_name.split()) for c in bot.tree.walk_commands() if isinstance(c,app_commands.Command)}
        if name not in known: return await reply(i,'Use an existing slash command name, for example social reminders.')
        profile=store.profile(i.guild_id,i.user.id); values=profile.get('favorites',[])
        if remove: values=[x for x in values if x!=name]
        elif name not in values:
            if len(values)>=20: return await reply(i,'Maximum twenty favorites.')
            values.append(name)
        profile['favorites']=values; store.save_profile(i.guild_id,i.user.id,profile); await reply(i,'Favorites saved. Command permissions still apply.')
    @social.command(name='favorites',description='Show your private list of favorite command names.')
    async def favorites(i:discord.Interaction): await reply(i,'\n'.join('/'+x for x in store.profile(i.guild_id,i.user.id).get('favorites',[])) or 'No favorites yet. Use /social favorite.')
    @social.command(name='lfg',description='Publish an expiring looking-for-group board with Join/Leave buttons.')
    async def lfg(i:discord.Interaction,game:app_commands.Range[str,1,80],availability:app_commands.Range[str,1,100],slots:app_commands.Range[int,2,10],description:app_commands.Range[str,1,500]):
        if not await service.need(i,'lfg'): return
        channel=i.guild.get_channel(store.option(i.guild_id,'lfg_channel',0))
        if not isinstance(channel,discord.TextChannel): return await reply(i,'An admin must configure lfg_channel first.')
        async with suite.lock:
            rows=[r for r in store.records(i.guild_id,'lfg') if not r['data'].get('closed') and r['data']['expires']>time.time()]
            if len(rows)>=50 or any(r['data']['owner']==i.user.id for r in rows): return await reply(i,'You already host a group, or this server has fifty active groups.')
            await i.response.defer(ephemeral=True)
            data=dict(owner=i.user.id,members=[i.user.id],game=game,availability=availability,description=description,slots=slots,expires=time.time()+store.option(i.guild_id,'lfg_hours',24)*3600,channel=channel.id,message=0,closed=False)
            ident=store.put_record(i.guild_id,'lfg',data)
            try: message=await channel.send(suite.board_text(data),view=LFGView(suite,ident),allowed_mentions=discord.AllowedMentions.none())
            except Exception: store.delete_record(ident); raise
            data['message']=message.id; store.put_record(i.guild_id,'lfg',data,ident)
        await reply(i,'Group posted: '+message.jump_url)
    @social.command(name='lfg_find',description='Find open groups by game name.')
    async def lfg_find(i:discord.Interaction,game:str=''):
        if not await service.need(i,'lfg'): return
        await reply(i,'\n'.join(f'{r["data"]["game"]} · {len(r["data"]["members"])}/{r["data"]["slots"]} · https://discord.com/channels/{i.guild_id}/{r["data"]["channel"]}/{r["data"]["message"]}' for r in store.records(i.guild_id,'lfg') if not r['data'].get('closed') and r['data']['expires']>time.time() and game.lower() in r['data']['game'].lower())[:1800] or 'No matching groups.')
    admin=bot.tree.get_command('admin')
    @admin.command(name='updates',description='Check published Vivi releases without installing anything.')
    @app_commands.default_permissions(administrator=True)
    async def updates(i:discord.Interaction):
        if not i.user.guild_permissions.administrator: return await reply(i,'Only server administrators may check release information.')
        await i.response.defer(ephemeral=True)
        from .updates import check_updates
        try: result=await check_updates(service)
        except Exception: return await reply(i,'The release service is unavailable. Check host network access and update configuration.')
        await reply(i,result)
    for group in [cases,support,social]: bot.tree.add_command(group)
