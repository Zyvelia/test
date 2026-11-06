"""Server-scoped XP rules, branding and provider filters."""
import html
from aiohttp import web
from .settings import validate_resources
from .customization import THEMES,filters_for

class AdvancedDashboard:
 def advanced_forms(self,gid,session):
  store=self.service.store;guild=self.service.bot.get_guild(gid);hidden=self.hidden(session,gid)
  branding=store.option(gid,'branding',{})
  result='<details><summary>Dashboard themes and branding</summary><form action="/branding" method="post">'+hidden
  result+=f'<input name="name" maxlength="40" value="{html.escape(branding.get("name","Vivi"),quote=True)}" placeholder="Display brand" required><input name="tagline" maxlength="160" value="{html.escape(branding.get("tagline",""),quote=True)}" placeholder="Tagline">'
  result+=self.select('theme',[(x,x.title()) for x in THEMES],branding.get('theme','midnight'))
  result+=f'<input name="accent" type="color" value="{branding.get("accent",THEMES[branding.get("theme","midnight")]["accent"])}"><button>Save branding</button></form></details>'
  result+='<details><summary>Per-channel XP</summary><p>Text channels and forum channels; threads inherit the parent rule. Cooldowns still prevent rapid channel hopping.</p>'
  for ident,rule in store.option(gid,'xp_channels',{}).items():
   result+='<form action="/xp-channel" method="post">'+hidden+f'Channel {ident}: {rule["amount"]} XP / {rule["cooldown"]}s · {"enabled" if rule["enabled"] else "excluded"}<input name="channel" type="hidden" value="{ident}"><button name="action" value="remove">Use default</button></form>'
  import discord
  channels=[(c.id,c.name) for c in getattr(guild,'channels',guild.text_channels) if isinstance(c,(discord.TextChannel,discord.ForumChannel))]
  result+='<form action="/xp-channel" method="post">'+hidden+self.select('channel',channels)
  result+='<label>XP per award<input name="amount" type="number" min="0" max="100" value="10"></label><label>Cooldown seconds<input name="cooldown" type="number" min="30" max="3600" value="60"></label><label><input name="enabled" type="checkbox" value="yes" checked> Award XP in this channel</label><button name="action" value="save">Save channel XP</button></form></details>'
  result+='<details><summary>Notification filters</summary><p>Exact GitHub commit branch, GitHub release/tag patterns, or Twitch categories. YouTube RSS does not expose category metadata.</p>'
  for row in store.records(gid,'notification'):
   d=row['data'];f=d.get('filters',{})
   result+='<form action="/filters" method="post">'+hidden+f'<b>{html.escape(d["source"])} ({d["provider"]})</b><input name="id" type="hidden" value="{row["id"]}"><input name="branch" placeholder="Exact branch" value="{html.escape(f.get("branch",""),quote=True)}"><input name="tags" placeholder="Tag patterns, comma separated" value="{html.escape(", ".join(f.get("tags",[])),quote=True)}"><input name="categories" placeholder="Category patterns, comma separated" value="{html.escape(", ".join(f.get("categories",[])),quote=True)}"><button>Save filters</button></form>'
  return result+'</details>'

 async def xp_channel(self,request):
  data,session,gid,guild=await self.form(request);rules=self.service.store.option(gid,'xp_channels',{})
  try:
   ident=str(int(data.get('channel','')))
   if data.get('action')=='remove':rules.pop(ident,None)
   elif data.get('action')=='save':rules[ident]=dict(enabled=data.get('enabled')=='yes',amount=int(data.get('amount','10')),cooldown=int(data.get('cooldown','60')))
   else:raise ValueError('Invalid XP action.')
   validate_resources(self.service.store,guild,'xp_channels',rules)
  except (ValueError,KeyError) as error:raise web.HTTPBadRequest(text=str(error))
  self.service.store.set_option(gid,'xp_channels',rules);self.done(gid)

 async def branding(self,request):
  data,session,gid,guild=await self.form(request)
  value={key:str(data.get(key,'')) for key in ['name','tagline','theme','accent']}
  try:validate_resources(self.service.store,guild,'branding',value)
  except ValueError as error:raise web.HTTPBadRequest(text=str(error))
  self.service.store.set_option(gid,'branding',value);self.done(gid)

 async def filters(self,request):
  data,session,gid,guild=await self.form(request);record=self.service.store.record(str(data.get('id','')))
  if not record or record['guild']!=gid or record['kind']!='notification':raise web.HTTPNotFound(text='Subscription not found.')
  try:value=filters_for(record['data']['provider'],dict(branch=str(data.get('branch','')),tags=[x.strip() for x in str(data.get('tags','')).split(',') if x.strip()],categories=[x.strip() for x in str(data.get('categories','')).split(',') if x.strip()]))
  except ValueError as error:raise web.HTTPBadRequest(text=str(error))
  record['data'].update(filters=value,initialized=False,last=None,next_poll=0)
  self.service.store.put_record(gid,'notification',record['data'],record['id']);self.done(gid)
