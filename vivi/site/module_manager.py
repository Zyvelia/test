"""Authenticated website module catalog backed by the bot's shared feature switches."""
from aiohttp import web
from vivi.core.features import FEATURES,enabled
from vivi.site.website import esc,icon

GROUPS={
 'Protection':{'global_bans','scam_images','automod','moderation','raid_protection','mention_protection','warning_thresholds','staff_reviews','appeals','reports'},
 'Community':{'polls','giveaways','suggestions','welcome','welcome_cards','goodbye','autorole','rules','roles','birthdays','spotlight','daily_questions','afk','timezone_directory'},
 'Games & profiles':{'games','xp','economy','profiles','competitions','teams','library','lfg'},
 'Support':{'tickets','ticket_tools'},
 'Voice & alerts':{'music','voice_rooms','notifications','instant_webhooks'},
 'Tools':{'ai','translation','reminders','scheduled_backups','custom_aliases','invite_tracking'}}
DESCRIPTIONS={
 'global_bans':'Opt in to the configured operator’s global blocklist and enforce active entries.',
 'polls':'Run timed button polls with optional anonymous voting.',
 'giveaways':'Run giveaways with eligibility rules and recorded rerolls.',
 'suggestions':'Collect member suggestions and votes with staff decisions.',
 'scam_images':'Delete member attachments matching administrator-supplied scam-image references.',
 'automod':'Filter spam, blocked words and suspicious links using your server rules.',
 'moderation':'Enable moderation actions and case records for your staff team.',
 'raid_protection':'Detect join surges and apply your configured raid response.',
 'mention_protection':'Limit excessive member, role and everyone mentions.',
 'warning_thresholds':'Apply configured consequences when warning thresholds are reached.',
 'staff_reviews':'Collect independent staff-conduct and blocklist appeal reviews.',
 'appeals':'Let members privately appeal their own moderation cases.',
 'reports':'Let members privately report concerns to the moderation team.',
 'welcome':'Greet new members in the configured welcome channel.',
 'welcome_cards':'Include illustrated member cards in welcome messages.',
 'goodbye':'Post departure messages in your chosen channel.',
 'autorole':'Assign a configured safe role to new members.',
 'rules':'Offer a persistent rules acceptance button with an optional safe role.',
 'roles':'Allow supported self-assignable role buttons and dropdowns.',
 'birthdays':'Announce birthdays for members who opt in.',
 'spotlight':'Celebrate members who consent to community spotlights.',
 'daily_questions':'Post scheduled questions in your chosen channel.',
 'afk':'Let members set an AFK status with controlled mention replies.',
 'timezone_directory':'Share local times for members who explicitly opt in.',
 'games':'Enable the arcade, card opponents, generated puzzles and persistent idle worlds.',
 'xp':'Award activity XP with cooldowns and optional per-channel rules.',
 'economy':'Enable fictional coins, achievements and cosmetic shop features.',
 'profiles':'Enable custom profile cards and the live appearance editor.',
 'competitions':'Manage tournament brackets, matches and recorded results.',
 'teams':'Maintain rosters, recruitment posts and team membership.',
 'library':'Organize community builds and strategy guides.',
 'lfg':'Publish expiring looking-for-group boards with join controls.',
 'tickets':'Let members open private support channels.',
 'ticket_tools':'Add ticket claiming, priorities, category controls and feedback.',
 'music':'Play supported uploaded audio with voice queue controls.',
 'voice_rooms':'Create and manage temporary member voice rooms.',
 'notifications':'Post configured Twitch, YouTube, GitHub and Steam updates.',
 'instant_webhooks':'Accept signed incoming events through the host-configured webhook listener.',
 'ai':'Offer optional AI assistance in approved channels using the host’s provider.',
 'translation':'Translate text on request through a configured provider.',
 'reminders':'Let members create personal reminders delivered by Vivi.',
 'scheduled_backups':'Create scheduled configuration backups using your retention settings.',
 'custom_aliases':'Register configured informational slash-command shortcuts.',
 'invite_tracking':'Estimate which invite brought a member into the server.'}
FAMILIES={
 'welcome':('Welcome & joining',['welcome','welcome_cards','goodbye','autorole','rules','roles','invite_tracking'],'Messages, welcome cards, newcomer roles and rules in one place.'),
 'moderation':('Moderation & safety',['moderation','automod','raid_protection','mention_protection','warning_thresholds','scam_images','reports','appeals','staff_reviews','global_bans'],'Moderation, automatic protection and staff review tools.'),
 'tickets':('Tickets & support',['tickets','ticket_tools'],'Ticket channels, staff tools, priorities and feedback.'),
 'profiles':('Levels & profiles',['xp','economy','profiles'],'XP, fictional currency and member appearance.'),
 'games':('Games & events',['games','competitions','polls','giveaways'],'Games, tournaments, polls and giveaways.'),
 'community':('Community activities',['suggestions','birthdays','spotlight','daily_questions','afk','timezone_directory','reminders'],'Member activities, celebrations and personal utilities.'),
 'teams':('Teams & gaming groups',['teams','lfg','library'],'Rosters, recruitment, looking-for-group boards and guides.'),
 'voice':('Music & voice',['music','voice_rooms'],'Music queues and temporary voice rooms.'),
 'notifications':('Notifications',['notifications','instant_webhooks'],'Subscriptions, filters and webhook delivery.'),
 'assistance':('AI & translation',['ai','translation'],'Optional assistance, approved channels and usage limits.'),
 'server':('Server tools',['scheduled_backups','custom_aliases'],'Backups and custom command shortcuts.')}

def family_for(key):return next((ident for ident,(_,keys,_) in FAMILIES.items() if key in keys),'server')
def family_navigation(gid,current=None):
    return ''.join('<details'+(' open' if current==ident else '')+f'><summary>{esc(label)}</summary>'+''.join(f'<a href="/configure?guild={gid}&module={key}">{esc(title(key))}</a>' for key in keys)+'</details>' for ident,(label,keys,_) in FAMILIES.items())

COMMAND_TERMS={'global_bans':'globalban','competitions':'competition','profiles':'profile','roles':'role','polls':'poll','giveaways':'giveaway','suggestions':'suggest','birthdays':'birthday','timezone_directory':'timezone','reminders':'remind','invite_tracking':'invite','translation':'translate'}
HINTS={
 'global_bans':'Only the server owner can enable this. Existing entries may be banned; Ban Members is required. Disabling does not undo existing bans.',
 'games':'Arcade: /games · Cards: /cards · Puzzles: /puzzles · Idle worlds: /idle.',
 'scam_images':'Add reference images in /settings → Setup & backups. Exact matching is the default.',
 'welcome':'Customize the channel, text, saved embed and welcome card in Configure.',
 'welcome_cards':'Also enable Welcome and choose a welcome channel.',
 'goodbye':'Choose a goodbye channel and message.',
 'autorole':'Configure server channels and a safe role below Vivi.',
 'rules':'Configure rules text and an optional safe acceptance role.',
 'birthdays':'Choose an announcement channel and server timezone.',
 'daily_questions':'Choose a channel, timezone and posting hour.',
 'tickets':'Configure a private support category, staff role and log channel.',
 'ticket_tools':'Also enable Tickets and configure its support channels.',
 'voice_rooms':'Choose a voice lobby and a category for temporary rooms.',
 'music':'The host needs working voice dependencies and FFmpeg.',
 'notifications':'Add subscriptions and destination channels in notification settings.',
 'instant_webhooks':'The host must configure the signed webhook listener and HTTPS endpoint.',
 'ai':'The host must configure a provider. Add approved channels and usage limits.',
 'translation':'The host must configure a translation provider.',
 'scheduled_backups':'Choose a backup interval and retention count.',
 'custom_aliases':'Add shortcut names and their supported targets.',
 'raid_protection':'Choose a join threshold, response and alert channel.'}
CONFIGURABLE={'scam_images','automod','moderation','raid_protection','mention_protection','warning_thresholds','staff_reviews','welcome','welcome_cards','goodbye','autorole','rules','birthdays','daily_questions','lfg','tickets','ticket_tools','voice_rooms','notifications','instant_webhooks','ai','scheduled_backups','custom_aliases','xp'}

def group_for(key):return next((name for name,keys in GROUPS.items() if key in keys),'Tools')
def module_enabled(dashboard,gid,key):
    return dashboard.service.global_bans.participating(dashboard.service.bot.get_guild(gid)) if key=='global_bans' else enabled(dashboard.service.store,gid,key)

def title(key):return {'ai':'AI assistance','xp':'XP levels','afk':'AFK status','lfg':'Looking for group','automod':'Automatic moderation'}.get(key,key.replace('_',' ').title())

class ModuleManager:
    async def module_state(self,request):
        try:gid=int(request.query.get('guild',''))
        except ValueError:raise web.HTTPBadRequest(text='Invalid server ID.')
        await self.authorize(request,gid)
        return web.json_response({'features':{key:module_enabled(self,gid,key) for key in FEATURES if key!='faq'},'revision':self.config_revision(gid)})

    async def modules(self,request):
        if not request.cookies.get('vivi_session'):
            return self.site_shell('<div class="container"><section class="error-card"><h1>Your server. Your features.</h1><p>Sign in with Discord to choose a server and manage Vivi’s modules.</p><a class="btn btn-primary" href="/login?next=modules">Sign in with Discord</a></section></div>','Manage features','features')
        if not request.query.get('guild'):return await self.index(request)
        try:gid=int(request.query['guild'])
        except ValueError:raise web.HTTPBadRequest(text='Invalid server ID.')
        session=await self.authorize(request,gid);guild=self.service.bot.get_guild(gid)
        query=request.query.get('search','')[:100];group=request.query.get('category','all');state=request.query.get('state','all')
        if group not in GROUPS:group='all'
        if state not in {'enabled','disabled'}:state='all'
        cards=[];card_keys=[];count=0;total=0
        for key in sorted(FEATURES,key=lambda key:(list(GROUPS).index(group_for(key)),title(key))):
            if key=='faq':continue  # Retained legacy data has no active FAQ command module.
            total+=1;on=module_enabled(self,gid,key);category=group_for(key);description=DESCRIPTIONS.get(key,'Enable '+title(key)+' for this server.')
            matches=(group=='all' or category==group) and (state=='all' or on==(state=='enabled')) and all(term in (title(key)+' '+description+' '+key+' '+category+' '+FAMILIES[family_for(key)][0]).lower() for term in query.lower().split())
            if matches:count+=1
            symbol='shield' if category=='Protection' else 'game' if category=='Games & profiles' else 'ticket' if category=='Support' else 'bell' if category=='Voice & alerts' else 'users' if category=='Community' else 'settings'
            configure=f'<a class="text-link" href="/configure?guild={gid}&module={key}">Configure →</a>'
            consent='';owner_disabled=key=='global_bans' and not on and session.get('user_id')!=getattr(guild,'owner_id',None)
            if key=='global_bans':
                from vivi.server.global_bans import operator_id
                consent=f'<label class="global-consent" data-global-consent'+(' hidden' if on else '')+f'><input type="checkbox" name="global_consent" value="true"'+(' required' if not on else '')+(' disabled' if owner_disabled else '')+f'> I am the server owner and accept enforcement of existing and future entries controlled by user {operator_id()}.</label>'
            card_keys.append(key)
            cards.append(f'<article class="feature-module" id="module-{key}" data-feature-module="{key}" data-group="{esc(category)}" data-enabled="{str(on).lower()}" data-owner-can-enable="{str(session.get('user_id')==getattr(guild,'owner_id',None)).lower()}"'+(' hidden' if not matches else '')+f'><div class="module-heading"><span class="module-symbol">{icon(symbol)}</span><span class="module-state" data-module-state>{"Enabled" if on else "Disabled"}</span></div><span class="tag">{esc(category)}</span><h3>{esc(title(key))}</h3><p class="module-description">{esc(description)}</p><p class="module-hint">{esc(HINTS.get(key,""))}</p><div class="module-bottom">{configure}<form action="/feature" method="post" data-module-toggle>'+self.hidden(session,gid)+f'<input type="hidden" name="feature" value="{key}"><input type="hidden" name="enabled" value="{str(not on).lower()}"><input type="hidden" name="return" value="modules">{consent}<button type="submit"'+(' disabled title="Only the server owner can opt in"' if owner_disabled else '')+f' role="switch" aria-checked="{str(on).lower()}" aria-label="Toggle {esc(title(key))}">{"Disable" if on else "Enable"}</button></form></div><span class="module-save" role="status" aria-live="polite"></span></article>')
        sections=[]
        for ident,(label,keys,description) in FAMILIES.items():
            children=''.join(card for key,card in zip(card_keys,cards) if key in keys)
            visible=any((group=='all' or group_for(key)==group) and (state=='all' or module_enabled(self,gid,key)==(state=='enabled')) and all(term in (title(key)+' '+DESCRIPTIONS.get(key,'')+' '+key+' '+group_for(key)+' '+label).lower() for term in query.lower().split()) for key in keys)
            active=sum(module_enabled(self,gid,key) for key in keys)
            sections.append(f'<details class="module-family" data-module-family="{ident}"'+(' hidden' if not visible else '')+(' open' if visible and (query or group!='all' or state!='all') else '')+f'><summary><span><strong>{esc(label)}</strong><small>{esc(description)}</small></span><span class="family-count">{active} of {len(keys)} enabled</span></summary><div class="family-children">'+children+'</div></details>')
        options='<option value="all">All categories</option>'+''.join(f'<option value="{esc(name)}"'+(' selected' if name==group else '')+f'>{esc(name)}</option>' for name in GROUPS)
        states=''.join(f'<option value="{value}"'+(' selected' if value==state else '')+f'>{label}</option>' for value,label in [('all','All modules'),('enabled','Enabled'),('disabled','Disabled')])
        content=f'<div data-module-manager data-guild="{gid}"><div class="modules-intro"><div><span class="eyebrow">Your server modules</span><h2>{esc(guild.name)}</h2><p>Open a section to customize related features together. Changes are shared with Discord.</p></div><a class="btn btn-ghost" href="/dashboard?guild={gid}">Server tools →</a></div><form action="/modules" method="get" class="module-filters" id="module-filters"><input type="hidden" name="guild" value="{gid}"><label>Find a module<input type="search" name="search" maxlength="100" value="{esc(query)}" placeholder="Welcome, moderation, games…"></label><label>Category<select name="category">{options}</select></label><label>Status<select name="state">{states}</select></label><button class="btn" type="submit">Filter</button></form><p id="module-manager-status" role="status" aria-live="polite"></p><p class="module-count" role="status" id="module-count">{count} of {total} modules</p><p class="module-manager-note">Enable switches control availability. Modules with setup notes also need their channels, roles or host providers configured.</p><div class="module-families">'+''.join(sections)+'</div><p id="module-empty"'+(' hidden' if count else '')+'>No modules match these filters.</p></div>'
        response=self.page(content)
        response.text=response.text.replace('<nav data-dashboard-sections aria-label="Server modules"></nav>','<nav data-dashboard-sections aria-label="Server modules">'+family_navigation(gid)+'</nav>')
        return response
