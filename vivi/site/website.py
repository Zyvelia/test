"""Vivi's public site and the shared, authenticated dashboard shell."""
from contextvars import ContextVar
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode
from aiohttp import web
from discord import app_commands
from vivi import __version__
from vivi.site.policies import PRIVACY,TERMS,policy_html,contact_html

WEB_SESSION=ContextVar('website_session',default=None)

ROOT=Path(__file__).resolve().parents[2]
WEB=Path(__file__).parent/'web'
DEFAULT_APPLICATION_ID='1568121020047429775'
INVITE_PERMISSIONS='1374678019126'
AVATARS={'neon-headset':'02-neon-headset.png','neon-bob':'03-neon-bob.png','silver-crown':'04-silver-crown.png','velvet-moth':'01-velvet-moth.png'}
REMOVED_COMMANDS={'admin faq_add','admin faq_remove','community faq'}
GITHUB='https://github.com/Zyvelia/test'
ICONS={
 'arrow':'M5 12h14m-5-5 5 5-5 5','shield':'M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z M8 12l3 3 5-6',
 'spark':'m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z',
 'users':'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
 'game':'M6 7h12l3 11c.5 2-2 3-3 1l-2-3H8l-2 3c-1 2-3.5 1-3-1z M7 10v5 M4.5 12.5h5 M16 11h.1 M18 14h.1',
 'ticket':'M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4z M15 6v3m0 3v2m0 2v2',
 'bell':'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4',
 'palette':'M12 3a9 9 0 1 0 0 18h1c2 0 3-2 1.5-3.5-1-1 .5-2.5 2-2.5H18c5 0 4-12-6-12 M7 10h.1 M10 6h.1 M15 6h.1 M18 10h.1',
 'voice':'M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3 M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8',
 'settings':'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3m0 14v3M2 12h3m14 0h3 M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2'}


def icon(name):return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{ICONS[name]}"/></svg>'
def esc(value):return html.escape(str(value),quote=True)


def server_avatar(guild_id,name,icon=None):
    initials=''.join(word[0] for word in str(name).split()[:2]) or 'S'
    valid=re.fullmatch(r'[0-9]{1,20}',str(guild_id)) and re.fullmatch(r'(?:a_)?[a-fA-F0-9]{32}',str(icon or ''))
    if not valid:return '<div class="server-avatar">'+esc(initials)+'</div>'
    extension='gif' if str(icon).startswith('a_') else 'png'
    url=f'https://cdn.discordapp.com/icons/{guild_id}/{icon}.{extension}?size=128'
    return f'<div class="server-avatar"><img data-server-icon src="{esc(url)}" alt="{esc(name)} server icon" width="52" height="52" loading="lazy" referrerpolicy="no-referrer"><span class="server-avatar-fallback" hidden aria-hidden="true">{esc(initials)}</span></div>'


def asset_stamp(filename):
    try:return str((WEB/filename).stat().st_mtime_ns)
    except OSError:return '1'


def command_catalog(bot):
    rows=[]
    for command in bot.tree.walk_commands():
        if not isinstance(command,app_commands.Command) or command.qualified_name in REMOVED_COMMANDS:continue
        root=command.qualified_name.split()[0];category=root if command.parent or root in getattr(bot,'menu_groups',{}) or root=='settings' else 'basics'
        rows.append(dict(name='/'+command.qualified_name,description=command.description,category=category,parameters=[dict(name=p.name,required=p.required,description=p.description) for p in command.parameters]))
    return sorted(rows,key=lambda row:(row['category'],row['name']))

FEATURE_CARDS=[
 ('shield','Moderation','Keep your space yours.','Warnings, timed bans, case evidence and independent staff reviews. Give your moderation team context, not more busywork.','mod','Warnings,Private reports,Case history'),
 ('users','Community','A better first hello.','Personal welcome cards, safe self-assignable roles and rules acceptance help new members feel at home.','community','Welcome cards,Role menus,Polls'),
 ('game','Arcade','One more game?','Illustrated chess, Connect Four, Battleship and puzzle games. Play in Discord with private boards and clear controls.','games','Multiplayer,Puzzles,Three themes'),
 ('ticket','Support','Every conversation matters.','Private support tickets, staff claims, priorities and activity timelines keep conversations moving.','ticket','Private tickets,Staff tools,Feedback'),
 ('palette','Profiles','A little more you.','Personal backgrounds, gradients, stickers and cosmetic loadouts, with control over what your profile shares.','profile','Custom cards,Privacy controls,Free cosmetics'),
 ('bell','Notifications','Keep everyone in the loop.','Follow Twitch streams, YouTube uploads, GitHub updates and Steam game news in the channels you choose.','notify','Stream alerts,Game news,Webhooks'),
 ('voice','Voice','Make room for your people.','Temporary voice rooms and uploaded-audio playback, with room controls and queues for your community.','music','Temporary rooms,Audio queues,Room limits'),
 ('settings','Your server','Set it up your way.','Enable the features you need. Manage server settings through Discord or the permission-checked web dashboard.','admin','Feature switches,Backups,Optional AI')]

class Website:
    def website_routes(self):
        return [web.get('/features',self.site_features),web.get('/commands',self.site_commands),web.get('/support',self.site_support),web.get('/privacy',self.site_privacy),web.get('/terms',self.site_terms),web.get('/invite',self.site_invite),web.get('/api/commands',self.site_command_api),web.get('/api/status',self.site_status),web.get('/assets/{filename}',self.site_asset),web.get('/favicon.svg',self.site_asset)]
    def website_application_id(self):
        value=self.client or str(getattr(self.service.bot,'application_id',None) or DEFAULT_APPLICATION_ID)
        if not re.fullmatch(r'[0-9]{1,20}',value) or not 0<int(value)<2**64:raise ValueError('DISCORD_CLIENT_ID must be a Discord application ID.')
        return value
    def site_shell(self,content,title='Your community, your way',active='',dashboard=False,branding=None,extra_style=''):
        branding=branding or {};name=branding.get('name','Vivi') if dashboard else 'Vivi'
        links=''.join(f'<a href="/{path}"'+(' aria-current="page"' if active==path else '')+f'>{label}</a>' for path,label in [('features','Features'),('commands','Commands'),('support','Support')])
        brand=f'<a class="brand" href="/" aria-label="Vivi home"><svg viewBox="0 0 30 38" fill="none" aria-hidden="true"><path d="M3 3 15 34 27 3M10 3l5 14 5-14" stroke="currentColor" stroke-width="3.4" stroke-linejoin="round"/></svg>{esc(name)}<span class="brand-dot">.</span></a>'
        session=WEB_SESSION.get()
        account='<a class="nav-login" href="/login">Sign in with Discord</a>'
        if session:
            profile=session.get('profile',{});display=profile.get('global_name') or profile.get('username') or 'Discord member'
            uid=str(session.get('user_id',''));avatar=profile.get('avatar','')
            picture=f'<span class="account-avatar">{esc(display[:1].upper())}</span>'
            if re.fullmatch(r'[0-9]{1,20}',uid) and re.fullmatch(r'(?:a_)?[a-f0-9]{32}',avatar):
                picture=f'<img class="account-avatar" src="https://cdn.discordapp.com/avatars/{uid}/{avatar}.png?size=64" alt="">'
            account=f'<details class="account-menu"><summary>{picture}<span>{esc(display)}</span></summary><div class="account-popover"><strong>Signed in with Discord</strong><a href="/dashboard">Your servers</a><form action="/logout" method="post"><input type="hidden" name="csrf" value="{esc(session["csrf"])}"><button>Sign out</button></form></div></details>'
        header=f'<a class="skip-link" href="#main-content">Skip to content</a><header class="site-header"><div class="container nav-wrap">{brand}<nav class="nav-links" id="site-navigation" aria-label="Main navigation">{links}<a href="/dashboard">Dashboard</a></nav><div class="nav-actions">{account}<a class="btn btn-primary" href="/invite">Add to Discord {icon("arrow")}</a><button class="menu-toggle" id="menu-toggle" aria-expanded="false" aria-controls="site-navigation" aria-label="Open navigation">☰</button></div></div></header>'
        footer=f'<footer class="site-footer"><div class="container"><div class="footer-top"><div>{brand}<p class="footer-tagline">A little structure. A lot of personality.</p></div><nav class="footer-links" aria-label="Footer"><a href="/commands">Commands</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="{GITHUB}">GitHub</a></nav></div><div class="footer-bottom"><span>Vivi · Community tools, made personal. Not affiliated with Discord.</span><span class="small-status"><i class="status-dot" data-site-dot></i><span data-site-status>Checking Vivi’s bot connection…</span></span></div></div></footer>'
        if dashboard:
            content='<div class="container dashboard-layout"><aside class="dashboard-rail"><div class="rail-label">Your workspace</div><a href="/dashboard">Your servers</a><a href="/modules">Manage features</a><a href="/embeds">Embed writer</a><a href="/staff">Staff workspace</a><a href="/commands">Command directory</a><a href="/support">Help & setup</a><div class="rail-label">Server modules</div><nav data-dashboard-sections aria-label="Server modules"></nav></aside><div class="dashboard-content"><div id="studio-status" role="status" aria-live="polite"></div><h1>'+esc(name)+' · Server Dashboard</h1><p>'+esc(branding.get('tagline','Your server, your settings.'))+'</p>'+content+'</div></div>'
        scripts='<script src="/assets/site.js" defer></script>'+('<script src="/assets/studio.js" defer></script>' if dashboard else '')
        style='<style>'+extra_style+'</style>' if extra_style else ''
        return web.Response(content_type='text/html',text='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0d0b12"><meta name="description" content="Vivi brings moderation, community tools, games and customizable profiles to your Discord server."><title>'+esc(title)+' · Vivi</title><link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/site.css?v='+asset_stamp("site.css")+'">'+style+scripts+'</head><body>'+header+'<main id="main-content">'+content+'</main>'+footer+'</body></html>')
    def site_heading(self,kicker,title,description):return f'<div class="page-heading"><div class="eyebrow">{esc(kicker)}</div><h1>{title}</h1><p>{esc(description)}</p></div>'
    def feature_cards(self,all=False):
        cards=FEATURE_CARDS if all else FEATURE_CARDS[:3]
        return ''.join(f'<article class="feature-card"><div class="feature-icon">{icon(symbol)}</div><span class="tag">{esc(category)}</span><h3>{esc(title)}</h3><p>{esc(description)}</p><a class="text-link" href="/commands?category={group}">Explore {esc(category.lower())} →</a>'+('<div class="feature-chips">'+''.join(f'<span>{esc(item)}</span>' for item in chips.split(','))+'</div>' if all else '')+'</article>' for symbol,category,title,description,group,chips in cards)
    async def site_home(self,request):
        if request.query.get('guild'):
            ident=request.query['guild']
            if not re.fullmatch(r'[0-9]{1,20}',ident):raise web.HTTPBadRequest(text='Invalid server ID.')
            raise web.HTTPFound('/dashboard?'+urlencode({'guild':ident}))
        body=f'''<section class="hero"><div class="container hero-grid"><div><div class="eyebrow">Your server. A little more you.</div><h1>Less chaos.<br>More <span class="serif">community.</span></h1><p class="hero-copy">Meet Vivi. Your server’s new favorite companion for keeping things welcoming, organized, and a lot more fun. All the useful tools. Your own kind of personality.</p><div class="hero-buttons"><a class="btn btn-primary" href="/invite">Add Vivi to Discord {icon('arrow')}</a><a class="btn btn-ghost" href="/features">Find your features</a></div><p class="hero-note"><span>No premium subscription.</span> Optional features. Your rules.</p></div><div class="portrait-wrap"><div class="art-corner">HELLO, I’M VIVI</div><div class="portrait-frame"><img class="portrait" src="/assets/vivi-avatar.png" alt="Vivi, a short-haired cyber-gothic assistant surrounded by pink neon" width="495" height="495"><div class="portrait-gradient"></div><div class="portrait-label"><div><strong>Your people.<br>Your place.</strong><small>I’ll help with the rest.</small></div><span class="portrait-icon">{icon('spark')}</span></div></div><div class="floating-card">{icon('shield')}<div><b>Good vibes. Clear boundaries.</b><small>Built for the community you’re making.</small></div></div></div></div></section>
<div class="container principles"><div>{icon('settings')}<div><strong>Your server, your switches</strong><p>Turn on what matters. Leave the rest off.</p></div></div><div>{icon('shield')}<div><strong>Privacy is part of the picture</strong><p>Private reports. Opt-ins. Profile controls.</p></div></div><div>{icon('spark')}<div><strong>More than moderation</strong><p>Profiles, game nights, and familiar faces.</p></div></div></div>
<section class="container section"><div class="section-heading"><div><div class="eyebrow">A place worth coming back to</div><h2>Useful tools.<br><span class="serif">Actual personality.</span></h2><p class="section-intro">From the first hello to the late-night game, make your server feel like yours.</p></div><a class="text-link" href="/features">See everything Vivi can do ↗</a></div><div class="feature-grid">{self.feature_cards()}</div></section>
<section class="container arcade-section"><div class="arcade-art"><img src="/assets/arcade-preview.png" alt="Examples of Vivi’s illustrated chess, Connect Four and puzzle boards" loading="lazy" width="960" height="1204"><span class="arcade-label">Vivi Arcade / real game previews</span></div><div class="arcade-copy"><div class="eyebrow">Stay for one more round</div><h2>Your next game night<br>is <span class="serif">already here.</span></h2><p>Challenge a friend, solve a puzzle, or host an anagram tournament. Illustrated boards and private controls keep the game right where your people are: in Discord.</p><div class="game-tags"><a href="/commands?search=chess">Chess</a><a href="/commands?search=connect_four">Connect Four</a><a href="/commands?search=battleship">Battleship</a><a href="/commands?search=minesweeper">Minesweeper</a></div><a class="text-link" href="/commands?category=games">Explore the arcade →</a></div></section>
<section class="cta-wrap"><div class="eyebrow" style="justify-content:center">Make yourself at home</div><h2>A better server starts with <span class="serif">your people.</span></h2><p>Vivi helps you take care of the rest.</p><a class="btn btn-primary" href="/invite">Let’s meet your server {icon('arrow')}</a></section>'''
        return self.site_shell(body)
    async def site_features(self,request):
        body='<div class="container">'+self.site_heading('Made to fit your server','Your tools. <span class="serif">Your atmosphere.</span>','Choose the features that fit your community. Administrators control which optional modules are enabled.')+'<div class="feature-grid feature-page-grid">'+self.feature_cards(True)+'</div><div class="help-callout"><h2>Set up in Discord. Fine-tune on the web.</h2><p>Start with /setup, then choose your modules in the dashboard. Optional AI, translation and voice features may need host configuration.</p></div></div>'
        body=body.replace('<div class="feature-grid feature-page-grid">','<p><a class="btn btn-primary" href="/modules">Manage your server’s features →</a></p><div class="feature-grid feature-page-grid">',1)
        return self.site_shell(body,'Features','features')
    def command_cards(self,rows):
        return ''.join(f'<article class="command-card"><header><code>{esc(row["name"])}</code><button class="copy-button" type="button" data-copy="{esc(row["name"])}" aria-label="Copy {esc(row["name"])}">Copy</button></header><p>{esc(row["description"])}</p></article>' for row in rows) or '<p class="empty-state">No matching commands. Try another search or category.</p>'
    async def site_commands(self,request):
        catalog=command_catalog(self.service.bot);query=request.query.get('search','')[:100];category=request.query.get('category','all')[:32]
        groups=sorted({row['category'] for row in catalog})
        if category not in ['all']+groups:category='all'
        rows=[r for r in catalog if (category=='all' or r['category']==category) and all(term in (r['name']+' '+r['description']).lower() for term in query.lower().split())]
        options='<option value="all">All categories</option>'+''.join(f'<option value="{esc(group)}"'+(' selected' if group==category else '')+f'>{esc(group.title())}</option>' for group in groups)
        body='<div class="container">'+self.site_heading('The command directory','A little help.<br><span class="serif">Right at your fingertips.</span>','Search Vivi’s built-in commands. Availability depends on server feature switches and your Discord permissions.')+f'<form class="command-tools" id="command-search-form" action="/commands" method="get"><div><label for="command-search">Find a command</label><input id="command-search" name="search" type="search" placeholder="Try moderation, chess, or profile…" maxlength="100" value="{esc(query)}"></div><div><label for="command-category">Category</label><select id="command-category" name="category">{options}</select></div><button class="btn btn-primary">Search commands</button></form><div class="command-meta"><span id="command-count" role="status" aria-live="polite">{len(rows)} of {len(catalog)} commands</span><span>Use the same slash commands in Discord.</span></div><div class="command-grid" id="command-results">'+self.command_cards(rows)+'</div></div>'
        return self.site_shell(body,'Commands','commands')
    async def site_support(self,request):
        body='<div class="container">'+self.site_heading('A good place to start','Let’s get you <span class="serif">settled in.</span>','Add Vivi, choose a few features, and make the server your own. You can do the essentials in Discord or sign in to the dashboard.')+f'<div class="guide-grid"><article class="guide-card"><div class="step-number">01</div><h2>Invite Vivi</h2><p>Choose a server you manage and authorize the permissions for the features you want.</p><a class="text-link" href="/invite">Add to Discord →</a></article><article class="guide-card"><div class="step-number">02</div><h2>Make a first home</h2><p>Use <code>/setup</code> to choose your welcome channel, support category and private staff logs.</p><a class="text-link" href="/commands?search=setup">Find setup commands →</a></article><article class="guide-card"><div class="step-number">03</div><h2>Choose your modules</h2><p>Sign in with Discord and manage your server. Or use <code>/admin feature</code> to enable a module.</p><a class="text-link" href="/dashboard">Open your dashboard →</a></article></div><div class="help-callout"><h2>Need a hand?</h2><p>Ask your server’s staff about local rules or moderation. For Vivi setup and bug reports, use the project guides and issue tracker.</p></div><div class="prose"><h2>For the person hosting Vivi</h2><p>Vivi runs on Windows, Linux or Docker. The bot and its website must be running for dashboard changes to reach the server. Keep your host awake if you want continuous availability.</p><p><a href="{GITHUB}/blob/main/docs/WEBSITE.md">Website & login setup</a> · <a href="{GITHUB}/blob/main/README.md">Bot installation guide</a> · <a href="{GITHUB}/issues">Report a bug</a></p></div>{contact_html()}</div>'
        return self.site_shell(body,'Support','support')
    async def site_privacy(self,request):
        body='<div class="container">'+self.site_heading('Your data matters','Privacy <span class="serif">Policy.</span>','How Vivi handles information, your choices and how to contact its operator.')+policy_html(PRIVACY,'terms','Terms of Service')+'</div>'
        return self.site_shell(body,'Privacy Policy')
    async def site_terms(self,request):
        body='<div class="container">'+self.site_heading('A few shared expectations','Terms of <span class="serif">Service.</span>','Rules for using Vivi, server responsibilities and the limits of the service.')+policy_html(TERMS,'privacy','Privacy Policy')+'</div>'
        return self.site_shell(body,'Terms of Service')
    async def site_invite(self,request):
        params=dict(client_id=self.website_application_id(),permissions=INVITE_PERMISSIONS,scope='bot applications.commands',integration_type='0')
        guild=request.query.get('guild_id')
        if guild:
            if not re.fullmatch(r'[0-9]{1,20}',guild) or not 0<int(guild)<2**64:raise web.HTTPBadRequest(text='Invalid server ID.')
            params['guild_id']=guild
        raise web.HTTPFound('https://discord.com/oauth2/authorize?'+urlencode(params))
    async def site_command_api(self,request):return web.json_response(dict(commands=command_catalog(self.service.bot)))
    async def site_status(self,request):
        ready=getattr(self.service.bot,'is_ready',lambda:False)()
        return web.json_response(dict(online=bool(ready),version=__version__,commands=len(command_catalog(self.service.bot))))
    async def site_asset(self,request):
        filename=request.match_info.get('filename',request.path.rsplit('/',1)[-1])
        avatar=os.getenv('WEBSITE_AVATAR','neon-bob')
        if avatar not in AVATARS:avatar='neon-bob'
        paths={'draft-recovery.js':WEB/'draft-recovery.js','site.css':WEB/'site.css','site.js':WEB/'site.js','message-preview.js':WEB/'message-preview.js','serif.ttf':ROOT/'vivi/assets/fonts/serif.ttf','vivi-avatar.png':ROOT/'assets/vivi/avatars'/AVATARS[avatar],'arcade-preview.png':ROOT/'docs/assets/arcade-preview.png','favicon.svg':WEB/'favicon.svg'}
        path=paths.get(filename)
        if not path or not path.is_file():raise web.HTTPNotFound(text='Asset not found.')
        return web.FileResponse(path,headers={'Cache-Control':'public, max-age=3600'})
