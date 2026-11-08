"""Administrator-only change log, diagnostic buttons and privacy-request review."""
import html
import json
import time
from urllib.parse import urlencode
from aiohttp import web
import discord
from vivi.core.features import validate_option
from vivi.core.privacy import RETENTION
from vivi.core.policy import safe_self_role
from vivi.site.module_manager import family_navigation
from vivi.site.staff_dashboard import member_name

E=lambda value:html.escape(str(value),quote=True)
MISSING=object()

def changes(before,after,path=''):
    if isinstance(before,dict) and isinstance(after,dict):
        result=[]
        for key in sorted(before.keys()|after.keys()):result+=changes(before.get(key,MISSING),after.get(key,MISSING),path+'.'+key if path else key)
        return result
    return [] if before==after else [(path,before,after)]

def display(value):return '(not set)' if value is MISSING else json.dumps(value,ensure_ascii=False,indent=2)

class DashboardCare:
    def care_routes(self):
        return [web.get('/changes',self.change_log),web.get('/checks',self.checks_page),web.post('/checks',self.run_checks),web.get('/privacy-settings',self.privacy_settings),web.post('/privacy-settings',self.save_privacy),web.post('/privacy-review',self.privacy_review)]
    async def care_member(self,session,gid):
        _,_,guild,access=await self.staff_membership(session,gid)
        if not access['admin']:raise web.HTTPForbidden(text='Only current server administrators can access configuration history and privacy requests.')
        return guild
    async def care_access(self,request):
        gid,_=await self.authorized_guild(request);session=self.session(request)
        return session,gid,await self.care_member(session,gid)
    async def care_form(self,request):
        data,session,gid,_=await self.form(request)
        return data,session,gid,await self.care_member(session,gid)
    def care_page(self,gid,body):
        response=self.page(body)
        response.text=response.text.replace('<nav data-dashboard-sections aria-label="Server modules"></nav>','<nav data-dashboard-sections aria-label="Server modules">'+family_navigation(gid)+'</nav>')
        return response
    async def change_log(self,request):
        session,gid,guild=await self.care_access(request);store=self.service.store
        query=request.query.get('search','')[:100].strip();ident=request.query.get('id','')
        body='<h2>Dashboard change log</h2><p>Who changed a setting, when (UTC), and its previous and new values. Up to 100 configuration revisions are retained; age limits may remove older entries.</p>'
        body+=f'<form method="get"><input type="hidden" name="guild" value="{gid}"><label>Search setting, action or staff ID <input name="search" maxlength="100" value="{E(query)}"></label><button>Search changes</button></form>'
        if ident:
            try:row=store.revision(gid,int(ident))
            except ValueError:raise web.HTTPBadRequest(text='Invalid revision.')
            if not row:raise web.HTTPNotFound(text='Revision not found in this server.')
            rows=[row]
        else:
            rows=[]
            for item in store.history(gid):
                row=store.revision(gid,item['id'])
                if query.lower() in (row['actor']+' '+row['action']+' '+json.dumps(changes(row['before'],row['after']),default=lambda x:'(not set)',ensure_ascii=False)).lower():rows.append(row)
        try:page=int(request.query.get('page','0'))
        except ValueError:raise web.HTTPBadRequest(text='Invalid page.')
        if not 0<=page<=100:raise web.HTTPBadRequest(text='Invalid page.')
        for row in rows[page*20:page*20+20]:
            actor=row['actor'];user=actor.split(':')[-1]
            if user.isdigit():actor=member_name(guild,user)+' · '+actor.split(':')[0]
            body+=f'<article class="change-entry"><h3>#{row["id"]} · {E(row["action"])}</h3><p>{E(actor)} · {E(row["created"])} UTC</p>'
            delta=changes(row['before'],row['after'])
            if ident:
                body+='<div class="change-table"><table><thead><tr><th>Setting</th><th>Previous value</th><th>New value</th></tr></thead><tbody>'+''.join(f'<tr><th>{E(path)}</th><td><pre>{E(display(old))}</pre></td><td><pre>{E(display(new))}</pre></td></tr>' for path,old,new in delta)+'</tbody></table></div>'
                body+=f'<a href="/revision?guild={gid}&id={row["id"]}">Full revision and restore options →</a>'
            else:body+='<p>'+E(', '.join(path for path,_,_ in delta[:8]) or 'Configuration restored')+f'</p><a href="/changes?guild={gid}&id={row["id"]}">Compare values →</a>'
            body+='</article>'
        if not rows:body+='<p>No matching configuration changes.</p>'
        for label,target in [('Previous',page-1),('Next',page+1)]:
            if target>=0 and (label=='Previous' or len(rows)>(page+1)*20):body+='<a class="btn" href="/changes?'+E(urlencode(dict(guild=gid,search=query,page=target)))+'">'+label+'</a>'
        return self.care_page(gid,body)
    def test_controls(self,gid,session,kind='all'):
        body='<section class="diagnostic-controls"><h3>Test your setup</h3><p>Permission checks do not post messages or assign roles.</p>'
        for key,label in [('notifications','Check notification destinations'),('roles','Test role permissions')]:
            if kind not in ('all',key):continue
            body+='<form action="/checks" method="post">'+self.hidden(session,gid)+f'<input name="kind" value="{key}" type="hidden"><button>{label}</button></form>'
        return body+f'<p><a href="/configure?guild={gid}&module=welcome">Send a sample welcome from the Welcome editor →</a></p></section>'
    async def checks_page(self,request):
        session,gid,guild=await self.care_access(request)
        return self.care_page(gid,'<h2>Setup tests</h2>'+self.test_controls(gid,session))
    async def run_checks(self,request):
        data,session,gid,guild=await self.care_form(request);kind=data.get('kind');store=self.service.store;results=[]
        if kind=='notifications':
            for row in store.records(gid,'notification'):
                value=row['data'];channel=guild.get_channel(value.get('channel',0));label=f'{value.get("provider","Notification")} · channel {value.get("channel",0)}'
                if not isinstance(channel,discord.TextChannel):results.append((label,False,'Destination text channel is missing.'));continue
                permissions=channel.permissions_for(guild.me);missing=[name for name in ('view_channel','send_messages','embed_links') if not getattr(permissions,name)]
                results.append((label,not missing,'Missing: '+', '.join(missing) if missing else 'Vivi can view this destination and send messages and embeds.'))
            if not results:results.append(('Notifications',False,'No notification subscriptions configured.'))
        elif kind=='roles':
            allowed=guild.me.guild_permissions.manage_roles
            results.append(('Manage Roles',allowed,'Available.' if allowed else 'Grant Vivi Manage Roles to assign roles.'))
            config=store.settings(gid)
            protected={guild.default_role.id}
            if config:protected.add(config['staff'])
            role_ids=set(row['role'] for row in store.roles() if row['guild']==gid)
            role_ids.update(store.option(gid,key,0) for key in ('autorole','rules_role'))
            for ident in sorted(role_ids-{0}):
                role=guild.get_role(ident)
                safe=bool(role and ident not in protected and safe_self_role(role,guild.me))
                results.append((f'Role {ident}',allowed and safe,'Assignable by Vivi; still subject to current channel/member restrictions.' if allowed and safe else 'Missing, protected, managed, privileged, or above Vivi’s highest role.'))
            if not role_ids-{0}:results.append(('Role selections',False,'No automatic, rules or selectable role has been configured.'))
        else:raise web.HTTPBadRequest(text='Choose a supported test.')
        body='<h2>Test results</h2><p>No Discord messages were sent and no roles were changed. Provider delivery is not tested by permission checks.</p>'+''.join(f'<article class="change-entry"><h3>{E(label)} · {"Passed" if passed else "Needs attention"}</h3><p>{E(detail)}</p></article>' for label,passed,detail in results)
        return self.care_page(gid,body+self.test_controls(gid,session,kind))
    async def privacy_settings(self,request):
        session,gid,guild=await self.care_access(request);store=self.service.store
        body=('<p role="status">Privacy settings saved.</p>' if request.query.get('saved')=='yes' else '')+'<h2>Privacy & retention</h2><p>Administrator-only. Members can use <code>/tools delete_data</code> and confirm to remove supported personal data and request staff review of retained records. See the <a href="/privacy">Privacy Policy</a> and <a href="/support">contact details</a>.</p>'
        body+='<h3>Retention settings</h3><p>0 keeps records until manually removed (change log still has a 100-revision cap). Otherwise choose 7–3,650 days. Cleanup runs while Vivi is online, approximately every 10 minutes. Existing records older than a newly enabled limit will be removed. This does not delete moderation evidence, transcripts, Discord messages, exports or backups.</p><form method="post" action="/privacy-settings">'+self.hidden(session,gid)
        for key,label in RETENTION.items():body+=f'<label>{E(label)} (days) <input type="number" name="{key}" min="0" max="3650" required value="{store.option(gid,key,0)}"></label>'
        body+='<label><input type="checkbox" name="confirm" value="yes" required> Apply these retention limits to existing and future records.</label><button>Save retention settings</button></form><h3>Deletion request queue</h3><p>Completing a review records your explanation; it does not automatically delete retained records or backups. Do not close a request until you have reviewed it and contacted the requester as appropriate.</p>'
        rows=store.records(gid,'privacy')[::-1]
        try:page=int(request.query.get('page','0'))
        except ValueError:raise web.HTTPBadRequest(text='Invalid page.')
        if not 0<=page<=10000:raise web.HTTPBadRequest(text='Invalid page.')
        body+=f'<p>Requests · page {page+1}</p>'
        for row in rows[page*25:(page+1)*25]:
            d=row['data'];status='completed' if d.get('status')=='accepted' else d.get('status','pending')
            body+=f'<article class="change-entry"><h3>Request {E(row["id"])} · {E(status)}</h3><p>Member: {E(member_name(guild,d.get("author",0)))}</p><p>{E(d.get("text",""))}</p>'
            if d.get('reviewer'):body+=f'<p>Reviewed by {E(member_name(guild,d["reviewer"]))} · {E(d.get("reviewed_at",""))} UTC</p>'
            body+='<form method="post" action="/privacy-review">'+self.hidden(session,gid)+f'<input type="hidden" name="id" value="{E(row["id"])}"><label>Review status '+self.select('status',[('pending','Pending'),('reviewing','In review'),('completed','Review completed'),('declined','Declined with explanation')],status)+'</label><label>Private review note — explain what was removed or retained, and why<textarea name="note" required maxlength="1200">'+E(d.get('review_note',d.get('response','')))+'</textarea></label><button>Save review</button></form></article>'
        if not rows:body+='<p>No deletion requests awaiting review.</p>'
        for label,target in [('Previous',page-1),('Next',page+1)]:
            if target>=0 and (label=='Previous' or len(rows)>(page+1)*25):body+=f'<a class="btn" href="/privacy-settings?guild={gid}&page={target}">{label}</a>'
        body+='<h3>Access boundaries</h3><p>Only current administrators can view this page, settings history or retention controls. Moderation staff and support staff have separate permissions for cases and tickets. Browser drafts are stored locally for up to seven days; discard them in each editor. The deletion command cannot erase browser storage or backup copies.</p>'
        return self.care_page(gid,body)
    async def save_privacy(self,request):
        data,session,gid,guild=await self.care_form(request)
        if data.get('confirm')!='yes':raise web.HTTPBadRequest(text='Confirm retention limits before saving.')
        try:
            values={key:int(data[key]) for key in RETENTION}
            for key,value in values.items():validate_option(key,value)
        except (ValueError,TypeError,KeyError):raise web.HTTPBadRequest(text='Use 0 to disable age-based cleanup, or 7–3,650 days.') from None
        store=self.service.store;before=store.export_config(gid)
        with store.db:
            store.db.executemany('INSERT OR REPLACE INTO options VALUES (?,?,?)',[(gid,key,json.dumps(value)) for key,value in values.items()]);store.log_config(gid,'privacy retention settings',before)
        raise web.HTTPSeeOther(f'/privacy-settings?guild={gid}&saved=yes')
    async def privacy_review(self,request):
        data,session,gid,guild=await self.care_form(request);row=self.service.store.record(str(data.get('id','')))
        if not row or row['guild']!=gid or row['kind']!='privacy':raise web.HTTPNotFound(text='Request not found in this server.')
        status=data.get('status');note=str(data.get('note','')).strip()
        if status not in {'pending','reviewing','completed','declined'} or not 1<=len(note)<=1200:raise web.HTTPBadRequest(text='Choose a valid status and provide a review note (1–1,200 characters).')
        import datetime as dt
        record={**row['data'], 'status':status,'review_note':note,'reviewer':session['user_id'],'reviewed_at':dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}
        record['resolved_at']=time.time() if status in {'completed','declined'} else None
        self.service.store.put_record(gid,'privacy',record,row['id'])
        raise web.HTTPSeeOther(f'/privacy-settings?guild={gid}&saved=yes')
