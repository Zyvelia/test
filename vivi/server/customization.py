from contextvars import ContextVar
UI_BRAND=ContextVar("vivi_ui_brand",default={})
"""Validated branding, per-channel activity awards and provider filter policy."""
import fnmatch
import re

THEMES={
 'midnight':dict(background='#111827',panel='#1f2937',text='#e5e7eb',accent='#87ceeb'),
 'velvet':dict(background='#180f22',panel='#302039',text='#f7edf8',accent='#d7a1d9'),
 'ocean':dict(background='#081c2b',panel='#123347',text='#e6f5ff',accent='#64d8df'),
 'light':dict(background='#f1f5f9',panel='#ffffff',text='#182436',accent='#2553a8'),
}

def validate_xp(value):
 if not isinstance(value,dict) or len(value)>50: raise ValueError('Maximum 50 channel XP overrides.')
 for ident,rule in value.items():
  if not isinstance(ident,str) or not ident.isdigit() or not 0<int(ident)<2**63: raise ValueError('Invalid XP channel ID.')
  if not isinstance(rule,dict) or set(rule)!={'enabled','amount','cooldown'}: raise ValueError('Each XP rule needs enabled, amount and cooldown.')
  if type(rule['enabled']) is not bool or type(rule['amount']) is not int or not 0<=rule['amount']<=100: raise ValueError('XP amount must be 0–100.')
  if type(rule['cooldown']) is not int or not 30<=rule['cooldown']<=3600: raise ValueError('XP cooldown must be 30–3600 seconds.')

def validate_brand(value):
 if not isinstance(value,dict) or set(value)-{'name','tagline','theme','accent'}: raise ValueError('Unknown branding fields.')
 if not isinstance(value.get('name','Vivi'),str) or not 1<=len(value.get('name','Vivi'))<=40: raise ValueError('Brand name must be 1–40 characters.')
 if not isinstance(value.get('tagline',''),str) or len(value.get('tagline',''))>160: raise ValueError('Tagline must be at most 160 characters.')
 if value.get('theme','midnight') not in THEMES: raise ValueError('Choose midnight, velvet, ocean or light.')
 if not re.fullmatch(r'#[0-9a-fA-F]{6}',value.get('accent',THEMES[value.get('theme','midnight')]['accent'])): raise ValueError('Use a hex accent color.')

def filters_for(provider,value=None):
 value={} if value is None else value
 if not isinstance(value,dict) or set(value)-{'branch','tags','categories'}: raise ValueError('Unknown notification filter.')
 result=dict(branch=value.get('branch',''),tags=value.get('tags',[]),categories=value.get('categories',[]))
 branch=result['branch']
 if not isinstance(branch,str) or len(branch)>100 or (branch and (not re.fullmatch(r'[A-Za-z0-9_./-]+',branch) or '..' in branch or branch.startswith('/'))): raise ValueError('Use a simple exact branch name.')
 for key in ['tags','categories']:
  if not isinstance(result[key],list) or len(result[key])>20 or any(not isinstance(x,str) or not 1<=len(x)<=100 for x in result[key]): raise ValueError('Maximum 20 nonempty tag/category patterns.')
 if branch and provider!='github_commits': raise ValueError('Branch filters apply to GitHub commits.')
 if result['tags'] and provider not in {'github_releases','github_commits','webhook'}: raise ValueError('Tag filters apply to GitHub or custom webhooks.')
 if result['categories'] and provider not in {'twitch','github_releases','webhook'}: raise ValueError('Categories apply to Twitch, release/prerelease or custom webhooks; YouTube RSS has no category metadata.')
 if branch and result['tags'] and provider=='github_commits': raise ValueError('Choose either a branch or tag patterns for a commit watch.')
 return result

def accepts(data,event):
 filters=filters_for(data['provider'],data.get('filters'))
 def matches(patterns,value): return not patterns or any(fnmatch.fnmatchcase(str(value).casefold(),p.casefold()) for p in patterns)
 if filters['branch'] and event.get('branch')!=filters['branch']: return False
 if not matches(filters['tags'],event.get('tag','')): return False
 if not matches(filters['categories'],event.get('category','')): return False
 return True


def register_customization(bot):
 import discord
 from discord import app_commands
 from vivi.bot import reply
 from vivi.core.settings import validate_resources
 store=bot.store
 @bot.tree.get_command('economy').command(name='channel_xp',description='Configure XP amounts, cooldowns or exclusions for a text channel.')
 @app_commands.checks.has_permissions(administrator=True)
 async def channel_xp(i:discord.Interaction,channel:discord.TextChannel,enabled:bool=True,amount:app_commands.Range[int,0,100]=10,cooldown:app_commands.Range[int,30,3600]=60):
  values=store.option(i.guild_id,'xp_channels',{});values[str(channel.id)]=dict(enabled=enabled,amount=amount,cooldown=cooldown)
  validate_resources(store,i.guild,'xp_channels',values);store.set_option(i.guild_id,'xp_channels',values)
  await reply(i,'Channel XP rule saved. Threads inherit the parent rule.')
 @bot.tree.get_command('admin').command(name='branding',description='Set dashboard branding and welcome/profile footer identity.')
 @app_commands.checks.has_permissions(administrator=True)
 @app_commands.choices(theme=[app_commands.Choice(name=x,value=x) for x in THEMES])
 async def branding(i:discord.Interaction,name:app_commands.Range[str,1,40]='Vivi',tagline:app_commands.Range[str,0,160]='',theme:str='midnight',accent:str='#87CEEB'):
  value=dict(name=name,tagline=tagline,theme=theme,accent=accent);validate_brand(value);store.set_option(i.guild_id,'branding',value)
  await reply(i,'Branding saved. The Discord application username is managed separately in Developer Portal.')
 @bot.tree.get_command('notify').command(name='filters',description='Set branch, tag-pattern or category-pattern filters for a subscription.')
 @app_commands.checks.has_permissions(administrator=True)
 async def filters(i:discord.Interaction,ident:str,branch:str='',tags:str='',categories:str=''):
  row=store.record(ident)
  if not row or row['guild']!=i.guild_id or row['kind']!='notification':return await reply(i,'Subscription not found in this server.')
  value=filters_for(row['data']['provider'],dict(branch=branch,tags=[x.strip() for x in tags.split(',') if x.strip()],categories=[x.strip() for x in categories.split(',') if x.strip()]))
  row['data'].update(filters=value,initialized=False,last=None,next_poll=0);store.put_record(i.guild_id,'notification',row['data'],ident)
  await reply(i,'Filters saved; polling establishes a new baseline. Tag filters on commit watches require signed push webhooks.')
 @bot.tree.get_command('notify').command(name='webhook_info',description='Show the configured callback URL without revealing signing secrets.')
 @app_commands.checks.has_permissions(administrator=True)
 async def webhook_info(i:discord.Interaction,ident:str):
  import os
  from urllib.parse import urlsplit
  row=store.record(ident)
  if not row or row['guild']!=i.guild_id or row['kind']!='notification':return await reply(i,'Subscription not found in this server.')
  base=os.getenv('WEBHOOK_PUBLIC_URL','').rstrip('/');url=urlsplit(base)
  if url.scheme!='https' or not url.hostname or url.username is not None or url.query or url.fragment:return await reply(i,'The host must configure WEBHOOK_PUBLIC_URL with its HTTPS webhook endpoint first.')
  await reply(i,f'Callback: {base}/hooks/{ident}\nExport the per-watch signing secret on the host. Secrets are not shown in Discord or the dashboard.')
 @bot.tree.get_command('notify').command(name='clear_webhooks',description='Discard this subscription’s queued/dead webhook deliveries.')
 @app_commands.checks.has_permissions(administrator=True)
 async def clear(i:discord.Interaction,ident:str):
  import time
  row=store.record(ident)
  if not row or row['guild']!=i.guild_id or row['kind']!='notification':return await reply(i,'Subscription not found in this server.')
  jobs=[x for x in store.records(i.guild_id,'webhook_job') if x['data']['watch']==ident]
  with store.db:
   for job in jobs:
    store.db.execute('INSERT OR IGNORE INTO webhook_receipts VALUES (?,?,?)',(ident,job['data']['digest'],time.time()))
    store.db.execute('DELETE FROM records WHERE id=?',(job['id'],))
  await reply(i,f'Discarded {len(jobs)} queued deliveries; duplicate payloads stay suppressed during receipt retention.')
