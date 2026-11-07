"""Read-only Discord permission verification and opt-in external-provider smoke tests."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil

import aiohttp
import discord
from dotenv import load_dotenv
from vivi.core.storage import Store, database_path
from vivi.core.features import enabled

ROOT=Path(__file__).resolve().parents[1]

def guild_checks(store,guild,member=None):
    member=member or guild.me; checks=[]; config=store.settings(guild.id)
    def add(name,passed,detail): checks.append(dict(name=name,status='passed' if passed else 'failed',detail=detail))
    if not config: return [dict(name='server setup',status='failed',detail='Configure welcome, tickets, staff and logs first.')]
    specs=[('welcome',config['welcome'],('view_channel','send_messages')),
           ('staff logs',config['logs'],('view_channel','send_messages','attach_files','read_message_history')),
           ('ticket category',config['category'],('view_channel','manage_channels'))]
    for name,ident,permissions in specs:
        channel=guild.get_channel(ident)
        if not channel: add(name,False,'Configured channel is missing.'); continue
        actual=channel.permissions_for(member); missing=[p for p in permissions if not getattr(actual,p)]
        add(name,not missing,'Missing: '+', '.join(missing) if missing else 'Required channel permissions are available.')
    logs=guild.get_channel(config['logs'])
    if logs: add('staff log privacy',not logs.permissions_for(guild.default_role).view_channel,'Also review other role/member overwrites manually.')
    for feature,permissions in [('moderation',['moderate_members','kick_members','ban_members','manage_messages']),
                                ('roles',['manage_roles']),('invite_tracking',['manage_guild']),('music',['connect','speak']),
                                ('voice_rooms',['manage_channels','move_members'])]:
        if enabled(store,guild.id,feature):
            missing=[p for p in permissions if not getattr(member.guild_permissions,p)]
            add(feature+' permissions',not missing,'Missing: '+', '.join(missing) if missing else 'Server-wide permissions are available; channel overrides and target role hierarchy still apply.')
    for feature,key in [('lfg','lfg_channel'),('staff_reviews','review_channel')]:
        if not enabled(store,guild.id,feature): continue
        channel=guild.get_channel(store.option(guild.id,key,0))
        if not channel: add(feature+' channel',False,'Configure '+key+' to an existing text channel.'); continue
        actual=channel.permissions_for(member)
        add(feature+' channel',actual.view_channel and actual.send_messages,'Vivi needs View Channel and Send Messages.')
        if feature=='staff_reviews': add('review notification privacy',not channel.permissions_for(guild.default_role).view_channel,'Deny @everyone View Channel; review all other overwrites manually.')
    if enabled(store,guild.id,'music'): add('FFmpeg',bool(shutil.which(os.getenv('FFMPEG_PATH','ffmpeg'))),'FFmpeg must be installed on the host PC.')
    return checks

async def provider_checks(session,do_requests=False):
    results=[]
    for kind,url,model in [('AI',os.getenv('AI_BASE_URL','').rstrip('/'),os.getenv('AI_MODEL','')),
                           ('translation',os.getenv('TRANSLATE_URL',''),'')]:
        if not url or (kind=='AI' and not model):
            results.append(dict(name=kind,status='not configured',detail='Optional provider settings are absent.')); continue
        if not do_requests:
            results.append(dict(name=kind,status='unrun',detail='Configured; use --providers or explicitly run the dashboard provider check.')); continue
        try:
            if kind=='AI':
                headers={'Authorization':'Bearer '+os.environ['AI_API_KEY']} if os.getenv('AI_API_KEY') else {}
                endpoint=url+'/chat/completions'; payload=dict(model=model,messages=[dict(role='user',content='Reply with OK.')],max_tokens=8)
            else:
                headers={}; endpoint=url; payload=dict(q='Hello',source='en',target='es',format='text')
                if os.getenv('TRANSLATE_API_KEY'): payload['api_key']=os.environ['TRANSLATE_API_KEY']
            async with session.post(endpoint,json=payload,headers=headers,allow_redirects=False) as response:
                if response.status!=200: raise ValueError('provider HTTP '+str(response.status))
                body=await response.json()
                value=body['choices'][0]['message']['content'] if kind=='AI' else body['translatedText']
                if not isinstance(value,str) or not value.strip(): raise ValueError('Empty provider response')
            results.append(dict(name=kind,status='passed',detail='A small explicit functional request returned text.'))
        except Exception as error:
            results.append(dict(name=kind,status='failed',detail=f'{type(error).__name__}: check endpoint, model, credentials and quota.'))
    return results

async def run(providers=False):
    load_dotenv(ROOT/'.env'); report={'discord':[],'oauth':{'status':'manual','detail':'Sign in to the local dashboard in your browser; a configured client secret alone does not verify OAuth.'}}
    token=os.getenv('DISCORD_TOKEN','').strip()
    if token:
        # Login fetches metadata without connecting the gateway, syncing commands, or posting messages.
        async with discord.Client(intents=discord.Intents.none()) as client:
            try:
                await client.login(token)
                store=Store(database_path(ROOT))
                try:
                    guild_id=os.getenv('DEV_GUILD_ID','').strip()
                    ids=[int(guild_id)] if guild_id else [g.id async for g in client.fetch_guilds(limit=100)]
                    for ident in ids:
                        guild=await client.fetch_guild(ident)
                        channels=await guild.fetch_channels()
                        guild._channels.update({c.id:c for c in channels})
                        member=await guild.fetch_member(client.user.id)
                        report['discord'].append(dict(guild=ident,checks=guild_checks(store,guild,member)))
                finally: store.close()
            except Exception as error:
                report['discord'].append(dict(status='failed',detail=f'{type(error).__name__}: check token, server access and configuration.'))
    else: report['discord'].append(dict(status='not configured',detail='DISCORD_TOKEN is absent. No live Discord requests made.'))
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25),trust_env=True) as session:
        report['providers']=await provider_checks(session,providers)
    path=ROOT/'data'/'verification.json'; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2)); print('Report saved to data/verification.json. No messages were posted to Discord.')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--providers',action='store_true',help='Explicitly send small AI/translation requests to configured providers (may incur a small charge).')
    args=parser.parse_args(); report=asyncio.run(run(args.providers))
    if any(x.get('status')=='not configured' for x in report['discord']): raise SystemExit(2)
    failed=any(x.get('status')=='failed' or any(c['status']=='failed' for c in x.get('checks',[])) for x in report['discord'])
    failed=failed or any(x['status']=='failed' for x in report['providers'])
    if failed: raise SystemExit(1)

if __name__=='__main__': main()
