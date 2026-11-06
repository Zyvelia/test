"""Additional authenticated dashboard workflows; the base dashboard owns auth/CSRF."""
import html
import json

from aiohttp import web
from .bot import ROOT,RoleView
from .features import validate_option
from .productivity import ALIAS_TARGETS,BACKUP_NAME,validate_aliases

class DashboardTools:
    def tools_forms(self,gid,session):
        hidden=self.hidden(session,gid);store=self.service.store
        rows='<details><summary>Dashboard previews</summary><p>Preview only; these buttons never publish to Discord or change settings.</p>'
        for kind,label in [('welcome','Preview welcome card'),('announcement','Preview announcement')]:
            text=store.option(gid,'welcome_text','Welcome {member} to {server}!') if kind=='welcome' else ''
            rows+='<form action="/preview" method="post" target="_blank">'+hidden+f'<input name="type" type="hidden" value="{kind}"><textarea name="text" maxlength="1800" placeholder="Preview text">{html.escape(text)}</textarea>'
            if kind=='welcome': rows+=f'<input name="color" type="color" value="{html.escape(store.option(gid,"welcome_color","#87CEEB"))}">'
            rows+=f'<button>{label}</button></form>'
        rows+='</details><details><summary>Configuration history</summary><p>Last 100 configuration revisions. Rollback affects settings, not messages or personal data.</p>'
        for row in store.history(gid)[:20]:
            rows+=f'<p>#{row["id"]} · {html.escape(row["created"])} · {html.escape(row["actor"])} · {html.escape(row["action"])} · <a href="/revision?guild={gid}&id={row["id"]}">View revision</a></p>'
        rows+='</details><details><summary>Scheduled backups</summary><p>Enable scheduled_backups and choose backup hours / backup keep above. Backups contain configuration only.</p><form action="/backup-now" method="post">'+hidden+'<button>Create backup now</button></form>'
        folder=ROOT/'data'/'backups'/str(gid)
        for path in sorted(folder.glob('config-*.json'),reverse=True)[:30]:
            if BACKUP_NAME.fullmatch(path.name): rows+=f'<p><a href="/scheduled-backup?guild={gid}&name={path.name}">{path.name}</a></p>'
        rows+='</details><details><summary>Custom command aliases</summary><p>Safe informational shortcuts; no moderation actions or raw code.</p>'
        for name,value in store.option(gid,'aliases',{}).items():
            rows+='<form action="/aliases" method="post">'+hidden+f'<input name="name" type="hidden" value="{html.escape(name)}">/{html.escape(name)} → {html.escape(value["target"])} {html.escape(value["argument"])} <button name="action" value="remove">Remove</button></form>'
        rows+='<form action="/aliases" method="post">'+hidden+'<input name="name" maxlength="20" placeholder="New command name" required>'+self.select('target',[(x,x) for x in ALIAS_TARGETS])+'<input name="argument" maxlength="100" placeholder="Fixed FAQ/search argument (optional)"><button name="action" value="add">Add alias</button></form></details>'
        rows+=f'<details><summary>Health dashboard</summary><p><a href="/health?guild={gid}">Open live health dashboard</a></p></details>'
        return rows

    async def authorized_guild(self,request):
        try: gid=int(request.query.get('guild',''))
        except ValueError: raise web.HTTPBadRequest(text='Invalid server.')
        await self.authorize(request,gid);return gid,self.service.bot.get_guild(gid)

    async def preview(self,request):
        data,session,gid,guild=await self.form(request)
        kind=data.get('type');text=str(data.get('text',''))
        try: validate_option('welcome_text',text)
        except ValueError as error: raise web.HTTPBadRequest(text=str(error))
        if kind=='announcement':
            return self.page('<h2>Announcement preview</h2><p>Nothing has been posted to Discord.</p><article><pre style="white-space:pre-wrap">'+html.escape(text)+'</pre></article>')
        if kind!='welcome': raise web.HTTPBadRequest(text='Unknown preview type.')
        accent=str(data.get('color',self.service.store.option(gid,'welcome_color','#87CEEB')))
        try: validate_option('welcome_color',accent)
        except ValueError as error: raise web.HTTPBadRequest(text=str(error))
        from .community import card_bytes
        import asyncio
        member=guild.get_member(int(session.get('user_id',0))) if hasattr(guild,'get_member') else None
        member=member or guild.me
        name=getattr(member,'display_name','Preview member')
        avatar=getattr(member,'display_avatar',None);image=None
        if avatar:
            try: image=await avatar.with_size(256).with_format('png').read()
            except Exception: pass
        from .i18n import tr
        png=await asyncio.to_thread(card_bytes,name,guild.name,text.replace('{member}',name).replace('{server}',guild.name),accent,image, tr(self.service.store.option(gid,'language','en'),'Welcome, {name}!',name=name[:30]),self.service.store.option(gid,'branding',{}).get('name','Vivi'))
        return web.Response(body=png,content_type='image/png')

    async def revision(self,request):
        gid,guild=await self.authorized_guild(request)
        try: ident=int(request.query.get('id',''))
        except ValueError: raise web.HTTPBadRequest(text='Invalid revision.')
        row=self.service.store.revision(gid,ident)
        if not row: raise web.HTTPNotFound(text='Revision not found in this server.')
        session=self.session(request)
        return self.page(f'<h2>Revision #{ident}</h2><p>{html.escape(row["actor"])} · {html.escape(row["action"])}</p>'
            '<h3>Before</h3><pre>'+html.escape(json.dumps(row['before'],indent=2))+'</pre><h3>After</h3><pre>'+html.escape(json.dumps(row['after'],indent=2))+'</pre>'
            '<form action="/rollback" method="post">'+self.hidden(session,gid)+f'<input name="id" value="{ident}" type="hidden"><label><input name="confirm" type="checkbox" value="yes" required> Restore the After configuration from this revision</label><button>Roll back to this configuration</button></form>')

    async def rollback(self,request):
        data,session,gid,guild=await self.form(request)
        if data.get('confirm')!='yes': raise web.HTTPBadRequest(text='Explicit rollback confirmation required.')
        try: ident=int(data.get('id',''))
        except ValueError: raise web.HTTPBadRequest(text='Invalid revision.')
        row=self.service.store.revision(gid,ident)
        if not row: raise web.HTTPNotFound(text='Revision not found in this server.')
        from .settings import validate_restore
        try: validate_restore(self.service.store,guild,row['after'])
        except (ValueError,KeyError,TypeError) as error: raise web.HTTPBadRequest(text=str(error)[:500])
        self.service.store.restore_config(gid,row['after'])
        for record in self.service.store.roles():
            if record['guild']==gid: self.service.bot.add_view(RoleView(self.service.bot,gid,record['role']))
        await self.service.productivity.refresh_configuration(gid)
        self.done(gid)

    async def backup_now(self,request):
        data,session,gid,guild=await self.form(request)
        self.service.productivity.backup(gid);self.done(gid)

    async def scheduled_backup(self,request):
        gid,guild=await self.authorized_guild(request);name=request.query.get('name','')
        if not BACKUP_NAME.fullmatch(name): raise web.HTTPBadRequest(text='Invalid backup filename.')
        folder=ROOT/'data'/'backups'/str(gid);path=folder/name
        if not path.is_file() or not path.resolve().is_relative_to(folder.resolve()): raise web.HTTPNotFound(text='Backup not found.')
        return web.FileResponse(path,headers={'Content-Disposition':f'attachment; filename="{name}"','Content-Type':'application/json'})

    async def aliases(self,request):
        data,session,gid,guild=await self.form(request);values=self.service.store.option(gid,'aliases',{})
        name=str(data.get('name',''))
        if data.get('action')=='remove': values.pop(name,None)
        elif data.get('action')=='add': values[name]=dict(target=str(data.get('target','')),argument=str(data.get('argument','')))
        else: raise web.HTTPBadRequest(text='Invalid alias action.')
        try: validate_aliases(values)
        except ValueError as error: raise web.HTTPBadRequest(text=str(error))
        self.service.store.set_option(gid,'aliases',values)
        try: await self.service.productivity.refresh_aliases(gid)
        except Exception as error:
            self.service.productivity.error('alias sync',error)
            return self.page('<p>Alias configuration saved. Discord command registration failed; use /alias run until restart/retry.</p>')
        self.done(gid)

    async def health(self,request):
        gid,guild=await self.authorized_guild(request)
        data=self.service.productivity.health(gid)
        return self.page('<h2>Health dashboard</h2><p>Refresh to update. Connection and job status are observed, not assumed.</p><pre>'+html.escape(json.dumps(data,indent=2))+'</pre>')
