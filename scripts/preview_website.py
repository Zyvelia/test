"""Local website preview with temporary records and no Discord connection or real tokens."""
import argparse
import asyncio
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp import web
import discord
from vivi.bot import ViviBot
from vivi.site.dashboard import Dashboard
from vivi.core.storage import Store

async def main(port,dashboard_preview=False):
    os.environ['DASHBOARD_REDIRECT_URI']='http://127.0.0.1:8765/callback'
    os.environ['DASHBOARD_BIND_HOST']='127.0.0.1'
    os.environ.pop('DASHBOARD_LISTEN_PORT',None)
    os.environ['DISCORD_CLIENT_ID']='1568121020047429775';os.environ['DISCORD_CLIENT_SECRET']=''
    with tempfile.TemporaryDirectory(prefix='vivi-website-preview-') as temporary:
        store=Store(Path(temporary)/'vivi.sqlite3');bot=ViviBot(store);await bot.__aenter__()
        bot.sync_application_commands=AsyncMock(return_value=[]);bot.community.start=AsyncMock();bot.community.productivity.start_aliases=AsyncMock()
        dashboard=None
        try:
            await bot.setup_hook();dashboard=Dashboard(bot.community)
            if dashboard_preview:
                bot._connection.user=NS(id=99)
                guild=NS(id=1,owner_id=7,default_role=NS(id=1),get_role=lambda ident:None,name='Velvet Ruins',text_channels=[],channels=[],categories=[],voice_channels=[],roles=[],me=NS(display_name='Preview bot',guild_permissions=discord.Permissions(ban_members=True,view_audit_log=True),top_role=10),get_member=lambda uid:None,get_channel=lambda cid:None)
                welcome=MagicMock(spec=discord.TextChannel);welcome.id=3;welcome.name='welcome';welcome.send=AsyncMock()
                welcome.permissions_for.return_value=discord.Permissions.all()
                guild.text_channels=[welcome];guild.channels=[welcome];guild.member_count=42;guild.get_channel=lambda cid:welcome if cid==3 else None
                guild.fetch_member=AsyncMock(side_effect=lambda uid:NS(id=uid,roles=[],guild_permissions=discord.Permissions.all() if uid==7 else discord.Permissions.none()))
                ticket=MagicMock(spec=discord.TextChannel);ticket.id=4;ticket.name='ticket-preview';ticket.send=AsyncMock();ticket.permissions_for.return_value=discord.Permissions.all()
                guild.text_channels.append(ticket);guild.channels.append(ticket);guild.get_channel=lambda cid:welcome if cid==3 else ticket if cid==4 else None
                store.put_record(1,'privacy',dict(author=8,text='Synthetic deletion request for privacy review.',status='pending',created_at=time.time()),'preview-privacy')
                store.put_record(1,'notification',dict(provider='github',source='Zyvelia/test',channel=3),'preview-watch')
                case=store.add_case(1,8,7,'warning','Example case for the dashboard preview')
                store.put_record(1,'report',dict(author=8,target=9,text='Synthetic report for staff review.',status='pending'),'preview-report')
                store.put_record(1,'appeal',dict(author=8,case=case,text='Synthetic moderation appeal.',status='pending'),'preview-appeal')
                store.add_ticket(1,8,4);bot.community.operations.save_ticket_meta(1,4,dict(priority='high',claimed=7,category='General'))
                store.db.execute('UPDATE ticket_events SET at=? WHERE guild=1 AND channel=4',(time.time()-7200,));store.db.commit()
                bot.get_guild=lambda gid:guild if gid==1 else None
                dashboard.api_guilds=AsyncMock(side_effect=lambda session,**kwargs: {'1':dict(id='1',name='Velvet Ruins',permissions='8',icon='a'*32),'2':dict(id='2',name='Your next community',permissions='8')} if session['user_id']==7 else {'1':dict(id='1',name='Velvet Ruins',permissions='0')} if kwargs.get('include_all') else {})
                dashboard.sessions['vivi-preview']=dict(profile={'username':'ItsZyVelia','global_name':'ZyVelia','avatar':''},user_id=7,token='not-a-real-token',csrf='preview-only-csrf',expires=time.time()+3600)
                dashboard.sessions['vivi-member-preview']=dict(profile={'username':'Member','global_name':'Member','avatar':''},user_id=8,token='not-a-real-token',csrf='member-preview-csrf',expires=time.time()+3600)
            dashboard.runner=web.AppRunner(dashboard.app,access_log=None);await dashboard.runner.setup()
            site=web.TCPSite(dashboard.runner,'127.0.0.1',port);await site.start()
            dashboard.port=site._server.sockets[0].getsockname()[1];dashboard.public_port=dashboard.port
            dashboard.redirect=f'http://127.0.0.1:{dashboard.port}/callback'
            print(f'PREVIEW_READY=http://127.0.0.1:{dashboard.port}',flush=True)
            stopped=asyncio.Event();loop=asyncio.get_running_loop()
            for signum in [signal.SIGTERM,signal.SIGINT]:
                try:loop.add_signal_handler(signum,stopped.set)
                except NotImplementedError:pass
            await stopped.wait()
        finally:
            if dashboard:await dashboard.close()
            await bot.close();store.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765);parser.add_argument('--dashboard-preview',action='store_true',help='Enable fake, temporary server settings for local UI tests only.')
    args=parser.parse_args()
    try:asyncio.run(main(args.port,args.dashboard_preview))
    except KeyboardInterrupt:pass
