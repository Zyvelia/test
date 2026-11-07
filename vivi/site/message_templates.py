"""Shared welcome/goodbye rendering with bounded placeholder expansion."""
import re
import discord
from vivi.site.embed_writer import render

def expand(text,member,mention=False):
    values={'member':member.mention if mention else member.display_name,'username':member.display_name,'server':member.guild.name,'member_count':str(getattr(member.guild,'member_count',0) or 0)}
    for key,value in values.items():text=text.replace('{'+key+'}',str(value))
    return text

def cut(text,limit):return text.encode('utf-16-le')[:limit*2].decode('utf-16-le',errors='ignore')

def validate_appearance(value):
    if not isinstance(value,dict) or set(value)-{'color','thumbnail','image'}:raise ValueError('Invalid message appearance.')
    color=value.get('color','')
    if not isinstance(color,str) or (color and not re.fullmatch(r'#[0-9a-fA-F]{6}',color)):raise ValueError('Use a six-digit hex color.')
    for key in ('thumbnail','image'):
        if not isinstance(value.get(key,'template'),str) or value.get(key,'template') not in ('template','member','server','none'):raise ValueError('Choose a supported image source.')
    return value

def message_embed(document,member,appearance=None):
    data={**document};budget=6000
    for key,limit in [('title',256),('description',4096),('footer',2048)]:
        data[key]=cut(expand(data.get(key,''),member),min(limit,budget));budget-=len(data[key].encode('utf-16-le'))//2
    data['fields']=[]
    for field in document.get('fields',[]):
        if budget<2:break
        name=cut(expand(field['name'],member),min(256,budget-1));budget-=len(name.encode('utf-16-le'))//2
        value=cut(expand(field['value'],member),min(1024,budget));budget-=len(value.encode('utf-16-le'))//2
        if name.strip() and value.strip():data['fields'].append(dict(name=name,value=value,inline=field.get('inline',False)))
    appearance=validate_appearance(appearance or {})
    if appearance.get('color'):data['color']=appearance['color']
    for key in ('thumbnail','image'):
        source=appearance.get(key,'template')
        if source!='template':
            asset=getattr(member,'display_avatar',None) if source=='member' else getattr(member.guild,'icon',None) if source=='server' else None
            data[key]=str(asset.url) if asset else ''
    return render(data)
