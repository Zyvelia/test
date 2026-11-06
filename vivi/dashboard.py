"""Optional loopback dashboard. OAuth tokens and sessions remain in memory only."""
import hashlib
import io
import json
import hmac
import html
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit

import aiohttp
import discord
from aiohttp import web
from .features import FEATURES, OPTION_TYPES, enabled, validate_backup
from .settings import DEFAULTS, parse_value, validate_resources, validate_setup

DISCORD='https://discord.com/api/v10'

from .dashboard_tools import DashboardTools
from .i18n import UI_LANGUAGE,localize_html,tr

class Dashboard(DashboardTools):
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
        self.bind_host=os.getenv('DASHBOARD_BIND_HOST',self.host)
        if self.bind_host not in {'127.0.0.1','localhost'} and not (self.bind_host=='0.0.0.0' and os.getenv('VIVI_CONTAINER')=='1'):
            raise ValueError('An external dashboard bind is allowed only in explicit container mode.')
        self.app=web.Application(client_max_size=262144,middlewares=[self.security])
        self.app.add_routes([web.get('/',self.index),web.get('/login',self.login),web.get('/callback',self.callback),
                             web.post('/feature',self.feature),web.post('/logout',self.logout),
                             web.post('/setting',self.setting),web.post('/setup',self.setup),
                             web.post('/faq',self.faq),web.post('/ticket-category',self.ticket_category),
                             web.post('/subscription',self.subscription),web.post('/subscription-test',self.subscription_test),
                             web.get('/backup',self.backup),web.post('/restore',self.restore),
                             web.post('/verify',self.verify),web.post('/preview',self.preview),
                             web.get('/revision',self.revision),web.post('/rollback',self.rollback),
                             web.post('/backup-now',self.backup_now),web.get('/scheduled-backup',self.scheduled_backup),
                             web.post('/aliases',self.aliases),web.get('/health',self.health)])

    @web.middleware
    async def security(self,request,handler):
        # DNS rebinding protection: the loopback listener accepts only its configured authority.
        expected=f'{self.host}:{self.port}'
        if request.host not in {expected, self.host if self.port==80 else expected}:
            raise web.HTTPForbidden(text='Unexpected Host header.')
        locale_token=UI_LANGUAGE.set('en')
        actor_token=self.service.store.actor.set('dashboard')
        try:
            try: response=await handler(request)
            except web.HTTPException as response:
                self.headers(response);raise
            self.headers(response);return response
        finally:
            UI_LANGUAGE.reset(locale_token)
            self.service.store.actor.reset(actor_token)

    @staticmethod
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})

    def session(self,request):
        sid=request.cookies.get('vivi_session',''); session=self.sessions.get(sid)
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
        UI_LANGUAGE.set(self.service.store.option(guild,'language','en'))
        self.service.store.actor.set('dashboard:'+str(session.get('user_id','admin')))
        return session

    def page(self,content):
        content=localize_html(UI_LANGUAGE.get(),content)
        return web.Response(content_type='text/html',text='<!doctype html><html><head><meta charset="utf-8"><title>Vivi Dashboard</title>'
            '<style>body{font:16px system-ui;background:#111827;color:#e5e7eb;max-width:850px;margin:40px auto;padding:20px}'
            'a{color:#87ceeb}form{margin:12px 0;padding:14px;background:#1f2937;border-radius:12px}'
            'button{padding:8px 14px;border:0;border-radius:8px;cursor:pointer}small{color:#aab6c9}'
            'input,select,textarea{box-sizing:border-box;max-width:100%;padding:9px;margin:5px;background:#111827;color:#fff;border:1px solid #6b7280;border-radius:6px}'
            'textarea{width:95%;min-height:70px}summary{font-size:1.3em;cursor:pointer;padding:15px}label{display:block}table{width:100%;text-align:left}td{padding:7px}</style></head><body>'
            '<h1>Vivi · '+html.escape(tr(UI_LANGUAGE.get(),'Server Dashboard'))+'</h1>'+content+'</body></html>')

    async def index(self,request):
        if not request.cookies.get('vivi_session'): return self.page('<p><a href="/login">Sign in with Discord</a></p><p>Local dashboard: server administrators only.</p>')
        session=self.session(request)
        if not request.query.get('guild'):
            guilds=await self.api_guilds(session)
            rows=[f'<li><a href="/?guild={html.escape(gid)}">{html.escape(g["name"])}</a></li>' for gid,g in guilds.items() if self.service.bot.get_guild(int(gid))]
            return self.page('<h2>Your servers</h2><ul>'+''.join(rows)+'</ul>'+self.logout_form(session))
        try: guild=int(request.query['guild'])
        except ValueError: raise web.HTTPBadRequest(text='Invalid server ID.')
        session=await self.authorize(request,guild)
        UI_LANGUAGE.set(self.service.store.option(guild,'language','en'))
        name=html.escape(self.service.bot.get_guild(guild).name)
        forms=[]
        for feature in FEATURES:
            on=enabled(self.service.store,guild,feature)
            forms.append(f'<form action="/feature" method="post"><input type="hidden" name="csrf" value="{session["csrf"]}">'
                         f'<input type="hidden" name="guild" value="{guild}"><input type="hidden" name="feature" value="{feature}">'
                         f'<input type="hidden" name="enabled" value="{str(not on).lower()}"><b>{feature}</b>: {"ON" if on else "OFF"} '
                         f'<button>{"Disable" if on else "Enable"}</button></form>')
        return self.page(f'<h2>{name}</h2><p><a href="/">All servers</a></p><p>Manage Vivi for this server. Optional AI, voice and notification providers need local host configuration.</p><details><summary>Feature switches</summary>'+''.join(forms)+'</details>'+self.settings_forms(guild,session)+self.logout_form(session))

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
        response.set_cookie('vivi_oauth',verifier,max_age=600,httponly=True,samesite='Lax',path='/callback')
        return response

    async def callback(self,request):
        state=request.query.get('state',''); pending=self.states.pop(state,None)
        if (not pending or pending['expires']<time.time()
                or not hmac.compare_digest(pending['verifier'],request.cookies.get('vivi_oauth',''))):
            raise web.HTTPForbidden(text='Invalid or expired login state. Start again at /login.')
        code=request.query.get('code')
        if not code: raise web.HTTPBadRequest(text='Discord login was not completed.')
        payload=dict(client_id=self.client,client_secret=self.secret,grant_type='authorization_code',
                     code=code,redirect_uri=self.redirect)
        async with self.service.session.post(DISCORD+'/oauth2/token',data=payload,allow_redirects=False) as response:
            if response.status!=200: raise web.HTTPUnauthorized(text='Discord rejected this login. Start again.')
            data=await response.json()
        sid=secrets.token_urlsafe(32)
        identity={}
        async with self.service.session.get(DISCORD+'/users/@me',headers={'Authorization':'Bearer '+data['access_token']},allow_redirects=False) as who:
            if who.status!=200: raise web.HTTPUnauthorized(text='Discord identity check failed.')
            identity=await who.json()
        self.sessions[sid]={'user_id':int(identity['id']),'token':data['access_token'],'csrf':secrets.token_urlsafe(32),
                            'expires':time.time()+min(int(data.get('expires_in',3600)),3600)}
        response=web.HTTPFound('/')
        response.set_cookie('vivi_session',sid,max_age=3600,httponly=True,samesite='Lax',path='/')
        response.del_cookie('vivi_oauth',path='/callback')
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
        self.sessions.pop(request.cookies.get('vivi_session',''),None)
        response=web.HTTPSeeOther('/'); response.del_cookie('vivi_session'); return response

    def hidden(self,session,guild):
        return f'<input type="hidden" name="csrf" value="{session["csrf"]}"><input type="hidden" name="guild" value="{guild}">'

    def select(self,name,options,current=0):
        out=f'<select name="{html.escape(name)}">'
        for value,label in options:
            out+=f'<option value="{html.escape(str(value))}"'+(' selected' if str(value)==str(current) else '')+f'>{html.escape(str(label))}</option>'
        return out+'</select>'

    def settings_forms(self,gid,session):
        guild=self.service.bot.get_guild(gid); store=self.service.store; hidden=self.hidden(session,gid)
        texts=[(0,'Not set')]+[(c.id,'#'+c.name) for c in guild.text_channels]
        categories=[(0,'Not set')]+[(c.id,c.name) for c in guild.categories]
        voices=[(0,'Not set')]+[(c.id,c.name) for c in guild.voice_channels]
        roles=[(0,'Not set')]+[(r.id,r.name) for r in guild.roles if not r.is_default() and not r.managed]
        configuration=store.settings(gid)
        setup='<details><summary>Server channels and support staff</summary><form action="/setup" method="post">'+hidden
        for key,options in [('welcome',texts),('category',categories),('staff',roles),('logs',texts)]:
            setup+=f'<label>{key}'+self.select(key,options,configuration[key] if configuration else 0)+'</label>'
        setup+='<button>Save server setup</button></form></details>'
        fields='<details><summary>Welcome, moderation, AI channels and other settings</summary>'
        channel_keys={'goodbye_channel':texts,'birthday_channel':texts,'daily_channel':texts,'raid_channel':texts,
                      'voice_category':categories,'voice_lobby':voices,'autorole':roles,'rules_role':roles}
        for key,typ in OPTION_TYPES.items():
            if key in {'faq','ticket_categories','aliases'}: continue
            default=DEFAULTS.get(key,[] if typ is list else False if typ is bool else 0 if typ is int else '')
            if key=='welcome_text': default=tr(store.option(gid,'language','en'),'Welcome {member} to {server}!')+' '+tr(store.option(gid,'language','en'),'Please read the rules and choose your roles.')
            if key=='goodbye_text': default=tr(store.option(gid,'language','en'),'Goodbye {member}.')
            value=store.option(gid,key,default)
            fields+='<form action="/setting" method="post">'+hidden+f'<input type="hidden" name="name" value="{key}"><label>{key.replace("_"," ")}</label>'
            if key=='ai_channels':
                control='<select name="values" multiple size="5">'+''.join(f'<option value="{ident}"'+(' selected' if ident in value else '')+f'>{html.escape(label)}</option>' for ident,label in texts if ident)+'</select><small>Hold Ctrl to choose several AI channels; clear selections to allow none.</small>'
            elif key in channel_keys: control=self.select('value',channel_keys[key],value)
            elif key=='language': control=self.select('value',[('en','English'),('es','Español'),('fr','Français')],value)
            elif typ is bool: control=self.select('value',[('true','On'),('false','Off')],str(value).lower())
            elif key=='raid_action': control=self.select('value',[('alert','Alert and pause newcomer roles'),('lockdown','Alert and lock selected raid channel')],value)
            elif typ is str or typ is list:
                text=', '.join(str(x) for x in value) if typ is list else value
                control='<textarea name="value">'+html.escape(str(text))+'</textarea>'
            else: control=f'<input name="value" type="number" value="{value}">'
            fields+=control+'<button>Save setting</button></form>'
        fields+='</details>'
        faq='<details><summary>FAQ manager</summary>'
        for question,answer in store.option(gid,'faq',{}).items():
            faq+='<form action="/faq" method="post">'+hidden+f'<b>{html.escape(question)}</b><p>{html.escape(answer)}</p><input type="hidden" name="question" value="{html.escape(question,quote=True)}"><button name="action" value="remove">Remove</button></form>'
        faq+='<form action="/faq" method="post">'+hidden+'<input name="question" maxlength="150" placeholder="Question" required><textarea name="answer" maxlength="1200" placeholder="Answer" required></textarea><button name="action" value="add">Add or update FAQ</button></form></details>'
        tickets='<details><summary>Ticket categories and open tickets</summary>'
        for label,ident in store.option(gid,'ticket_categories',{}).items():
            tickets+='<form action="/ticket-category" method="post">'+hidden+f'{html.escape(label)} → {ident}<input type="hidden" name="label" value="{html.escape(label,quote=True)}"><button name="action" value="remove">Remove category option</button></form>'
        tickets+='<form action="/ticket-category" method="post">'+hidden+'<input name="label" maxlength="32" placeholder="Category label" required>'+self.select('category',categories)+'<button name="action" value="add">Add or update category</button></form><table><tr><th>Channel</th><th>Owner</th><th>Claimed by</th><th>Priority</th></tr>'
        for row in store.db.execute('SELECT * FROM tickets WHERE guild=?',(gid,)):
            meta=self.service.operations.ticket_meta(row['channel'])
            tickets+=f'<tr><td>{row["channel"]}</td><td>{row["user"]}</td><td>{meta["claimed"] or "unclaimed"}</td><td>{html.escape(meta["priority"])}</td></tr>'
        tickets+='</table><p>Staff use /ticket claim, release, priority and category inside the ticket.</p></details>'
        subscriptions='<details><summary>Twitch, YouTube and GitHub notifications</summary>'
        for record in store.records(gid,'notification'):
            d=record['data']
            subscriptions+='<form action="/subscription" method="post">'+hidden+f'<input type="hidden" name="id" value="{record["id"]}">{html.escape(d["provider"])}: {html.escape(d["source"])} → {d["channel"]}<br><small>Last error: {html.escape(d.get("error") or "none recorded")}</small> <button name="action" value="remove">Remove</button></form>'
            subscriptions+='<form action="/subscription-test" method="post">'+hidden+f'<input type="hidden" name="id" value="{record["id"]}"><button>Test provider metadata (no Discord post)</button></form>'
        subscriptions+='<form action="/subscription" method="post">'+hidden+self.select('provider',[(x,x) for x in ['twitch','youtube','github_releases','github_commits']])+self.select('channel',texts)+'<input name="source" placeholder="Twitch login / UC channel ID / owner/repo" required><button name="action" value="add">Add subscription</button></form></details>'
        backup=f'<details><summary>Backup and restore</summary><p><a href="/backup?guild={gid}">Download configuration backup</a></p><form action="/restore" method="post" enctype="multipart/form-data">'+hidden+'<input name="file" type="file" accept=".json" required><label><input name="confirm" type="checkbox" value="yes" required> Replace this server’s configuration with the backup</label><button>Restore configuration</button></form></details>'
        verification='<details><summary>Live permission and provider checks</summary><form action="/verify" method="post">'+hidden+'<label><input name="providers" type="checkbox" value="yes"> Also send a small AI/translation test request (provider charges may apply)</label><button>Run checks without posting Discord messages</button></form></details>'
        return setup+fields+faq+tickets+subscriptions+backup+verification+self.tools_forms(gid,session)

    async def form(self,request):
        data=await request.post(); session=self.session(request)
        if not hmac.compare_digest(session['csrf'],str(data.get('csrf',''))): raise web.HTTPForbidden(text='Invalid form token.')
        try: gid=int(data.get('guild',''))
        except ValueError: raise web.HTTPBadRequest(text='Invalid server.')
        await self.authorize(request,gid)
        UI_LANGUAGE.set(self.service.store.option(gid,'language','en'))
        self.service.store.actor.set('dashboard:'+str(session.get('user_id','admin')))
        return data,session,gid,self.service.bot.get_guild(gid)

    def done(self,guild): raise web.HTTPSeeOther('/?guild='+str(guild))

    async def setting(self,request):
        data,session,gid,guild=await self.form(request)
        try:
            key=str(data.get('name',''))
            if key=='ai_channels':
                values=data.getall('values',[]) if hasattr(data,'getall') else data.get('values',[])
                if isinstance(values,str): values=[values]
                raw=','.join(str(x) for x in values)
            else: raw=str(data.get('value',''))
            value=parse_value(key,raw)
            validate_resources(self.service.store,guild,key,value)
            self.service.store.set_option(gid,key,value)
        except (ValueError,KeyError) as error: raise web.HTTPBadRequest(text=str(error)[:500])
        self.done(gid)

    async def setup(self,request):
        data,session,gid,guild=await self.form(request)
        try:
            settings={k:int(data[k]) for k in ['welcome','category','staff','logs']}
            validate_setup(guild,settings)
            self.service.store.configure(gid,**settings)
        except (ValueError,KeyError) as error: raise web.HTTPBadRequest(text=str(error)[:500])
        self.done(gid)

    async def faq(self,request):
        data,session,gid,guild=await self.form(request); items=self.service.store.option(gid,'faq',{})
        question=str(data.get('question',''))
        if data.get('action')=='remove': items.pop(question,None)
        elif data.get('action')=='add': items[question]=str(data.get('answer',''))
        else: raise web.HTTPBadRequest(text='Invalid FAQ action.')
        try: validate_resources(self.service.store,guild,'faq',items)
        except ValueError as error: raise web.HTTPBadRequest(text=str(error))
        self.service.store.set_option(gid,'faq',items); self.done(gid)

    async def ticket_category(self,request):
        data,session,gid,guild=await self.form(request); categories=self.service.store.option(gid,'ticket_categories',{})
        label=str(data.get('label',''))
        try:
            if data.get('action')=='remove': categories.pop(label,None)
            elif data.get('action')=='add': categories[label]=int(data.get('category','0'))
            else: raise ValueError('Invalid category action.')
            validate_resources(self.service.store,guild,'ticket_categories',categories)
        except ValueError as error: raise web.HTTPBadRequest(text=str(error))
        self.service.store.set_option(gid,'ticket_categories',categories); self.done(gid)

    async def subscription(self,request):
        data,session,gid,guild=await self.form(request)
        if data.get('action')=='remove':
            record=self.service.store.record(str(data.get('id','')))
            if not record or record['guild']!=gid or record['kind']!='notification': raise web.HTTPNotFound(text='Subscription not found.')
            self.service.store.delete_record(record['id'])
        elif data.get('action')=='add':
            from .operations import subscription
            try:
                channel=guild.get_channel(int(data.get('channel','0')))
                if not isinstance(channel,discord.TextChannel): raise ValueError('Select a text channel in this server.')
                if len(self.service.store.records(gid,'notification'))>=20: raise ValueError('Maximum 20 subscriptions.')
                value=subscription(str(data.get('provider','')),str(data.get('source','')),channel.id)
            except ValueError as error: raise web.HTTPBadRequest(text=str(error))
            self.service.store.put_record(gid,'notification',value)
        else: raise web.HTTPBadRequest(text='Invalid subscription action.')
        self.done(gid)

    async def subscription_test(self,request):
        data,session,gid,guild=await self.form(request); record=self.service.store.record(str(data.get('id','')))
        if not record or record['guild']!=gid or record['kind']!='notification': raise web.HTTPNotFound(text='Subscription not found.')
        try:
            events=await self.service.operations.events(record['data'],gid)
            result=f'Provider responded with {len(events)} recent event(s). No Discord notification was posted.'
        except Exception as error: result=f'Provider check failed ({type(error).__name__}). Check the configured source, credentials and API quota.'
        return self.page('<p>'+html.escape(result)+f'</p><a href="/?guild={gid}">Back</a>')

    async def backup(self,request):
        try: gid=int(request.query.get('guild',''))
        except ValueError: raise web.HTTPBadRequest(text='Invalid server.')
        await self.authorize(request,gid)
        return web.Response(body=json.dumps(self.service.store.export_config(gid),indent=2).encode(),content_type='application/json',
                            headers={'Content-Disposition':f'attachment; filename="vivi-config-{gid}.json"'})

    async def restore(self,request):
        data,session,gid,guild=await self.form(request)
        if data.get('confirm')!='yes': raise web.HTTPBadRequest(text='Explicit restore confirmation is required.')
        upload=data.get('file')
        if not isinstance(upload,web.FileField): raise web.HTTPBadRequest(text='Choose a configuration JSON file.')
        try:
            raw=upload.file.read(131073)
            if len(raw)>131072: raise ValueError('Backup must be under 128 KiB.')
            backup=json.loads(raw)
            from .settings import validate_restore
            validate_restore(self.service.store,guild,backup)
            self.service.store.restore_config(gid,backup)
        except (ValueError,KeyError,TypeError) as error: raise web.HTTPBadRequest(text=str(error)[:500])
        from .bot import RoleView
        for record in self.service.store.roles():
            if record['guild']==gid: self.service.bot.add_view(RoleView(self.service.bot,gid,record['role']))
        await self.service.productivity.refresh_configuration(gid)
        self.done(gid)

    async def verify(self,request):
        data,session,gid,guild=await self.form(request)
        from .verify import guild_checks, provider_checks
        checks=guild_checks(self.service.store,guild)+[{'name':'dashboard OAuth','status':'passed','detail':'Current session authenticated and current administrator permissions verified.'}]
        checks+=await provider_checks(self.service.session,data.get('providers')=='yes')
        return self.page('<h2>Verification results</h2>'+''.join('<p><b>'+html.escape(c['name'])+'</b>: '+html.escape(c['status'])+' — '+html.escape(c['detail'])+'</p>' for c in checks)+f'<a href="/?guild={gid}">Back</a>')

    async def start(self):
        if not self.client or not self.secret: raise ValueError('Missing OAuth credentials')
        self.runner=web.AppRunner(self.app,access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner,self.bind_host,self.port).start()

    async def close(self):
        if self.runner: await self.runner.cleanup()
