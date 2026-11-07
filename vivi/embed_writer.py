"""Reusable server embed templates shared by Discord and the website."""
import re
import time
from urllib.parse import urlsplit
import discord

KIND='embed_template'

def validate(document):
    if not isinstance(document,dict):raise ValueError('Invalid embed document.')
    limits={'name':80,'title':256,'description':4096,'footer':2048,'url':2048,'image':2048,'thumbnail':2048}
    clean={}
    for key,limit in limits.items():
        value=document.get(key,'')
        if not isinstance(value,str) or len(value)>limit:raise ValueError(f'{key.title()} must be text up to {limit} characters.')
        clean[key]=value.strip()
    if not clean['name']:raise ValueError('Give this template a name.')
    for key in ('url','image','thumbnail'):
        if clean[key]:
            try:
                url=urlsplit(clean[key]);valid=url.scheme=='https' and url.hostname and not url.username and not url.password
                url.port
            except ValueError:valid=False
            if not valid:raise ValueError(f'{key.title()} must be a valid HTTPS URL.')
    color=document.get('color','#ff65ad')
    if not isinstance(color,str) or not re.fullmatch('#[0-9a-fA-F]{6}',color):raise ValueError('Use a six-digit hex color, such as #ff65ad.')
    clean['color']=color
    fields=document.get('fields',[])
    if not isinstance(fields,list) or len(fields)>25:raise ValueError('Use up to 25 fields.')
    clean['fields']=[]
    for field in fields:
        if not isinstance(field,dict):raise ValueError('Invalid field.')
        name,value=field.get('name',''),field.get('value','')
        if not isinstance(name,str) or not isinstance(value,str) or not 1<=len(name.strip())<=256 or not 1<=len(value.strip())<=1024:raise ValueError('Each field needs a name (1–256) and text (1–1024).')
        if not isinstance(field.get('inline',False),bool):raise ValueError('Invalid inline setting.')
        clean['fields'].append(dict(name=name.strip(),value=value.strip(),inline=field.get('inline',False)))
    if not any(clean[k] for k in ('title','description','image','thumbnail')) and not fields:raise ValueError('Add a title, description, field or image.')
    # Discord counts UTF-16 code units, including non-BMP emoji.
    size=sum(len(s.encode('utf-16-le'))//2 for s in [clean['title'],clean['description'],clean['footer']]+[f[k] for f in clean['fields'] for k in ('name','value')])
    if size>6000:raise ValueError('The embed exceeds Discord’s 6,000-character combined limit.')
    for key,limit in [('title',256),('description',4096),('footer',2048)]:
        if len(clean[key].encode('utf-16-le'))//2>limit:raise ValueError(f'{key.title()} exceeds Discord’s character limit (emoji can count twice).')
    for f in clean['fields']:
        if len(f['name'].encode('utf-16-le'))//2>256 or len(f['value'].encode('utf-16-le'))//2>1024:raise ValueError('Field exceeds Discord’s character limit (emoji can count twice).')
    return clean

def render(document):
    data=validate(document);embed=discord.Embed(title=data['title'] or None,description=data['description'] or None,color=int(data['color'][1:],16),url=data['url'] or None)
    if data['footer']:embed.set_footer(text=data['footer'])
    if data['image']:embed.set_image(url=data['image'])
    if data['thumbnail']:embed.set_thumbnail(url=data['thumbnail'])
    for field in data['fields']:embed.add_field(**field)
    return embed

def load(store,guild,ident):
    row=store.record(ident)
    if not row or row['guild']!=guild or row['kind']!=KIND:raise ValueError('This saved embed does not exist in this server.')
    return row

def save(store,guild,document,actor,ident=''):
    data=validate(document)
    if ident:load(store,guild,ident)
    elif len(store.records(guild,KIND))>=100:raise ValueError('This server has 100 saved embeds. Remove one before adding another.')
    return store.put_record(guild,KIND,dict(document=data,updated=time.time(),editor=actor),ident or None)

async def publish(guild,channel_id,document,actor):
    """Fetch current member permissions immediately before posting; no mentions."""
    channel=guild.get_channel(channel_id)
    if not isinstance(channel,discord.TextChannel):raise ValueError('Choose a text channel in this server.')
    member=await guild.fetch_member(actor)
    if not member.guild_permissions.administrator:raise PermissionError('Administrator permission is required.')
    permissions=channel.permissions_for(guild.me)
    if not permissions.view_channel or not permissions.send_messages or not permissions.embed_links:raise PermissionError('Vivi needs View Channel, Send Messages and Embed Links in this channel.')
    return await channel.send(embed=render(document),allowed_mentions=discord.AllowedMentions.none())
