"""Feature policy, backups, local games, and pure formatting helpers."""
import datetime as dt
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit

FEATURES = {
    'scam_images':False,
    'invite_tracking':False,'competitions':False,'teams':False,'library':False,'profiles':False,
    'staff_reviews': False, 'lfg': False, 'timezone_directory': False, 'reminders': False,
    # Retain the stored card preference for compatibility; it is a Welcome option, not a separate module.
    'welcome': True, 'welcome_cards': False, 'goodbye': False, 'autorole': False,
    'rules': False, 'faq': False, 'automod': False, 'moderation': True,
    'appeals': False, 'reports': False, 'roles': True, 'tickets': True,
    'polls': False, 'giveaways': False, 'suggestions': False, 'birthdays': False,
    'spotlight': False, 'games': False, 'daily_questions': False, 'xp': False,
    'economy': False, 'translation': False, 'ai': False,
    'music': False, 'voice_rooms': False, 'notifications': False, 'ticket_tools': False,
    'instant_webhooks': False, 'afk': False, 'scheduled_backups': False, 'custom_aliases': False,
    'raid_protection': False, 'mention_protection': False, 'warning_thresholds': False, 'global_bans':False,
}
OPTION_TYPES = {
    'welcome_appearance':dict,'goodbye_appearance':dict,
    'scam_image_distance':int,
    'welcome_channel':int, 'welcome_mode':str, 'goodbye_mode':str, 'welcome_embed':dict, 'goodbye_embed':dict,
    'welcome_text': str, 'welcome_color': str, 'goodbye_channel': int, 'goodbye_text': str,
    'autorole': int, 'rules_role': int, 'rules_text': str, 'blocked_words': list,
    'blocked_domains': list, 'spam_limit': int, 'dm_explanations': bool,
    'birthday_channel': int, 'daily_channel': int, 'daily_hour': int, 'timezone': str,
    'ai_channels': list, 'ai_limit': int, 'faq': dict,
    'mention_limit': int, 'raid_limit': int, 'raid_window': int, 'raid_action': str,
    'raid_channel': int, 'raid_lock_minutes': int, 'warning_count': int,
    'warning_timeout_minutes': int, 'warning_window_days': int,
    'ticket_categories': dict, 'voice_lobby': int, 'voice_category': int,
    'voice_user_limit': int, 'language': str, 'backup_hours': int, 'backup_keep': int, 'aliases': dict, 'xp_channels': dict, 'branding': dict, 'review_channel': int, 'reviewer_role': int, 'lfg_channel': int, 'lfg_hours': int, 'welcome_layout': dict,
}
TRIVIA = [
    ('Which planet is the largest?', ['Jupiter','Earth','Mars','Venus'],0),
    ('What is the chemical symbol for gold?', ['Ag','Au','Fe','O'],1),
    ('How many sides does a hexagon have?', ['5','8','6','7'],2),
    ('Which ocean is the largest?', ['Atlantic','Indian','Arctic','Pacific'],3),
    ('Which language runs natively in web browsers?', ['JavaScript','Python','Rust','C'],0),
    ('What does CPU stand for?', ['Central Processing Unit','Computer Power Utility','Core Program User','Control Panel Unit'],0),
    ('What is 12 squared?', ['124','144','24','164'],1),
    ('Which animal is a mammal?', ['Shark','Trout','Dolphin','Octopus'],2),
    ('What is the smallest prime number?', ['0','1','2','3'],2),
    ('Which gas do plants absorb for photosynthesis?', ['Oxygen','Helium','Nitrogen','Carbon dioxide'],3),
    ('Which instrument has keys, pedals, and strings?', ['Piano','Flute','Drum','Trumpet'],0),
    ('What is the freezing point of water in Celsius?', ['100','32','0','-10'],2),
]
QUESTIONS = [
    'What game could you play forever?', 'What skill would you like to learn?',
    'What is your favorite soundtrack?', 'What made you smile this week?',
    'What fictional world would you visit?', 'What is your favorite comfort food?',
    'What is a hobby you would recommend?', 'Which movie deserves a sequel?',
    'What is your ideal weekend?', 'What is a small achievement you are proud of?',
    'What game should our community try next?', 'What is a useful tip you learned recently?',
    'What would you build with unlimited time?', 'What is your favorite season?',
    'What is your favorite cooperative game?', 'What book or show would you recommend?',
    'What is your dream travel destination?', 'What would your superpower be?',
    'What is your favorite thing about this community?', 'What are you looking forward to?',
]
WORDS = ['planet','silver','garden','rocket','puzzle','forest','castle','window','dragon','orange']
SHOP = {'starlight': (100,'✨ Starlight',0xFFD166), 'ocean': (150,'🌊 Ocean',0x57C7FF),
        'royal': (200,'👑 Royal',0xB980FF), 'neon': (250,'⚡ Neon',0x50FA7B)}

def enabled(store, guild, name):
    return store.option(guild, 'feature:'+name, FEATURES.get(name,False))

def validate_option(key, value):
    if key.startswith('feature:'):
        if key[8:] not in FEATURES or type(value) is not bool: raise ValueError('Unknown feature or invalid switch.')
        return
    if key not in OPTION_TYPES or type(value) is not OPTION_TYPES[key]: raise ValueError('Unknown setting or invalid type.')
    if isinstance(value,str) and len(value)>1800: raise ValueError('Setting is too long.')
    if key in {'welcome_appearance','goodbye_appearance'}:
        from vivi.site.message_templates import validate_appearance
        validate_appearance(value)
    if key in {'welcome_embed','goodbye_embed'}:
        if value:
            from vivi.site.embed_writer import validate
            validate(value)
    if key in {'welcome_mode','goodbye_mode'} and value not in {'text','embed'}:raise ValueError('Choose text or embed.')
    if key=='welcome_channel' and not 0<=value<2**63:raise ValueError('Invalid channel ID.')
    if key=='welcome_layout':
        from vivi.site.studio_layout import validate_layout
        validate_layout(value)
    if key=='lfg_hours' and not 1<=value<=72: raise ValueError('LFG lifetime must be 1–72 hours.')
    if key in {'review_channel','reviewer_role','lfg_channel'} and not 0<=value<2**63: raise ValueError('Invalid Discord ID.')
    if key=='xp_channels':
        from vivi.server.customization import validate_xp
        validate_xp(value)
    if key=='branding':
        from vivi.server.customization import validate_brand
        validate_brand(value)
    if key=='language' and value not in {'en','es','fr'}: raise ValueError('Supported languages: en, es, fr.')
    if key=='aliases':
        from vivi.server.productivity import validate_aliases
        validate_aliases(value)
    if key=='backup_hours' and not 1<=value<=168: raise ValueError('Backup interval must be 1–168 hours.')
    if key=='backup_keep' and not 1<=value<=30: raise ValueError('Backup retention must be 1–30 files.')
    if key=='faq':
        if len(value)>50 or any(not isinstance(q,str) or not isinstance(a,str) or not 1<=len(q)<=150 or not 1<=len(a)<=1200 for q,a in value.items()): raise ValueError('Invalid FAQ backup.')
    limits={'scam_image_distance':(0,4),'mention_limit':(1,100),'raid_limit':(3,100),'raid_window':(10,300),
            'raid_lock_minutes':(1,60),'warning_count':(2,20),'warning_timeout_minutes':(1,40320),
            'warning_window_days':(1,365),'voice_user_limit':(0,99)}
    if key in limits and not limits[key][0]<=value<=limits[key][1]: raise ValueError(f'{key} must be {limits[key][0]}–{limits[key][1]}.')
    if key=='raid_action' and value not in {'alert','lockdown'}: raise ValueError('raid_action must be alert or lockdown.')
    if key in {'raid_channel','voice_lobby','voice_category'} and value<0: raise ValueError('Invalid channel ID.')
    if key=='ticket_categories':
        if len(value)>20 or any(not isinstance(k,str) or not 1<=len(k)<=32 or type(v) is not int or v<=0 for k,v in value.items()): raise ValueError('Use a JSON object mapping up to 20 category labels to Discord category IDs.')
    if isinstance(value,list):
        if len(value)>100: raise ValueError('Too many list items.')
        for item in value:
            if key=='ai_channels':
                if type(item) is not int or item<=0: raise ValueError('Invalid channel ID.')
            elif not isinstance(item,str) or not item or len(item)>100: raise ValueError('Invalid filter entry.')
    if key in {'spam_limit','ai_limit'} and not 1<=value<=100: raise ValueError('Limit must be 1–100.')
    if key=='daily_hour' and not 0<=value<=23: raise ValueError('Hour must be 0–23.')
    if key in {'autorole','rules_role','goodbye_channel','birthday_channel','daily_channel'} and value<0: raise ValueError('Invalid ID.')
    if key=='welcome_color' and not re.fullmatch(r'#[0-9a-fA-F]{6}',value): raise ValueError('Use a hex color such as #87CEEB.')
    if key=='timezone':
        from zoneinfo import ZoneInfo
        ZoneInfo(value)

def validate_backup(guild, backup):
    if not isinstance(backup,dict) or set(backup) not in [{'version','guild','settings','options','roles'},{'version','guild','settings','options','roles','subscriptions'}]: raise ValueError('Invalid backup fields.')
    if backup['version'] not in {1,2} or backup['guild']!=guild: raise ValueError('Backup is for a different server or version.')
    if not isinstance(backup['options'],dict) or len(backup['options'])>100: raise ValueError('Invalid options.')
    for key,value in backup['options'].items(): validate_option(key,value)
    subscriptions=backup.get('subscriptions',[])
    if not isinstance(subscriptions,list) or len(subscriptions)>20: raise ValueError('Invalid subscriptions.')
    from vivi.server.operations import subscription
    for item in subscriptions:
        if not isinstance(item,dict) or set(item) not in [{'provider','source','channel'},{'provider','source','channel','filters'}] or not isinstance(item['provider'],str) or not isinstance(item['source'],str) or type(item['channel']) is not int or item['channel']<=0: raise ValueError('Invalid subscription.')
        subscription(item['provider'],item['source'],item['channel'],item.get('filters'))
    roles=backup['roles']
    if not isinstance(roles,list) or len(roles)>100 or any(type(x) is not int or x<=0 for x in roles): raise ValueError('Invalid roles.')
    s=backup['settings']
    if s is not None:
        if not isinstance(s,dict) or set(s)!={'guild','welcome','category','staff','logs'} or s['guild']!=guild: raise ValueError('Invalid setup.')
        if any(type(x) is not int or x<=0 for x in s.values()): raise ValueError('Invalid setup IDs.')

def suspicious_link(text, blocked):
    # Local heuristics, not a malware reputation service; no URLs are opened.
    links=re.findall(r'https?://[^\s<>]+',text,re.I)
    for link in links:
        try:
            u=urlsplit(link); host=(u.hostname or '').lower().rstrip('.')
            if not host or u.username or u.password: return True
            if any(host==d or host.endswith('.'+d) for d in blocked): return True
            if any(label.startswith('xn--') for label in host.split('.')): return True
            try:
                ipaddress.ip_address(host)
                return True
            except ValueError: pass
        except ValueError: return True
    return False

def blocked_word(text, words):
    return any(re.search(r'(?<!\w)'+re.escape(w)+r'(?!\w)',text,re.I) for w in words)

def award_activity(profile, content, now, amount=10, cooldown=60, channel=None):
    digest=hashlib.sha256(content.strip().casefold().encode()).hexdigest()
    last_channel=profile.get('last_xp_channels',{}).get(str(channel),0) if channel is not None else profile['last_xp']
    if amount<=0 or len(content.strip())<5 or (profile['last_xp']>0 and now-profile['last_xp']<min(cooldown,60)) or (last_channel>0 and now-last_channel<cooldown) or digest==profile['last_hash']: return False
    profile['last_xp']=now; profile['last_hash']=digest; profile['xp']+=amount; profile['coins']+=2
    if channel is not None:
        history=profile.setdefault('last_xp_channels',{});history[str(channel)]=now
        if len(history)>50: del history[min(history,key=history.get)]
    unlock(profile,'First words')
    if profile['xp']>=500: unlock(profile,'Level five')
    return True

def unlock(profile, name):
    if name not in profile['achievements']: profile['achievements'].append(name)

def win_board(board):
    for a,b,c in [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]:
        if board[a] and board[a]==board[b]==board[c]: return board[a]
    return 'draw' if all(board) else None

def convert(value, source, target):
    units={'m':('length',1),'km':('length',1000),'cm':('length',.01),'ft':('length',.3048),
           'in':('length',.0254),'mi':('length',1609.344),'kg':('mass',1),'g':('mass',.001),
           'lb':('mass',.45359237),'oz':('mass',.028349523125),'l':('volume',1),
           'ml':('volume',.001),'gal_us':('volume',3.785411784)}
    source,target=source.lower(),target.lower()
    if source in {'c','f','k'} and target in {'c','f','k'}:
        c=(value-32)*5/9 if source=='f' else value-273.15 if source=='k' else value
        if c< -273.15: raise ValueError('Temperature is below absolute zero.')
        return c*9/5+32 if target=='f' else c+273.15 if target=='k' else c
    if source not in units or target not in units or units[source][0]!=units[target][0]: raise ValueError('Use compatible supported units; see /tools units.')
    return value*units[source][1]/units[target][1]
