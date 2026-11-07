"""Consensual team membership, recruitment applications and searchable member libraries."""
import io
import json
import time
import discord
from discord import app_commands
from vivi.bot import reply
from vivi.core.features import enabled,blocked_word,suspicious_link


def clean_text(store,guild,text):
    if blocked_word(text,store.option(guild,'blocked_words',[])) or suspicious_link(text,store.option(guild,'blocked_domains',[])):raise ValueError('That content conflicts with this server’s word or link filters.')
    return text


def scoped(store,guild,ident,kind):
    row=store.record(ident)
    if not row or row['guild']!=guild or row['kind']!=kind:raise ValueError('Item not found in this server.')
    return row


def team_manager(i,data):return i.user.id==data['captain'] or i.user.guild_permissions.manage_guild

class TeamPanel(discord.ui.View):
    def __init__(self,service,ident,kind):
        super().__init__(timeout=None);self.service=service;self.ident=ident;self.kind=kind
        button=discord.ui.Button(label='Accept team invitation' if kind=='team_invite' else 'Apply to team',custom_id=f'vivi:team:{kind}:{ident}')
        button.callback=self.click;self.add_item(button)
    async def click(self,i):
        if not await self.service.need(i,'teams'):return
        store=self.service.store
        try:row=scoped(store,i.guild_id,self.ident,self.kind);team=scoped(store,i.guild_id,row['data']['team'],'team')
        except ValueError as error:return await reply(i,str(error))
        data=row['data'];roster=team['data']['roster']
        if data.get('closed') or data['expires']<time.time():return await reply(i,'This invitation or recruitment post is closed.')
        if any(x['user']==i.user.id for x in roster):return await reply(i,'You are already on this roster.')
        if self.kind=='team_invite':
            if i.user.id!=data['user']:return await reply(i,'This invitation belongs to another member.')
            if data['captain']!=team['data']['captain']:return await reply(i,'The team captain changed. Ask for a fresh invitation.')
            if len(roster)>=20:return await reply(i,'This roster has twenty members already.')
            roster.append(dict(user=i.user.id,position=data['position'],role=data['role']));data['closed']=True
            store.put_record(i.guild_id,'team',team['data'],team['id']);store.put_record(i.guild_id,self.kind,data,row['id'])
            return await reply(i,'You accepted the invitation and joined the team roster.')
        required=data.get('required_role',0)
        if required and not any(r.id==required for r in i.user.roles):return await reply(i,'You do not currently have the role required by this recruitment post.')
        ident=f'team_application:{row["id"]}:{i.user.id}'
        old=store.record(ident)
        if old and old['data'].get('status')=='pending':return await reply(i,'Your application is already pending.')
        if sum(r['data'].get('status')=='pending' for r in store.records(i.guild_id,'team_application') if r['data']['team']==team['id'])>=50:return await reply(i,'This team’s application queue is full.')
        store.put_record(i.guild_id,'team_application',dict(team=team['id'],recruitment=row['id'],user=i.user.id,status='pending',created=time.time()),ident)
        await reply(i,'Application saved for the captain. Membership still requires a personal invitation you accept.')


def restore_team_panels(service):
    for row in service.store.records():
        if row['kind'] in {'team_invite','team_recruitment'} and not row['data'].get('closed') and row['data']['expires']>time.time():service.bot.add_view(TeamPanel(service,row['id'],row['kind']))


def register_library(bot):
    service=bot.community;store=bot.store
    teams=app_commands.Group(name='teams',description='Consensual rosters, captains, substitutes and recruitment',guild_only=True)
    library=app_commands.Group(name='library',description='Searchable game builds and member-written strategy guides',guild_only=True)
    def get_team(i,ident,manage=False):
        row=scoped(store,i.guild_id,ident,'team')
        if manage and not team_manager(i,row['data']):raise ValueError('Only the current captain or Manage Server staff may manage this roster.')
        return row
    @teams.command(name='create',description='Create a team with yourself as its captain.')
    async def create(i:discord.Interaction,name:app_commands.Range[str,1,60],game:app_commands.Range[str,1,60]):
        if not await service.need(i,'teams'):return
        rows=store.records(i.guild_id,'team')
        if len(rows)>=50 or sum(r['data']['captain']==i.user.id for r in rows)>=2:return await reply(i,'Limit: two captaincies per member and fifty teams per server.')
        try:clean_text(store,i.guild_id,name+' '+game)
        except ValueError as error:return await reply(i,str(error))
        ident=store.put_record(i.guild_id,'team',dict(name=name,game=game,captain=i.user.id,roster=[dict(user=i.user.id,position='starter',role='Captain')],created=time.time()))
        await reply(i,f'Team `{ident}` created. Use /teams invite to invite consenting members.')
    @teams.command(name='invite',description='Invite a member to accept a starter or substitute roster position.')
    @app_commands.choices(position=[app_commands.Choice(name=x,value=x) for x in ['starter','substitute']])
    async def invite(i:discord.Interaction,team_id:str,member:discord.Member,position:str='starter',role:app_commands.Range[str,1,40]='Player'):
        if not await service.need(i,'teams'):return
        try:row=get_team(i,team_id,True);clean_text(store,i.guild_id,role)
        except ValueError as error:return await reply(i,str(error))
        if member.bot or len(row['data']['roster'])>=20 or any(x['user']==member.id for x in row['data']['roster']):return await reply(i,'Choose an eligible member outside this roster; maximum twenty members.')
        pending=[r for r in store.records(i.guild_id,'team_invite') if r['data']['team']==team_id and not r['data'].get('closed') and r['data']['expires']>time.time()]
        if len(pending)>=20 or any(r['data']['user']==member.id for r in pending):return await reply(i,'An invitation is already pending, or this team has twenty pending invitations.')
        ident=store.put_record(i.guild_id,'team_invite',dict(team=team_id,user=member.id,captain=row['data']['captain'],position=position,role=role,expires=time.time()+86400,closed=False))
        await i.response.send_message(f'<@{member.id}>, you are invited to {discord.utils.escape_markdown(row["data"]["name"])} as {position}: {discord.utils.escape_markdown(role)}. Only you can accept; invitation expires in 24 hours.',view=TeamPanel(service,ident,'team_invite'),allowed_mentions=discord.AllowedMentions.none())
    @teams.command(name='roster',description='Show a team’s captain, starters and substitutes.')
    async def roster(i:discord.Interaction,team_id:str):
        try:row=get_team(i,team_id)
        except ValueError as error:return await reply(i,str(error))
        data=row['data'];await reply(i,f'{data["name"]} · {data["game"]}\nCaptain: <@{data["captain"]}>\n'+'\n'.join(f'<@{x["user"]}> · {x["position"]} · {x["role"]}' for x in data['roster']))
    @teams.command(name='position',description='Update a consenting roster member’s starter/substitute position and game role.')
    @app_commands.choices(position=[app_commands.Choice(name=x,value=x) for x in ['starter','substitute']])
    async def position(i:discord.Interaction,team_id:str,member:discord.Member,position:str,role:app_commands.Range[str,1,40]='Player'):
        if not await service.need(i,'teams'):return
        try:
            row=get_team(i,team_id,True);clean_text(store,i.guild_id,role);entry=next((x for x in row['data']['roster'] if x['user']==member.id),None)
            if not entry:raise ValueError('That member is not on this roster.')
            entry.update(position=position,role=role);store.put_record(i.guild_id,'team',row['data'],row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Roster position saved. This changes game labels, not Discord roles.')
    @teams.command(name='captain',description='Transfer team management to an existing consenting roster member.')
    async def captain(i:discord.Interaction,team_id:str,member:discord.Member):
        if not await service.need(i,'teams'):return
        try:
            row=get_team(i,team_id,True)
            if not any(x['user']==member.id for x in row['data']['roster']):raise ValueError('The new captain must already be on the roster.')
            row['data']['captain']=member.id;store.put_record(i.guild_id,'team',row['data'],row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Captain transferred. Old pending roster invitations are no longer valid.')
    @teams.command(name='remove',description='Remove a roster member; captains must transfer management first.')
    async def remove(i:discord.Interaction,team_id:str,member:discord.Member):
        try:
            row=get_team(i,team_id,True)
            if member.id==row['data']['captain']:raise ValueError('Transfer captaincy first.')
            row['data']['roster']=[x for x in row['data']['roster'] if x['user']!=member.id];store.put_record(i.guild_id,'team',row['data'],row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Member removed from the roster.')
    @teams.command(name='leave',description='Leave a roster you joined; captains must transfer or disband first.')
    async def leave(i:discord.Interaction,team_id:str):
        try:
            row=get_team(i,team_id)
            if row['data']['captain']==i.user.id:raise ValueError('Transfer captaincy or disband this team first.')
            row['data']['roster']=[x for x in row['data']['roster'] if x['user']!=i.user.id];store.put_record(i.guild_id,'team',row['data'],row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'You left this roster.')
    @teams.command(name='recruit',description='Publish an expiring team recruitment post with optional required Discord role.')
    async def recruit(i:discord.Interaction,team_id:str,requirements:app_commands.Range[str,3,800],openings:app_commands.Range[int,1,19]=1,required_role:discord.Role=None):
        if not await service.need(i,'teams'):return
        try:row=get_team(i,team_id,True);clean_text(store,i.guild_id,requirements)
        except ValueError as error:return await reply(i,str(error))
        if sum(r['data']['team']==team_id and not r['data'].get('closed') and r['data']['expires']>time.time() for r in store.records(i.guild_id,'team_recruitment'))>=3:return await reply(i,'Close an existing recruitment post first; maximum three active posts per team.')
        data=dict(team=team_id,requirements=requirements,openings=openings,required_role=required_role.id if required_role else 0,expires=time.time()+7*86400,closed=False)
        ident=store.put_record(i.guild_id,'team_recruitment',data)
        await i.response.send_message(f'**Recruiting: {discord.utils.escape_markdown(row["data"]["name"])}** · {discord.utils.escape_markdown(row["data"]["game"])}\nOpenings: {openings}\n{discord.utils.escape_markdown(requirements)}\nRequired role: '+(required_role.mention if required_role else 'none')+f'\nPost `{ident}` · Applications close in seven days.',view=TeamPanel(service,ident,'team_recruitment'),allowed_mentions=discord.AllowedMentions.none())
    @teams.command(name='applications',description='Privately inspect this team’s applications as captain or staff.')
    async def applications(i:discord.Interaction,team_id:str):
        try:get_team(i,team_id,True)
        except ValueError as error:return await reply(i,str(error))
        rows=[dict(id=r['id'],**r['data']) for r in store.records(i.guild_id,'team_application') if r['data']['team']==team_id]
        await i.response.send_message(file=discord.File(io.BytesIO(json.dumps(rows,indent=2).encode()),filename='team-applications.json'),ephemeral=True)
    @teams.command(name='application_decide',description='Close an application with a recorded decision; use invite for membership.')
    @app_commands.choices(status=[app_commands.Choice(name=x,value=x) for x in ['accepted','declined']])
    async def application_decide(i:discord.Interaction,application_id:str,status:str,reason:app_commands.Range[str,3,500]):
        try:
            row=scoped(store,i.guild_id,application_id,'team_application');get_team(i,row['data']['team'],True)
            if row['data']['status']!='pending':raise ValueError('This application already has a decision.')
            row['data'].update(status=status,reason=reason,reviewer=i.user.id);store.put_record(i.guild_id,'team_application',row['data'],row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Decision saved. An accepted applicant joins only after accepting /teams invite.')
    @teams.command(name='my_applications',description='Privately inspect your team application decisions.')
    async def my_applications(i:discord.Interaction):await reply(i,'\n'.join(f'{r["data"]["team"]}: {r["data"]["status"]} · {r["data"].get("reason","")}' for r in store.records(i.guild_id,'team_application') if r['data']['user']==i.user.id) or 'No applications.')
    @teams.command(name='recruitment_close',description='Close one of your team’s recruitment posts.')
    async def recruitment_close(i:discord.Interaction,recruitment_id:str):
        try:
            row=scoped(store,i.guild_id,recruitment_id,'team_recruitment');get_team(i,row['data']['team'],True);row['data']['closed']=True;store.put_record(i.guild_id,'team_recruitment',row['data'],row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Recruitment closed. Existing message buttons now reject new applications.')
    @teams.command(name='disband',description='Delete a team and its outstanding invitations and applications.')
    async def disband(i:discord.Interaction,team_id:str,confirm:bool=False):
        try:get_team(i,team_id,True)
        except ValueError as error:return await reply(i,str(error))
        if not confirm:return await reply(i,'Set confirm:true to delete this team and its membership records.')
        for row in store.records(i.guild_id):
            if row['kind'] in {'team_invite','team_recruitment','team_application'} and row['data']['team']==team_id:store.delete_record(row['id'])
        store.delete_record(team_id);await reply(i,'Team disbanded. Old public recruitment messages may need manual removal.')
    @teams.command(name='list',description='Find teams by game name.')
    async def listing(i:discord.Interaction,game:str=''):await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["name"]} · {r["data"]["game"]} · {len(r["data"]["roster"])} members' for r in store.records(i.guild_id,'team') if game.casefold() in r['data']['game'].casefold())[:1800] or 'No matching teams.')

    @library.command(name='publish',description='Publish a searchable game build or member-written strategy guide.')
    @app_commands.choices(kind=[app_commands.Choice(name=x,value=x) for x in ['build','guide']])
    async def publish(i:discord.Interaction,kind:str,title:app_commands.Range[str,1,80],game:app_commands.Range[str,1,60],content:app_commands.Range[str,10,1800]):
        if not await service.need(i,'library'):return
        try:clean_text(store,i.guild_id,title+' '+game+' '+content)
        except ValueError as error:return await reply(i,str(error))
        rows=store.records(i.guild_id,'library_entry')
        if len(rows)>=500 or sum(r['data']['author']==i.user.id for r in rows)>=20:return await reply(i,'Library limit: twenty entries per member, five hundred per server.')
        ident=store.put_record(i.guild_id,'library_entry',dict(kind=kind,title=title,game=game,content=content,author=i.user.id,created=time.time(),updated=time.time(),history=[]))
        await reply(i,f'Published `{ident}`. Members can use /library search and /library read. Entry text is public to server members.')
    @library.command(name='search',description='Search builds and strategy guides by game, kind and text.')
    @app_commands.choices(kind=[app_commands.Choice(name=x,value=x) for x in ['all','build','guide']])
    async def search(i:discord.Interaction,game:str='',query:str='',kind:str='all'):
        if not await service.need(i,'library'):return
        rows=[r for r in store.records(i.guild_id,'library_entry') if (kind=='all' or r['data']['kind']==kind) and game.casefold() in r['data']['game'].casefold() and query.casefold() in (r['data']['title']+' '+r['data']['content']).casefold()]
        await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["kind"]} · {discord.utils.escape_markdown(r["data"]["title"])} · {discord.utils.escape_markdown(r["data"]["game"])}' for r in rows[:15]) or 'No matching entries.')
    @library.command(name='read',description='Read a server library entry, including its author and update time.')
    async def read(i:discord.Interaction,entry_id:str):
        if not await service.need(i,'library'):return
        try:row=scoped(store,i.guild_id,entry_id,'library_entry')
        except ValueError as error:return await reply(i,str(error))
        data=row['data'];embed=discord.Embed(title=data['title'],description=data['content'],color=0xB980FF);embed.set_footer(text=f'{data["game"]} · {data["kind"]} · author {data["author"]} · updated {int(data["updated"])}')
        await i.response.send_message(embed=embed,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    @library.command(name='edit',description='Edit your own library entry while keeping five previous versions.')
    async def edit(i:discord.Interaction,entry_id:str,content:app_commands.Range[str,10,1800]):
        if not await service.need(i,'library'):return
        try:
            row=scoped(store,i.guild_id,entry_id,'library_entry')
            if row['data']['author']!=i.user.id:raise ValueError('Only the author can edit this entry; staff may remove it.')
            clean_text(store,i.guild_id,content);data=row['data'];data['history']=(data['history']+[dict(content=data['content'],at=data['updated'])])[-5:];data.update(content=content,updated=time.time());store.put_record(i.guild_id,'library_entry',data,row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Entry updated.')
    @library.command(name='remove',description='Remove your library entry, or moderate one with Manage Messages permission.')
    async def remove_entry(i:discord.Interaction,entry_id:str,reason:app_commands.Range[str,3,500]):
        try:
            row=scoped(store,i.guild_id,entry_id,'library_entry')
            if row['data']['author']!=i.user.id and not i.user.guild_permissions.manage_messages:raise ValueError('Only the author or Manage Messages staff may remove this entry.')
            store.delete_record(entry_id)
            if row['data']['author']!=i.user.id:store.add_case(i.guild_id,row['data']['author'],i.user.id,'library entry removed',f'{entry_id}: {reason}')
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Library entry removed. Profile showcases referencing it will omit it.')
    bot.tree.add_command(teams);bot.tree.add_command(library)
