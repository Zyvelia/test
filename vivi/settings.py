"""Shared parsing and resource validation for Discord commands and the dashboard."""
import json
import discord
from .features import OPTION_TYPES, validate_option
from .policy import safe_self_role

DEFAULTS={'welcome_text':'Welcome {member} to {server}!','welcome_color':'#87CEEB',
 'goodbye_text':'Goodbye {member}.','spam_limit':6,'daily_hour':9,'timezone':'UTC','ai_limit':20,
 'mention_limit':5,'raid_limit':8,'raid_window':30,'raid_action':'alert','raid_lock_minutes':5,
 'language':'en','backup_hours':24,'backup_keep':7, 'warning_count':3,'warning_timeout_minutes':10,'warning_window_days':30,'voice_user_limit':0}

def parse_value(name,text):
    if name not in OPTION_TYPES: raise ValueError('Unknown setting.')
    typ=OPTION_TYPES[name]
    if typ is bool:
        if text.lower() not in {'true','false'}: raise ValueError('Use true or false.')
        value=text.lower()=='true'
    elif typ is int: value=int(text)
    elif typ is dict: value=json.loads(text)
    elif typ is list:
        value=[x.strip() for x in text.split(',') if x.strip()]
        if name=='ai_channels': value=[int(x) for x in value]
        if name=='blocked_domains': value=[x.lower().strip('.') for x in value]
    else: value=text
    validate_option(name,value)
    return value

def validate_resources(store,guild,name,value):
    validate_option(name,value)
    config=store.settings(guild.id)
    if name in {'autorole','rules_role'} and value:
        role=guild.get_role(value)
        if not config or not role or role.id==config['staff'] or not safe_self_role(role,guild.me):
            raise ValueError('Choose a safe non-staff role below Vivi; configure server channels first.')
    channels={'goodbye_channel':discord.TextChannel,'birthday_channel':discord.TextChannel,
              'daily_channel':discord.TextChannel,'raid_channel':discord.TextChannel,
              'voice_lobby':discord.VoiceChannel,'voice_category':discord.CategoryChannel}
    if name in channels and value and not isinstance(guild.get_channel(value),channels[name]):
        raise ValueError('Choose an existing channel of the correct type in this server.')
    if name=='ai_channels' and any(not isinstance(guild.get_channel(x),discord.TextChannel) for x in value):
        raise ValueError('Choose text channels in this server.')
    if name=='xp_channels' and any(not isinstance(guild.get_channel(int(x)),(discord.TextChannel,discord.ForumChannel)) for x in value):
        raise ValueError('XP overrides require text channels in this server.')
    if name=='ticket_categories' and any(not isinstance(guild.get_channel(x),discord.CategoryChannel) for x in value.values()):
        raise ValueError('Every ticket category must be a Discord category in this server.')

def validate_setup(guild,settings):
    if set(settings)!={'welcome','category','staff','logs'}: raise ValueError('Missing server settings.')
    welcome=guild.get_channel(settings['welcome']); category=guild.get_channel(settings['category'])
    logs=guild.get_channel(settings['logs']); staff=guild.get_role(settings['staff'])
    if not isinstance(welcome,discord.TextChannel) or not isinstance(logs,discord.TextChannel) or not isinstance(category,discord.CategoryChannel):
        raise ValueError('Select welcome/log text channels and a ticket category.')
    if not staff or staff.is_default() or staff.managed: raise ValueError('Choose a dedicated human support role.')
    if logs.permissions_for(guild.default_role).view_channel: raise ValueError('The staff log must deny @everyone View Channel.')
    for channel in (welcome,logs):
        p=channel.permissions_for(guild.me)
        if not (p.view_channel and p.send_messages): raise ValueError('Vivi needs View Channel and Send Messages in the selected text channels.')
    p=category.permissions_for(guild.me)
    if not (p.view_channel and p.manage_channels): raise ValueError('Vivi needs View Channel and Manage Channels in the ticket category.')
    if not logs.permissions_for(guild.me).attach_files: raise ValueError('Vivi needs Attach Files in staff logs.')


def validate_restore(store,guild,backup):
    from types import SimpleNamespace
    from .features import validate_backup
    validate_backup(guild.id,backup)
    config=backup['settings']
    if config: validate_setup(guild,{k:v for k,v in config.items() if k!='guild'})
    proposed=SimpleNamespace(settings=lambda ident:config)
    for key,value in backup['options'].items(): validate_resources(proposed,guild,key,value)
    for item in backup.get('subscriptions',[]):
        if not isinstance(guild.get_channel(item['channel']),discord.TextChannel): raise ValueError('A notification destination is missing from this server.')
