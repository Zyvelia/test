"""Bounded OAuth guild caching; rate limits never masquerade as expired logins."""
import asyncio
import time
import math
import aiohttp
from aiohttp import web

DISCORD='https://discord.com/api/v10'
class DashboardAuth:
    async def api_guilds(self,session,fresh=False):
        started=time.time();lock=session.setdefault('_guild_lock',asyncio.Lock())
        async with lock:
            now=time.time();cached=session.get('_guild_cache')
            if cached and (cached['at']>=started or not fresh and now-cached['at']<30):return cached['rows']
            if session.get('_guild_retry',0)>now:
                raise web.HTTPTooManyRequests(text='Discord is busy. You are still signed in. Wait a moment before trying again.',headers={'Retry-After':str(max(1,int(session['_guild_retry']-now)+1))})
            try:
                async with self.service.session.get(DISCORD+'/users/@me/guilds',headers={'Authorization':'Bearer '+session['token']},allow_redirects=False) as response:
                    if response.status==401:
                        session['expires']=0;session.pop('_guild_cache',None)
                        raise web.HTTPUnauthorized(text='Discord authorization ended. Sign in again to reconnect your account.')
                    if response.status==429:
                        try:delay=float(response.headers.get('Retry-After','5'))
                        except (ValueError,TypeError):delay=5
                        if not math.isfinite(delay):delay=5
                        session['_guild_retry']=now+min(max(delay,1),300)
                        raise web.HTTPTooManyRequests(text='Discord is limiting requests. Your login is still active. Wait a moment and try again.',headers={'Retry-After':str(int(min(max(delay,1),300))+1)})
                    if response.status==403:raise web.HTTPForbidden(text='Discord did not grant access to your server list. Check your Discord authorization scopes.')
                    if response.status!=200:raise web.HTTPServiceUnavailable(text='Discord is temporarily unavailable. Your login is still active; try again shortly.')
                    rows=await response.json()
                if not isinstance(rows,list):raise web.HTTPServiceUnavailable(text='Discord returned an unexpected server list. Try again shortly.')
                result={str(g['id']):g for g in rows if g.get('owner') or int(g.get('permissions',0))&8}
                session['_guild_cache']={'at':time.time(),'rows':result};session.pop('_guild_retry',None)
                return result
            except (ValueError,KeyError,TypeError):raise web.HTTPServiceUnavailable(text='Discord returned unexpected account data. Your login is still active; retry shortly.') from None
            except (aiohttp.ClientError,asyncio.TimeoutError):raise web.HTTPServiceUnavailable(text='Could not reach Discord. You are still signed in; please try again shortly.') from None
