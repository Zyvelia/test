"""Optional loopback dashboard. OAuth tokens and sessions remain in memory only."""
import hashlib
import hmac
import html
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit

import aiohttp
from aiohttp import web
from .features import FEATURES, enabled

DISCORD='https://discord.com/api/v10'

class Dashboard:
    def __init__(self,service):
        self.service=service; self.sessions={}; self.states={}; self.runner=None
        self.client=os.getenv('DISCORD_CLIENT_ID','').strip()
        self.secret=os.getenv('DISCORD_CLIENT_SECRET','').strip()
        self.redirect=os.getenv('DASHBOARD_REDIRECT_URI','http://127.0.0.1:8765/callback').strip()
        parsed=urlsplit(self.redirect)
        if (parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'}
                or parsed.path!='/callback' or parsed.query or parsed.fragment or parsed.username is not None):
            raise ValueError('Dashboard redirect must be http://127.0.0.1:PORT/callback or localhost equivalent.')
        self.host=parsed.hostname; self.port=parsed.port or 80
        self.app=web.Application(client_max_size=16384,middlewares=[self.security])
        self.app.add_routes([web.get('/',self.index),web.get('/login',self.login),web.get('/callback',self.callback),
                             web.post('/feature',self.feature),web.post('/logout',self.logout)])

    @web.middleware
    async def security(self,request,handler):
        # DNS rebinding protection: the loopback listener accepts only its configured authority.
        expected=f'{self.host}:{self.port}'
        if request.host not in {expected, self.host if self.port==80 else expected}:
            raise web.HTTPForbidden(text='Unexpected Host header.')
        try: response=await handler(request)
        except web.HTTPException as response:
            self.headers(response); raise
        self.headers(response); return response

    @staticmethod
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})

    def session(self,request):
        sid=request.cookies.get('aurora_session',''); session=self.sessions.get(sid)
        if not session or session['expires']<time.time():
            self.sessions.pop(sid,None); raise web.HTTPUnauthorized(text='Session expired. Return to /login.')
        return session

    async def api_guilds(self,session):
        async with self.service.session.get(DISCORD+'/users/@me/guilds',
                headers={'Authorization':'Bearer '+session['token']}) as response:
            if response.status!=200: raise web.HTTPUnauthorized(text='Discord login expired. Sign in again.')
            rows=await response.json()
        return {str(g['id']):g for g in rows if g.get('owner') or (int(g.get('permissions',0)) & 8)}

    async def authorize(self,request,guild):
        session=self.session(request)
        # Fresh Discord permissions on every page/action; cached login does not preserve revoked access.
        guilds=await self.api_guilds(session)
        if str(guild) not in guilds or self.service.bot.get_guild(guild) is None:
            raise web.HTTPForbidden(text='You must be a current server owner/administrator and this bot must be installed.')
        return session

    def page(self,content):
        return web.Response(content_type='text/html',text='<!doctype html><html><head><meta charset="utf-8"><title>Aurora Dashboard</title>'
            '<style>body{font:16px system-ui;background:#111827;color:#e5e7eb;max-width:850px;margin:40px auto;padding:20px}'
            'a{color:#87ceeb}form{margin:12px 0;padding:14px;background:#1f2937;border-radius:12px}'
            'button{padding:8px 14px;border:0;border-radius:8px;cursor:pointer}small{color:#aab6c9}</style></head><body>'
            '<h1>Aurora · Server Dashboard</h1>'+content+'</body></html>')

    async def index(self,request):
        if not request.cookies.get('aurora_session'): return self.page('<p><a href="/login">Sign in with Discord</a></p><p>Local dashboard: server administrators only.</p>')
        session=self.session(request)
        if not request.query.get('guild'):
            guilds=await self.api_guilds(session)
            rows=[f'<li><a href="/?guild={html.escape(gid)}">{html.escape(g["name"])}</a></li>' for gid,g in guilds.items() if self.service.bot.get_guild(int(gid))]
            return self.page('<h2>Your servers</h2><ul>'+''.join(rows)+'</ul>'+self.logout_form(session))
        try: guild=int(request.query['guild'])
        except ValueError: raise web.HTTPBadRequest(text='Invalid server ID.')
        session=await self.authorize(request,guild)
        name=html.escape(self.service.bot.get_guild(guild).name)
        forms=[]
        for feature in FEATURES:
            on=enabled(self.service.store,guild,feature)
            forms.append(f'<form action="/feature" method="post"><input type="hidden" name="csrf" value="{session["csrf"]}">'
                         f'<input type="hidden" name="guild" value="{guild}"><input type="hidden" name="feature" value="{feature}">'
                         f'<input type="hidden" name="enabled" value="{str(not on).lower()}"><b>{feature}</b>: {"ON" if on else "OFF"} '
                         f'<button>{"Disable" if on else "Enable"}</button></form>')
        return self.page(f'<h2>{name}</h2><p><a href="/">All servers</a></p><p>AI remains off until explicitly enabled. Configure channels and other settings with /admin setting in Discord.</p>'+''.join(forms)+self.logout_form(session))

    @staticmethod
    def logout_form(session):
        return f'<form action="/logout" method="post"><input type="hidden" name="csrf" value="{session["csrf"]}"><button>Sign out</button></form>'

    async def login(self,request):
        if not self.client or not self.secret: raise web.HTTPServiceUnavailable(text='Host must configure Discord OAuth client ID and secret.')
        now=time.time(); self.states={k:v for k,v in self.states.items() if v['expires']>now}
        self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
        if len(self.states)>=1000: raise web.HTTPTooManyRequests(text='Too many pending sign-ins. Try later.')
        state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(48)
        self.states[state]={'expires':now+600,'verifier':verifier}
        query=urlencode(dict(client_id=self.client,redirect_uri=self.redirect,response_type='code',scope='identify guilds',state=state))
        response=web.HTTPFound('https://discord.com/oauth2/authorize?'+query)
        response.set_cookie('aurora_oauth',verifier,max_age=600,httponly=True,samesite='Lax',path='/callback')
        return response

    async def callback(self,request):
        state=request.query.get('state',''); pending=self.states.pop(state,None)
        if (not pending or pending['expires']<time.time()
                or not hmac.compare_digest(pending['verifier'],request.cookies.get('aurora_oauth',''))):
            raise web.HTTPForbidden(text='Invalid or expired login state. Start again at /login.')
        code=request.query.get('code')
        if not code: raise web.HTTPBadRequest(text='Discord login was not completed.')
        payload=dict(client_id=self.client,client_secret=self.secret,grant_type='authorization_code',
                     code=code,redirect_uri=self.redirect)
        async with self.service.session.post(DISCORD+'/oauth2/token',data=payload,allow_redirects=False) as response:
            if response.status!=200: raise web.HTTPUnauthorized(text='Discord rejected this login. Start again.')
            data=await response.json()
        sid=secrets.token_urlsafe(32)
        self.sessions[sid]={'token':data['access_token'],'csrf':secrets.token_urlsafe(32),
                            'expires':time.time()+min(int(data.get('expires_in',3600)),3600)}
        response=web.HTTPFound('/')
        response.set_cookie('aurora_session',sid,max_age=3600,httponly=True,samesite='Lax',path='/')
        response.del_cookie('aurora_oauth',path='/callback')
        return response

    async def feature(self,request):
        data=await request.post(); session=self.session(request)
        if not hmac.compare_digest(session['csrf'],str(data.get('csrf',''))): raise web.HTTPForbidden(text='Invalid form token.')
        try: guild=int(data.get('guild',''))
        except ValueError: raise web.HTTPBadRequest(text='Invalid server.')
        await self.authorize(request,guild)
        feature=data.get('feature'); value=data.get('enabled')
        if feature not in FEATURES or value not in {'true','false'}: raise web.HTTPBadRequest(text='Invalid feature setting.')
        self.service.store.set_option(guild,'feature:'+feature,value=='true')
        raise web.HTTPSeeOther('/?guild='+str(guild))

    async def logout(self,request):
        session=self.session(request); data=await request.post()
        if not hmac.compare_digest(session['csrf'],str(data.get('csrf',''))): raise web.HTTPForbidden(text='Invalid form token.')
        self.sessions.pop(request.cookies.get('aurora_session',''),None)
        response=web.HTTPSeeOther('/'); response.del_cookie('aurora_session'); return response

    async def start(self):
        if not self.client or not self.secret: raise ValueError('Missing OAuth credentials')
        self.runner=web.AppRunner(self.app,access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner,self.host,self.port).start()

    async def close(self):
        if self.runner: await self.runner.cleanup()
