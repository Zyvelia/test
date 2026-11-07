"""Persistent seeded single/double elimination; only hosts or authorized staff report results."""
import copy
import io
import random
import time
import discord
from discord import app_commands
from vivi.bot import reply


def schedule(data):
    limit=1 if data['format']=='single' else 2
    alive=[u for u in data['players'] if data['losses'].get(str(u),0)<limit]
    if len(alive)<=1:
        data['status']='finished';data['winner']=alive[0] if alive else None;return
    upper=[u for u in alive if data['losses'].get(str(u),0)==0]
    lower=[u for u in alive if data['losses'].get(str(u),0)==1]
    pairs=[]
    if data['format']=='double' and len(alive)==2 and (len(upper)==len(lower)==1 or not upper):pairs=[(alive[0],alive[1],'grand final/reset')]
    else:
        for label,group in [('upper',upper),('lower',lower)]:
            pairs.extend((group[n],group[n+1],label) for n in range(0,len(group)-1,2))
    if not pairs:raise ValueError('No valid tournament pairing could be scheduled.')
    round_no=1+max((m['round'] for m in data['matches']),default=0)
    for a,b,label in pairs:data['matches'].append(dict(id=len(data['matches'])+1,round=round_no,a=a,b=b,bracket=label,winner=None))


def report_result(data,match_id,winner,actor,reason):
    updated=copy.deepcopy(data)
    if updated['status']!='active':raise ValueError('This competition is not active.')
    match=next((m for m in updated['matches'] if m['id']==match_id),None)
    if not match or match['winner'] is not None or winner not in {match['a'],match['b']}:raise ValueError('Choose a pending match and one of its players.')
    loser=match['b'] if winner==match['a'] else match['a'];match.update(winner=winner,actor=actor,reason=reason,at=time.time())
    updated['losses'][str(loser)]=updated['losses'].get(str(loser),0)+1
    if all(m['winner'] is not None for m in updated['matches']):schedule(updated)
    return updated


def bracket_text(data,audit=False):
    lines=[f'{data["name"]} · {data["format"]} elimination · {data["status"]}',f'Host: {data["host"]}; entrants: {len(data["players"])}/{data["capacity"]}', 'Seeds: '+', '.join(f'{n+1}={u}' for n,u in enumerate(data['players']))]
    for match in data['matches']:
        lines.append(f'Round {match["round"]} · {match["bracket"]} · match #{match["id"]}: {match["a"]} vs {match["b"]} → '+(str(match['winner']) if match['winner'] else 'pending'))
        if audit and match.get('winner'):lines.append(f'  Reported by {match.get("actor",0)}: {match.get("reason","")}')
    if data.get('winner'):lines.append('Champion: '+str(data['winner']))
    if data['format']=='double':lines.append('Double elimination uses seeded loss-bucket rounds, automatic byes and a grand-final reset when required. Each player is eliminated after two losses.')
    return '\n'.join(lines)


def register_competitions(bot):
    store=bot.store;service=bot.community
    group=app_commands.Group(name='competition',description='Persistent tournament brackets and result tracking',guild_only=True)
    def get(i,ident,manage=False):
        row=store.record(ident)
        if not row or row['guild']!=i.guild_id or row['kind']!='bracket':raise ValueError('Competition not found in this server.')
        if manage and row['data']['host']!=i.user.id and not i.user.guild_permissions.manage_guild:raise ValueError('Only the host or Manage Server staff may manage this competition.')
        return row
    @group.command(name='create',description='Create a seeded single- or double-elimination competition.')
    @app_commands.choices(format=[app_commands.Choice(name=x,value=x) for x in ['single','double']])
    async def create(i:discord.Interaction,name:app_commands.Range[str,1,80],format:str='single',capacity:app_commands.Range[int,2,32]=16):
        if not await service.need(i,'competitions'):return
        rows=store.records(i.guild_id,'bracket')
        if sum(r['data']['status'] in {'registration','active'} for r in rows)>=20:return await reply(i,'This server already has twenty open competitions.')
        if sum(r['data']['host']==i.user.id and r['data']['status'] in {'registration','active'} for r in rows)>=2:return await reply(i,'Finish or cancel one of your two open competitions first.')
        ident=store.put_record(i.guild_id,'bracket',dict(name=name,format=format,capacity=capacity,host=i.user.id,players=[],losses={},matches=[],status='registration',created=time.time()))
        await reply(i,f'Competition `{ident}` created. Members join with /competition join; the host then uses /competition start.')
    @group.command(name='join',description='Register yourself in an open competition.')
    async def join(i:discord.Interaction,competition_id:str):
        if not await service.need(i,'competitions'):return
        try:row=get(i,competition_id)
        except ValueError as error:return await reply(i,str(error))
        data=row['data']
        if data['status']!='registration':return await reply(i,'Registration is closed.')
        if i.user.id not in data['players']:
            if i.user.bot or len(data['players'])>=data['capacity']:return await reply(i,'Registration is full or this account is not eligible.')
            data['players'].append(i.user.id);store.put_record(i.guild_id,'bracket',data,row['id'])
        await reply(i,'You are registered. Joining order determines seeding unless the host shuffles at start.')
    @group.command(name='leave',description='Withdraw yourself before competition registration closes.')
    async def leave(i:discord.Interaction,competition_id:str):
        try:row=get(i,competition_id)
        except ValueError as error:return await reply(i,str(error))
        if row['data']['status']!='registration':return await reply(i,'Ask the host about a forfeit after play begins.')
        row['data']['players']=[u for u in row['data']['players'] if u!=i.user.id];store.put_record(i.guild_id,'bracket',row['data'],row['id']);await reply(i,'Registration withdrawn.')
    @group.command(name='start',description='Close registration and generate seeded bracket pairings.')
    async def start(i:discord.Interaction,competition_id:str,shuffle:bool=False):
        if not await service.need(i,'competitions'):return
        try:
            row=get(i,competition_id,True);data=row['data']
            if data['status']!='registration' or len(data['players'])<2:raise ValueError('At least two entrants and open registration are required.')
            if shuffle:random.SystemRandom().shuffle(data['players'])
            data['status']='active';schedule(data);store.put_record(i.guild_id,'bracket',data,row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Competition started. Use /competition show for pairings, then /competition result to record outcomes.')
    @group.command(name='result',description='Record a pending match result with an audit reason; a forfeit may be noted.')
    async def result(i:discord.Interaction,competition_id:str,match_id:int,winner:discord.Member,reason:app_commands.Range[str,3,500]):
        if not await service.need(i,'competitions'):return
        try:
            row=get(i,competition_id,True);data=report_result(row['data'],match_id,winner.id,i.user.id,reason);store.put_record(i.guild_id,'bracket',data,row['id'])
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Result recorded. '+(f'Champion: <@{data["winner"]}>.' if data['status']=='finished' else 'Use /competition show for the current round.'))
    @group.command(name='show',description='Download the bracket, seeds, match results and current competition status.')
    async def show(i:discord.Interaction,competition_id:str,audit:bool=False):
        try:row=get(i,competition_id,audit)
        except ValueError as error:return await reply(i,str(error))
        await i.response.send_message(file=discord.File(io.BytesIO(bracket_text(row['data'],audit).encode()),filename='bracket.txt'),ephemeral=True)
    @group.command(name='list',description='List this server’s open competitions.')
    async def listing(i:discord.Interaction):await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["name"]} · {r["data"]["status"]}' for r in store.records(i.guild_id,'bracket') if r['data']['status'] in {'registration','active'}) or 'No open competitions.')
    @group.command(name='cancel',description='Cancel a competition while retaining its match history and reason.')
    async def cancel(i:discord.Interaction,competition_id:str,reason:app_commands.Range[str,3,500]):
        try:row=get(i,competition_id,True)
        except ValueError as error:return await reply(i,str(error))
        row['data'].update(status='cancelled',cancelled_by=i.user.id,cancel_reason=reason);store.put_record(i.guild_id,'bracket',row['data'],row['id']);await reply(i,'Competition cancelled; history retained.')
    bot.tree.add_command(group)
