"""Authenticated dashboard editors. All writes use existing fresh OAuth and CSRF checks."""
import hashlib
import html
import json
import re
from pathlib import Path
import discord
from aiohttp import web
from vivi.site.studio_layout import DEFAULT_LAYOUT,validate_layout,render_layout,validate_announcement,announcement_embed
from vivi.core.a11y import audit_html
from vivi.core.updates import check_updates

class StudioDashboard:
    def studio_routes(self):
        return [web.get('/assets/studio.js',self.studio_script),web.post('/studio/layout',self.panel_layout),web.post('/studio/welcome',self.welcome_editor),web.post('/studio/announcement',self.announcement_editor),web.post('/studio/audit',self.accessibility_audit),web.post('/studio/updates',self.release_check)]
    async def studio_script(self,request): return web.Response(text=(Path(__file__).parent/'static'/'studio.js').read_text(),content_type='application/javascript')
    def studio_forms(self,gid,session):
        if not session.get('user_id'): return ''
        hidden=self.hidden(session,gid); profile=self.service.store.profile(gid,session['user_id'])
        welcome=html.escape(json.dumps(self.service.store.option(gid,'welcome_layout',DEFAULT_LAYOUT)),quote=True)
        blocks=html.escape(json.dumps(profile.get('announcement_draft',[{'type':'title','value':'Community announcement'},{'type':'text','value':'Write your announcement here.'}])),quote=True)
        channels=[(c.id,'#'+c.name) for c in self.service.bot.get_guild(gid).text_channels]
        return ('<details><summary>Dashboard studio</summary><p>Drag panels or use Move up/down, then save your layout. Editors also provide keyboard controls.</p>'
            '<form method="post" action="/studio/layout" id="panel-layout-form">'+hidden+'<input name="layout" type="hidden" value="[]"><button>Save my panel order</button></form>'
            '<h2>Welcome-card layout editor</h2><form method="post" action="/studio/welcome" data-editor="welcome">'+hidden+f'<input name="document" type="hidden" value="{welcome}">'
            '<label>Card style <select name="card_style"><option value="velvet">Vivi velvet neon</option><option value="plain">Plain</option></select></label><label>Background <input name="background" type="color" value="#121826"></label><canvas width="900" height="260" tabindex="0" aria-label="Welcome card preview; use the labeled fields to edit elements"></canvas>'
            '<p>Drag an element in the preview, or change X and Y below. The avatar is the joining member’s avatar. Text clips at card edges.</p><div class="editor-elements"></div>'
            '<label>New element type <select class="new-type"><option>text</option><option>avatar</option><option>header</option><option>server</option><option>message</option><option>brand</option></select></label><button type="button" class="add-element">Add element</button>'
            '<button name="action" value="preview">Preview PNG</button><button name="action" value="save">Save welcome layout</button><button name="action" value="reset">Restore default layout</button></form>'
            '<h2>Announcement builder</h2><form method="post" action="/studio/announcement" data-editor="announcement">'+hidden+f'<input name="document" type="hidden" value="{blocks}">'
            '<div class="editor-elements"></div><label>New block type <select class="new-type"><option>text</option><option>title</option><option>field</option><option>divider</option></select></label><button type="button" class="add-element">Add block</button>'
            '<h3>Announcement preview</h3><div class="announcement-preview" aria-live="polite"></div><label>Publish channel '+self.select('channel',channels)+'</label>'
            '<label><input type="checkbox" name="confirm" value="yes"> I confirm publication to this channel</label><button name="action" value="draft">Save my draft</button><button name="action" value="preview">Preview on server</button><button name="action" value="publish">Publish announcement</button></form>'
            '<h2>Accessibility checks</h2><form method="post" action="/studio/audit">'+hidden+'<p>Checks labels, headings, IDs, image alternatives and status regions in this dashboard. Manual keyboard and screen-reader testing is still needed.</p><button>Run static dashboard audit</button></form>'
            '<h2>Vivi release information</h2><form method="post" action="/studio/updates">'+hidden+'<button>Check published releases</button></form></details>')
    def personalize(self,content,gid,session):
        # Only top-level sections: summaries elsewhere are not rearranged.
        counter=[0]
        def identify(match):
            attributes,label=match.groups(); ident=hashlib.sha256(label.encode()).hexdigest()[:12]; counter[0]+=1
            return f'<details{attributes} data-panel="{ident}"><summary>'+label+'</summary>'
        content=re.sub(r'<details([^>]*)><summary>([^<]+)</summary>',identify,content)
        order=self.service.store.profile(gid,session['user_id']).get('dashboard_layout',[]) if session.get('user_id') else []
        return ('<div id="dashboard-controls"><div class="settings-global-search"><label for="settings-search">Search all settings</label><input id="settings-search" type="search" maxlength="100" autocomplete="off" placeholder="Welcome, raid protection, birthdays…" aria-controls="settings-search-results"><span id="settings-search-status" role="status" aria-live="polite"></span><div id="settings-search-results" hidden></div></div><button id="palette-open" type="button">Search settings (Ctrl+K)</button><details id="mobile-navigation"><summary>Jump to section</summary><nav id="section-links" aria-label="Dashboard sections"></nav></details></div>'
            '<dialog id="command-palette" aria-labelledby="palette-title"><h2 id="palette-title">Find settings and actions</h2><label>Search dashboard <input id="palette-search" type="search" autocomplete="off" aria-controls="palette-results"></label><p>Results open the matching control. They do not submit changes.</p><div id="palette-results" aria-live="polite"></div><button id="palette-close" type="button">Close search</button></dialog>'
            '<div id="dashboard-panels" data-order="'+html.escape(json.dumps(order),quote=True)+'">'+content+'</div>')
    async def panel_layout(self,request):
        data,session,gid,guild=await self.form(request)
        try:
            order=json.loads(str(data.get('layout','[]')))
            if not isinstance(order,list) or len(order)>32 or any(not isinstance(x,str) or not re.fullmatch('[0-9a-f]{12}',x) for x in order) or len(set(order))!=len(order): raise ValueError('Invalid panel order.')
            profile=self.service.store.profile(gid,session['user_id']); profile['dashboard_layout']=order; self.service.store.save_profile(gid,session['user_id'],profile)
        except (ValueError,KeyError) as error: raise web.HTTPBadRequest(text=str(error))
        return self.done(gid)
    async def welcome_editor(self,request):
        data,session,gid,guild=await self.form(request)
        try:
            layout=DEFAULT_LAYOUT if data.get('action')=='reset' else json.loads(str(data.get('document','')))
            validate_layout(layout)
            if data.get('action')=='preview': return web.Response(body=render_layout(layout,'Sample member',self.service.bot.get_guild(gid).name,'Welcome to our community!',brand=self.service.store.option(gid,'branding',{}).get('name','Vivi')),content_type='image/png')
            self.service.store.set_option(gid,'welcome_layout',layout)
        except (ValueError,TypeError) as error: raise web.HTTPBadRequest(text=str(error))
        return self.done(gid)
    async def announcement_editor(self,request):
        data,session,gid,guild=await self.form(request)
        try: blocks=validate_announcement(json.loads(str(data.get('document',''))))
        except (ValueError,TypeError) as error: raise web.HTTPBadRequest(text=str(error))
        action=data.get('action')
        if action=='preview': return self.page('<h2>Announcement preview</h2>'+''.join('<p>'+html.escape(b.get('name',''))+' '+html.escape(b.get('value','──────────'))+'</p>' for b in blocks)+f'<a href="/dashboard?guild={gid}">Back</a>')
        if action=='publish':
            if data.get('confirm')!='yes': raise web.HTTPBadRequest(text='Confirm publication before publishing.')
            try: channel=self.service.bot.get_guild(gid).get_channel(int(data.get('channel',0)))
            except ValueError: raise web.HTTPBadRequest(text='Invalid channel.')
            if not isinstance(channel,discord.TextChannel): raise web.HTTPBadRequest(text='Choose a text channel in this server.')
            member=await channel.guild.fetch_member(session['user_id'])
            if not member.guild_permissions.administrator or not channel.permissions_for(channel.guild.me).send_messages or not channel.permissions_for(channel.guild.me).embed_links: raise web.HTTPForbidden(text='Current administrator, Send Messages and Embed Links permissions are required.')
            try: await channel.send(embed=announcement_embed(blocks),allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException: raise web.HTTPBadGateway(text='Discord refused the announcement. Check channel permissions.')
        elif action!='draft': raise web.HTTPBadRequest(text='Unknown announcement action.')
        profile=self.service.store.profile(gid,session['user_id']); profile['announcement_draft']=blocks; self.service.store.save_profile(gid,session['user_id'],profile)
        return self.done(gid)
    async def accessibility_audit(self,request):
        data,session,gid,guild=await self.form(request)
        response=self.page(self.settings_forms(gid,session)); issues=audit_html(response.text)
        return self.page('<h2>Static accessibility findings</h2><p>Automated checks cannot confirm screen-reader compatibility. Test keyboard navigation, focus, contrast and spoken announcements manually.</p><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in issues)+('</ul><p>No static issues found.</p>' if not issues else '</ul>')+f'<p><a href="/dashboard?guild={gid}">Back</a></p>')
    async def release_check(self,request):
        data,session,gid,guild=await self.form(request)
        try: result=await check_updates(self.service)
        except Exception: raise web.HTTPBadGateway(text='Release service unavailable; check network access and host configuration.')
        return self.page('<p>'+html.escape(result)+f'</p><a href="/dashboard?guild={gid}">Back</a>')
