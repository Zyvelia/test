"""Server-scoped staff overview, moderation records, review queue and tickets."""
import html
import asyncio
import aiohttp
import time
from urllib.parse import urlencode
import discord
from aiohttp import web
from vivi.core.features import FEATURES
from vivi.site.module_manager import module_enabled
from vivi.site.website import server_avatar

E=lambda value:html.escape(str(value),quote=True)

def number(value,label='ID'):
    value=str(value)
    if not value.isascii() or not value.isdigit() or not 0<int(value)<2**63:raise web.HTTPBadRequest(text=f'Invalid {label}.')
    return int(value)

def member_name(guild,ident):
    lookup=getattr(guild,'get_member',None)
    try:member=lookup(int(ident)) if callable(lookup) else None
    except (ValueError,TypeError):member=None
    return f'{member.display_name} ({ident})' if member else str(ident)


def age(seconds):
    if seconds is None:return 'Not recorded'
    seconds=max(0,int(seconds))
    if seconds<60:return f'{seconds}s'
    if seconds<3600:return f'{seconds//60}m'
    if seconds<86400:return f'{seconds//3600}h {(seconds%3600)//60}m'
    return f'{seconds//86400}d {(seconds%86400)//3600}h'

class StaffDashboard:
    def staff_routes(self):return [web.get('/staff',self.staff_home),web.get('/staff/cases',self.staff_cases),web.get('/staff/queue',self.staff_queue),web.get('/staff/tickets',self.staff_tickets)]
    async def staff_access(self,request,area='home'):
        session=self.session(request);gid=number(request.query.get('guild',''),'server ID')
        return await self.staff_membership(session,gid,area)
    async def staff_membership(self,session,gid,area='home'):
        guild=self.service.bot.get_guild(gid)
        if not guild:raise web.HTTPForbidden(text='Staff access is required in a server where Vivi is installed.')
        try:member=await guild.fetch_member(session['user_id'])
        except (discord.NotFound,discord.Forbidden):raise web.HTTPForbidden(text='Current server staff membership could not be verified.') from None
        except (discord.HTTPException,aiohttp.ClientError,asyncio.TimeoutError):raise web.HTTPServiceUnavailable(text='Discord could not verify staff permissions. Try again shortly.') from None
        permissions=member.guild_permissions;admin=permissions.administrator or member.id==guild.owner_id
        moderate=admin or permissions.moderate_members
        settings=self.service.store.settings(gid)
        support=admin or permissions.manage_channels or bool(settings and any(role.id==settings['staff'] for role in member.roles))
        if not (moderate if area=='moderation' else support if area=='tickets' else moderate or support):raise web.HTTPForbidden(text='This page is available only to authorized server staff.')
        return session,gid,guild,dict(admin=admin,moderation=moderate,tickets=support)
    def server_home_card(self,gid):
        guild=self.service.bot.get_guild(gid);count=getattr(guild,'member_count',None);on=sum(module_enabled(self,gid,key) for key in FEATURES if key not in {'faq','welcome_cards'});total=len(FEATURES)-2
        ready=self.service.bot.is_ready()
        return f'<section class="server-home-card" aria-label="Server overview"><div><span class="eyebrow">Your server at a glance</span><h2>{E(guild.name)}</h2></div><dl><div><dt>Members</dt><dd>{E(count if count is not None else "Unavailable")}</dd></div><div><dt>Vivi status</dt><dd><span class="small-status"><i class="status-dot'+('' if ready else ' is-offline')+f'"></i><span data-home-status>{"Online" if ready else "Offline"}</span></span></dd></div><div><dt>Enabled modules</dt><dd><span data-enabled-count>{on}</span> <small>/ {total}</small></dd></div></dl></section>'
    def staff_navigation(self,gid,access,active='home'):
        links=[('home','Home','/staff')]
        if access['moderation']:links += [('cases','Cases','/staff/cases'),('queue','Reports & appeals','/staff/queue')]
        if access['tickets']:links += [('tickets','Tickets','/staff/tickets')]
        if access['admin']:links += [('modules','Manage features','/modules'),('embeds','Saved embeds','/embeds')]
        return '<nav class="related-modules staff-nav" aria-label="Staff workspace">'+''.join(f'<a href="{path}?guild={gid}"'+(' aria-current="page"' if key==active else '')+f'>{label}</a>' for key,label,path in links)+'</nav>'
    def staff_page(self,gid,access,active,body):
        response=self.page(self.staff_navigation(gid,access,active)+body)
        if not access['admin']:
            # Staff get the tools their current server role permits, without administrator controls.
            start=response.text.index('<aside class="dashboard-rail">');end=response.text.index('</aside>',start)+len('</aside>')
            response.text=response.text[:start]+'<aside class="dashboard-rail"><div class="rail-label">Staff workspace</div>'+self.staff_navigation(gid,access,active)+'</aside>'+response.text[end:]
        return response
    async def staff_home(self,request):
        if not request.query.get('guild'):
            session=self.session(request);servers=await self.api_guilds(session,include_all=True)
            try:page=int(request.query.get('page','0'))
            except ValueError:raise web.HTTPBadRequest(text='Invalid page.')
            if not 0<=page<=10000:raise web.HTTPBadRequest(text='Invalid page.')
            installed=[int(ident) for ident in servers if self.service.bot.get_guild(int(ident))];cards=[]
            for ident in installed[page*20:page*20+20]:
                try:_,gid,guild,access=await self.staff_membership(session,ident)
                except web.HTTPForbidden:continue
                avatar=server_avatar(gid,guild.name,servers[str(gid)].get('icon') or getattr(getattr(guild,'icon',None),'key',None))
                cards.append(f'<article class="server-card">{avatar}<h3>{E(guild.name)}</h3><p>Staff access verified.</p><a class="btn btn-primary" href="/staff?guild={gid}">Open staff workspace</a></article>')
            body='<h2>Your staff servers</h2><p>Only servers where your current role allows staff access appear here.</p><div class="server-grid">'+(''.join(cards) or '<p>No authorized staff servers on this page.</p>')+'</div>'
            if page:body+=f'<a href="/staff?page={page-1}">Previous</a> '
            if len(installed)>(page+1)*20:body+=f'<a href="/staff?page={page+1}">Next</a>'
            return self.page(body)
        session,gid,guild,access=await self.staff_access(request)
        cards=[]
        if access['moderation']:
            cases=self.service.store.db.execute('SELECT count(*) FROM cases WHERE guild=?',(gid,)).fetchone()[0]
            pending=sum(r['data'].get('status')=='pending' for r in self.service.store.records(gid) if r['kind'] in {'report','appeal'})
            cards += [('Cases',cases,'/staff/cases'),('Pending reports & appeals',pending,'/staff/queue')]
        if access['tickets']:
            tickets=self.service.store.db.execute('SELECT count(*) FROM tickets WHERE guild=?',(gid,)).fetchone()[0];cards += [('Open tickets',tickets,'/staff/tickets')]
        return self.staff_page(gid,access,'home',self.server_home_card(gid)+'<div class="staff-summary-grid">'+''.join(f'<a class="staff-summary" href="{path}?guild={gid}"><span>{label}</span><strong>{count}</strong></a>' for label,count,path in cards)+'</div><p>Staff permissions are checked with Discord on every visit. Configuration changes remain administrator-only.</p>')
    async def staff_cases(self,request):
        session,gid,guild,access=await self.staff_access(request,'moderation');store=self.service.store
        if request.query.get('case'):
            ident=number(request.query['case'],'case number');row=store.db.execute('SELECT * FROM cases WHERE guild=? AND id=?',(gid,ident)).fetchone()
            if row is None:raise web.HTTPNotFound(text='Case not found in this server.')
            body=f'<a href="/staff/cases?guild={gid}">← Cases</a><h2>Case #{row["id"]}</h2><dl class="case-details">'+''.join(f'<div><dt>{label}</dt><dd>{E(member_name(guild,row[key]) if key in {'user','moderator'} else row[key])}</dd></div>' for label,key in [('Member ID','user'),('Action','action'),('Staff member ID','moderator'),('Time (UTC)','created'),('Reason','reason')])+'</dl>'
            return self.staff_page(gid,access,'cases',body)
        user=request.query.get('member','').strip();action=request.query.get('action','')[:80];reason=request.query.get('reason','')[:300]
        try:page=int(request.query.get('page','0'))
        except ValueError:raise web.HTTPBadRequest(text='Invalid page.')
        if not 0<=page<=10000:raise web.HTTPBadRequest(text='Invalid page.')
        sql='SELECT * FROM cases WHERE guild=?';args=[gid]
        if user:sql+=' AND user=?';args.append(number(user,'member ID'))
        if action:sql+=' AND action=?';args.append(action)
        if reason:sql+=' AND instr(lower(reason),lower(?))>0';args.append(reason)
        rows=store.db.execute(sql+' ORDER BY id DESC LIMIT 51 OFFSET ?',[*args,page*50]).fetchall()
        actions=store.db.execute('SELECT DISTINCT action FROM cases WHERE guild=? ORDER BY action LIMIT 50',(gid,)).fetchall()
        body=f'<h2>Moderation cases</h2><form class="staff-filters" method="get" action="/staff/cases"><input type="hidden" name="guild" value="{gid}"><label>Member ID<input name="member" value="{E(user)}" inputmode="numeric"></label><label>Action '+self.select('action',[('','All actions')]+[(r['action'],r['action']) for r in actions],action)+f'</label><label>Words in reason<input name="reason" maxlength="300" value="{E(reason)}"></label><button>Search cases</button></form><div class="staff-table-wrap"><table><caption>Cases in this server</caption><thead><tr><th>Case</th><th>Member</th><th>Action</th><th>Staff</th><th>Time (UTC)</th><th>Reason</th></tr></thead><tbody>'
        body+=''.join(f'<tr><td><a href="/staff/cases?guild={gid}&case={r["id"]}">#{r["id"]}</a></td><td>{E(member_name(guild,r["user"]))}</td><td>{E(r["action"])}</td><td>{E(member_name(guild,r["moderator"]))}</td><td>{E(r["created"])}</td><td>{E(r["reason"][:160])}</td></tr>' for r in rows[:50]) or '<tr><td colspan="6">No matching cases.</td></tr>'
        body+='</tbody></table></div><nav aria-label="Case pages">'
        for label,next_page in [('Previous',page-1),('Next',page+1)]:
            if next_page>=0 and (label=='Previous' or len(rows)>50):body+='<a class="btn btn-ghost" href="/staff/cases?'+E(urlencode(dict(guild=gid,member=user,action=action,reason=reason,page=next_page)))+'">'+label+'</a>'
        return self.staff_page(gid,access,'cases',body+'</nav>')
    async def staff_queue(self,request):
        session,gid,guild,access=await self.staff_access(request,'moderation');kind=request.query.get('kind','all');status=request.query.get('status','pending')
        if kind not in {'all','report','appeal'} or status not in {'all','pending','accepted','declined'}:raise web.HTTPBadRequest(text='Invalid queue filter.')
        rows=[r for r in self.service.store.records(gid) if r['kind'] in {'report','appeal'} and (kind=='all' or r['kind']==kind) and (status=='all' or r['data'].get('status')==status)]
        rows.sort(key=lambda r:(r['data'].get('created',0),r['id']),reverse=True)
        try:page=int(request.query.get('page','0'))
        except ValueError:raise web.HTTPBadRequest(text='Invalid page.')
        if not 0<=page<=10000:raise web.HTTPBadRequest(text='Invalid page.')
        body=f'<h2>Reports & appeals</h2><form class="staff-filters" method="get"><input type="hidden" name="guild" value="{gid}"><label>Type '+self.select('kind',[('all','Reports and appeals'),('report','Reports'),('appeal','Appeals')],kind)+'</label><label>Status '+self.select('status',[(v,v.title()) for v in ['pending','accepted','declined','all']],status)+'</label><button>Filter queue</button></form><p>Use /mod review in Discord to record a decision. Reviewing does not automatically change a ban or timeout.</p>'
        for row in rows[page*50:(page+1)*50]:
            d=row['data'];body+=f'<details class="staff-request"><summary>{E(row["kind"].title())} #{E(row["id"])} · {E(d.get("status","pending"))}</summary><dl><dt>Submitted by</dt><dd>{E(member_name(guild,d.get("author","Unknown")))}</dd><dt>{"Case" if row["kind"]=="appeal" else "Reported member"}</dt><dd>{E(d.get("case",d.get("target","Unknown")))}</dd><dt>Message</dt><dd>{E(d.get("text",""))}</dd>'
            if d.get('response'):body+=f'<dt>Staff response</dt><dd>{E(d["response"])}</dd><dt>Reviewer</dt><dd>{E(d.get("reviewer","Unknown"))}</dd>'
            body+='</dl></details>'
        if not rows:body+='<p>No requests match these filters.</p>'
        for label,index in [('Previous',page-1),('Next',page+1)]:
            if index>=0 and (label=='Previous' or len(rows)>(page+1)*50):body+='<a class="btn btn-ghost" href="/staff/queue?'+E(urlencode(dict(guild=gid,kind=kind,status=status,page=index)))+'">'+label+'</a>'
        return self.staff_page(gid,access,'queue',body)
    async def staff_tickets(self,request):
        session,gid,guild,access=await self.staff_access(request,'tickets');store=self.service.store;now=time.time();items=[];seen=set()
        for row in store.db.execute('SELECT * FROM tickets WHERE guild=? ORDER BY channel DESC',(gid,)):
            channel=guild.get_channel(row['channel']);meta=self.service.operations.ticket_meta(row['channel']);seen.add(row['channel'])
            event=store.db.execute("SELECT min(at) opened FROM ticket_events WHERE guild=? AND channel=? AND action='opened'",(gid,row['channel'])).fetchone()
            latest=store.db.execute('SELECT action FROM ticket_events WHERE guild=? AND channel=? ORDER BY id DESC LIMIT 1',(gid,row['channel'])).fetchone()
            opened=event['opened'] or (channel.created_at.timestamp() if channel and getattr(channel,'created_at',None) else None)
            items.append(dict(channel=row['channel'],user=row['user'],status='Channel missing' if not channel else 'Closing' if latest and latest['action']=='closing' else 'Open',priority=meta.get('priority','normal'),claimed=meta.get('claimed',0),age=age(now-opened if opened is not None else None)))
        for row in store.records(gid,'ticket_rating'):
            d=row['data'];channel=d.get('channel')
            if not channel or channel in seen:continue
            seen.add(channel);events=store.db.execute("SELECT min(CASE WHEN action='opened' THEN at END) opened,max(CASE WHEN action='closed' THEN at END) ended FROM ticket_events WHERE guild=? AND channel=?",(gid,channel)).fetchone()
            items.append(dict(channel=channel,user=d.get('user','Unknown'),status='Closed',priority=d.get('priority','normal'),claimed=d.get('claimed',0),age=age(events['ended']-events['opened'] if events['opened'] is not None and events['ended'] is not None else None)))
        status=request.query.get('status','all')
        if status not in {'all','Open','Closing','Closed','Channel missing'}:raise web.HTTPBadRequest(text='Invalid ticket status.')
        items=[r for r in items if status=='all' or r['status']==status]
        try:page=int(request.query.get('page','0'))
        except ValueError:raise web.HTTPBadRequest(text='Invalid page.')
        if not 0<=page<=10000:raise web.HTTPBadRequest(text='Invalid page.')
        body=f'<h2>Support tickets</h2><form method="get" class="staff-filters"><input type="hidden" name="guild" value="{gid}"><label>Status '+self.select('status',[(v,'All statuses' if v=='all' else v) for v in ['all','Open','Closing','Closed','Channel missing']],status)+'</label><button>Filter tickets</button></form><p>Open tickets and retained closed-ticket records. Age is elapsed time since opening, or recorded duration for closed tickets. Older tickets without a timestamp show “Not recorded”.</p><div class="staff-table-wrap"><table><caption>Ticket status and ownership</caption><thead><tr><th>Channel</th><th>Member</th><th>Status</th><th>Priority</th><th>Claimed by</th><th>Age</th></tr></thead><tbody>'
        for row in items[page*50:(page+1)*50]:body+=f'<tr><td>{E(row["channel"])}</td><td>{E(member_name(guild,row["user"]))}</td><td>{E(row["status"])}</td><td>{E(row["priority"])}</td><td>{E(member_name(guild,row["claimed"]) if row["claimed"] else "Unclaimed")}</td><td>{E(row["age"])}</td></tr>'
        if not items:body+='<tr><td colspan="6">No matching tickets.</td></tr>'
        body+='</tbody></table></div>'
        for label,index in [('Previous',page-1),('Next',page+1)]:
            if index>=0 and (label=='Previous' or len(items)>(page+1)*50):body+='<a class="btn btn-ghost" href="/staff/tickets?'+E(urlencode(dict(guild=gid,status=status,page=index)))+'">'+label+'</a>'
        return self.staff_page(gid,access,'tickets',body)
