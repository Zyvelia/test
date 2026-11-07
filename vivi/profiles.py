"""Portable profile cards, bounded cosmetics, per-field privacy and reviewed banner uploads."""
import asyncio
import copy
import io
import json
import re
import secrets
import time
import warnings
from pathlib import Path
import discord
from discord import app_commands
from PIL import Image,ImageDraw,ImageFont,ImageOps
from .bot import reply,audit
from .features import enabled,SHOP
from .guild_library import clean_text,scoped
from .productivity import atomic_private

ASSETS=Path(__file__).parent/'assets'
BACKGROUNDS=['velvet_ruins','rose_dusk','moon_lake','violet_garden','cloud_dream','midnight_geometry']
FONTS=['rounded','serif','mono'];LAYOUTS=['compact','detailed','gallery'];STICKERS=['star','moon','heart','flower','crown','sparkle']
GRADIENTS={'violet_rose':['#b692ed','#ec9cbb'],'moonlight':['#8fcbdc','#c4b2f0'],'golden':['#efc875','#e59c9c'],'mint':['#88d4bc','#90b7ed']}
FIELDS=['xp','coins','achievements','showcase','status','avatar','banner','title']
DEFAULT_STYLE=dict(background='velvet_ruins',gradient='violet_rose',font='rounded',layout='detailed',status='',stickers=[],showcase=[])


def visible_fields(profile,showcase=None):
    public=profile.get('card_visibility',{});result={}
    values=dict(xp=profile.get('xp',0),coins=profile.get('coins',0),achievements=profile.get('achievements',[]),status=profile.get('card_style',{}).get('status',''),showcase=showcase or [])
    return {key:value for key,value in values.items() if public.get(key,True)}


def normalize_banner(body):
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(body)) as source:
            if source.format not in {'PNG','JPEG','WEBP'} or source.width*source.height>8_000_000:raise ValueError('Use a PNG, JPEG or WebP image up to eight million pixels.')
            picture=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),(900,360))
            out=io.BytesIO();picture.save(out,format='PNG',optimize=True);return out.getvalue()


def gradient_colors(value):
    if isinstance(value,str) and value in GRADIENTS:return GRADIENTS[value]
    if isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6},#[0-9a-fA-F]{6}',value):return value.split(',')
    raise ValueError('Choose a gradient preset or two hex colors separated by a comma, such as #bb99ee,#ffb6cc.')

def validate_style(style):
    if not isinstance(style,dict) or set(style)-set(DEFAULT_STYLE):raise ValueError('Unknown profile style field.')
    if style.get('font') not in FONTS or style.get('layout') not in LAYOUTS:raise ValueError('Choose a supported font, layout and gradient.')
    gradient_colors(style.get('gradient'))
    if not isinstance(style.get('status'),str) or len(style['status'])>120:raise ValueError('Status must be at most 120 characters.')
    background=style.get('background','')
    if background not in BACKGROUNDS and not re.fullmatch(r'upload:[a-f0-9]{32}',background):raise ValueError('Choose a starter background or an approved upload ID.')
    stickers=style.get('stickers',[])
    if not isinstance(stickers,list) or len(stickers)>6:raise ValueError('Maximum six stickers.')
    for item in stickers:
        if not isinstance(item,dict) or set(item)!={'item','x','y'} or item['item'] not in STICKERS or type(item['x']) is not int or type(item['y']) is not int or not 0<=item['x']<=860 or not 0<=item['y']<=320:raise ValueError('Sticker coordinates must fit the 900×360 card.')
    showcase=style.get('showcase',[])
    if not isinstance(showcase,list) or len(showcase)>3 or any(not isinstance(x,dict) or set(x)!={'kind','value'} or x['kind'] not in {'achievement','creation'} or not isinstance(x['value'],str) or len(x['value'])>120 for x in showcase):raise ValueError('Use up to three supported showcase slots.')
    return style


def font(name,size):return ImageFont.load_default(size=size) if name=='rounded' else ImageFont.truetype(str(ASSETS/'fonts'/(name+'.ttf')),size=size)


def sticker(draw,item,x,y):
    gold='#f3d395';pink='#efb1cd'
    if item in {'star','sparkle'}:
        import math
        count=5 if item=='star' else 4;points=[]
        for n in range(count*2):
            angle=-math.pi/2+n*math.pi/count;radius=19 if n%2==0 else 8;points.append((x+20+math.cos(angle)*radius,y+20+math.sin(angle)*radius))
        draw.polygon(points,fill=gold)
    elif item=='moon':draw.ellipse((x,y,x+38,y+38),fill='#ded6fa');draw.ellipse((x+13,y-3,x+43,y+27),fill='#514665')
    elif item=='heart':draw.ellipse((x+1,y+3,x+22,y+23),fill=pink);draw.ellipse((x+17,y+3,x+38,y+23),fill=pink);draw.polygon([(x+1,y+15),(x+38,y+15),(x+20,y+39)],fill=pink)
    elif item=='crown':draw.polygon([(x,y+5),(x+9,y+18),(x+20,y),(x+30,y+18),(x+39,y+5),(x+34,y+35),(x+5,y+35)],fill=gold)
    else:
        for dx,dy in [(0,12),(12,0),(24,12),(12,24)]:draw.ellipse((x+dx,y+dy,x+dx+15,y+dy+15),fill=pink)
        draw.ellipse((x+12,y+12,x+27,y+27),fill=gold)


def render_profile(name,profile,style,avatar=None,banner=None,showcase=None):
    validate_style(style);visibility=profile.get('card_visibility',{});background=style['background'] if style['background'] in BACKGROUNDS else 'velvet_ruins'
    with Image.open(ASSETS/'profile-backgrounds'/(background+'.png')) as source:image=source.convert('RGBA')
    if banner and visibility.get('banner',True):
        with Image.open(io.BytesIO(banner)) as source:image=ImageOps.fit(source.convert('RGBA'),(900,360))
    overlay=Image.new('RGBA',image.size);draw=ImageDraw.Draw(overlay)
    layout=style['layout'];right=870 if layout!='gallery' else 640
    draw.rounded_rectangle((18,18,right,342),radius=22,fill=(13,15,27,205));image=Image.alpha_composite(image,overlay);draw=ImageDraw.Draw(image)
    colors=[tuple(bytes.fromhex(c[1:])) for c in gradient_colors(style['gradient'])]
    for x in range(30,right-12):
        t=(x-30)/max(1,right-43);color=tuple(int(a*(1-t)+b*t) for a,b in zip(*colors));draw.line((x,27,x,32),fill=color,width=1)
    if avatar and visibility.get('avatar',True):
        with Image.open(io.BytesIO(avatar)) as source:picture=ImageOps.fit(source.convert('RGB'),(90,90))
        mask=Image.new('L',(90,90));ImageDraw.Draw(mask).ellipse((0,0,89,89),fill=255);image.paste(picture,(38,53),mask)
    x=150 if avatar and visibility.get('avatar',True) else 38
    draw.text((x,55),name[:28],fill='white',font=font(style['font'],27));values=visible_fields(dict(profile,card_style=style),showcase)
    lines=[]
    if 'status' in values and values['status']:lines.append(values['status'])
    if 'xp' in values:lines.append(f'Level {values["xp"]//100} · {values["xp"]} XP')
    if 'coins' in values:lines.append(f'{values["coins"]} virtual coins')
    if 'achievements' in values and values['achievements']:lines.append('Awards: '+', '.join(values['achievements'][:4]))
    if 'showcase' in values and values['showcase']:lines.extend('Showcase: '+value for value in values['showcase'])
    if layout=='compact':lines=lines[:4]
    size=16 if layout=='compact' else 18;y=105
    for line in lines:
        width=48 if layout=='gallery' else 65
        for start in range(0,min(len(line),width*2),width):
            if y>300:break
            draw.text((x if y<150 else 38,y),line[start:start+width],fill='#ece5f1',font=font(style['font'],size));y+=size+9
    equipped=SHOP.get(profile.get('equipped',''));title=equipped[1].split(' ',1)[-1] if equipped and visibility.get('title',True) else ''
    draw.text((38,321),'Vivi'+(' · '+title if title else ''),font=font(style['font'],12),fill='#d2bfdc')
    for item in style.get('stickers',[]):sticker(draw,item['item'],item['x'],item['y'])
    out=io.BytesIO();image.convert('RGB').save(out,format='PNG');return out.getvalue()

class ProfileCards:
    def __init__(self,service):self.service=service;self.bot=service.bot;self.store=service.store
    def style(self,guild,user):return dict(copy.deepcopy(DEFAULT_STYLE),**self.store.profile(guild,user).get('card_style',{}))
    def banner(self,guild,user,style,strict=False):
        background=style['background']
        if not background.startswith('upload:'):return None
        ident=background[7:]
        if not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('Invalid uploaded banner ID.')
        row=self.store.record(ident)
        if row and row['guild']==guild and row['kind']=='profile_banner' and row['data']['user']==user and row['data']['status']=='approved':
            path=self.store.path.parent/'profile-banners'/str(guild)/(ident+'.png')
            if path.is_file():return path.read_bytes()
        if strict:raise ValueError('This banner is not an available approved upload belonging to you.')
        return None
    def showcases(self,guild,user,profile,style):
        result=[]
        for entry in style.get('showcase',[]):
            if entry['kind']=='achievement' and entry['value'] in profile.get('achievements',[]):result.append(entry['value'])
            elif entry['kind']=='creation':
                row=self.store.record(entry['value'])
                if row and row['guild']==guild and row['kind']=='library_entry' and row['data']['author']==user:result.append(row['data']['title'])
        return result
    async def show(self,i,member=None,preview=None):
        target=member or i.user;p=self.store.profile(i.guild_id,target.id)
        if not p.get('visible',True) and target.id!=i.user.id:return await reply(i,'This member’s profile is private.')
        if not any(enabled(self.store,i.guild_id,key) for key in ['profiles','xp','economy']):return await reply(i,'Profiles, XP and economy are disabled here.')
        style=preview or self.style(i.guild_id,target.id);validate_style(style)
        await i.response.defer(ephemeral=True);avatar=None
        if p.get('card_visibility',{}).get('avatar',True):
            try:avatar=await target.display_avatar.with_size(128).with_format('png').read()
            except (discord.HTTPException,AttributeError):pass
        p=self.store.profile(i.guild_id,target.id)
        if not p.get('visible',True) and target.id!=i.user.id:return await reply(i,'This member’s profile is private.')
        style=preview or self.style(i.guild_id,target.id)
        showcase=self.showcases(i.guild_id,target.id,p,style)
        body=await asyncio.to_thread(render_profile,target.display_name,p,style,avatar,self.banner(i.guild_id,target.id,style),showcase)
        await i.followup.send(file=discord.File(io.BytesIO(body),filename='vivi-profile.png'),ephemeral=True)
    def delete_banners(self,guild,user):
        for row in self.store.records(guild,'profile_banner'):
            if row['data']['user']==user:
                (self.store.path.parent/'profile-banners'/str(guild)/(row['id']+'.png')).unlink(missing_ok=True);self.store.delete_record(row['id'])


def register_profiles(bot):
    cards=bot.community.profiles;service=bot.community;store=bot.store
    group=app_commands.Group(name='profile',description='Profile cards, starter cosmetics, privacy and saved loadouts',guild_only=True)
    @group.command(name='view',description='View a profile card with its owner’s field visibility settings applied.')
    async def view(i:discord.Interaction,member:discord.Member=None):await cards.show(i,member)
    @group.command(name='catalog',description='List free starter backgrounds, gradients, fonts, layouts and stickers.')
    async def catalog(i:discord.Interaction):await reply(i,'Free backgrounds: '+', '.join(BACKGROUNDS)+'\nGradients: '+', '.join(GRADIENTS)+' or #RRGGBB,#RRGGBB'+'\nFonts: '+', '.join(FONTS)+'\nLayouts: '+', '.join(LAYOUTS)+'\nStickers: '+', '.join(STICKERS)+'\nUse /profile → customize, /profile → sticker and /profile → preview.')
    @group.command(name='customize',description='Customize your card; omit fields to keep them, or use clear_status:true.')
    async def customize(i:discord.Interaction,background:str='',gradient:str='',font:str='',layout:str='',status:app_commands.Range[str,1,120]=None,clear_status:bool=False):
        if not await service.need(i,'profiles'):return
        style=cards.style(i.guild_id,i.user.id)
        for key,value in dict(background=background,gradient=gradient,font=font,layout=layout).items():
            if value:style[key]=value
        if status is not None:style['status']=status
        if clear_status:style['status']=''
        try:validate_style(style);clean_text(store,i.guild_id,style['status']);cards.banner(i.guild_id,i.user.id,style,True)
        except ValueError as error:return await reply(i,str(error))
        p=store.profile(i.guild_id,i.user.id);p['card_style']=style;store.save_profile(i.guild_id,i.user.id,p);await reply(i,'Profile style saved. Use /profile → preview to inspect it.')
    @group.command(name='preview',description='Privately preview current or temporary appearance changes without saving.')
    async def preview(i:discord.Interaction,background:str='',gradient:str='',font:str='',layout:str=''):
        style=cards.style(i.guild_id,i.user.id)
        for key,value in dict(background=background,gradient=gradient,font=font,layout=layout).items():
            if value:style[key]=value
        try:validate_style(style);cards.banner(i.guild_id,i.user.id,style,True)
        except ValueError as error:return await reply(i,str(error))
        await cards.show(i,preview=style)
    @group.command(name='visibility',description='Set privacy for one profile field, or all for the whole profile.')
    @app_commands.choices(field=[app_commands.Choice(name=x,value=x) for x in ['all']+FIELDS])
    async def visibility(i:discord.Interaction,field:str,public:bool):
        p=store.profile(i.guild_id,i.user.id)
        if field=='all':p['visible']=public
        else:p.setdefault('card_visibility',{})[field]=public
        store.save_profile(i.guild_id,i.user.id,p);await reply(i,f'{field}: '+('visible.' if public else 'private.'))
    @group.command(name='sticker',description='Place a free sticker, or remove a sticker by its 1-based slot.')
    @app_commands.choices(item=[app_commands.Choice(name=x,value=x) for x in STICKERS])
    async def sticker_command(i:discord.Interaction,item:str='star',x:app_commands.Range[int,0,860]=800,y:app_commands.Range[int,0,320]=35,remove_slot:app_commands.Range[int,1,6]=None):
        if not await service.need(i,'profiles'):return
        style=cards.style(i.guild_id,i.user.id)
        if remove_slot is not None:
            if remove_slot>len(style['stickers']):return await reply(i,'That sticker slot is empty.')
            style['stickers'].pop(remove_slot-1)
        else:
            if len(style['stickers'])>=6:return await reply(i,'Remove a sticker first; maximum six.')
            style['stickers'].append(dict(item=item,x=x,y=y))
        validate_style(style);p=store.profile(i.guild_id,i.user.id);p['card_style']=style;store.save_profile(i.guild_id,i.user.id,p);await reply(i,'Sticker placement saved.')
    @group.command(name='showcase',description='Set one of three showcase slots to an earned award or your published library entry.')
    @app_commands.choices(kind=[app_commands.Choice(name=x,value=x) for x in ['achievement','creation','clear']])
    async def showcase(i:discord.Interaction,slot:app_commands.Range[int,1,3],kind:str,value:str=''):
        if not await service.need(i,'profiles'):return
        p=store.profile(i.guild_id,i.user.id);style=cards.style(i.guild_id,i.user.id)
        if kind=='achievement' and value not in p['achievements']:return await reply(i,'Choose an achievement you have already earned.')
        if kind=='creation':
            row=store.record(value)
            if not row or row['guild']!=i.guild_id or row['kind']!='library_entry' or row['data']['author']!=i.user.id:return await reply(i,'Choose one of your published library entries in this server.')
        items=style['showcase']
        if kind=='clear':
            if slot<=len(items):items.pop(slot-1)
        else:
            if slot>len(items)+1:return await reply(i,'Fill the preceding showcase slot first.')
            entry=dict(kind=kind,value=value)
            if slot<=len(items):items[slot-1]=entry
            else:items.append(entry)
        validate_style(style);p['card_style']=style;store.save_profile(i.guild_id,i.user.id,p);await reply(i,'Showcase saved.')
    @group.command(name='loadout',description='Save, apply, delete or list up to five cosmetic loadouts; privacy stays unchanged.')
    @app_commands.choices(action=[app_commands.Choice(name=x,value=x) for x in ['save','apply','delete','list']])
    async def loadout(i:discord.Interaction,action:str,name:app_commands.Range[str,1,30]='default'):
        if not await service.need(i,'profiles'):return
        p=store.profile(i.guild_id,i.user.id);items=p.setdefault('card_loadouts',{})
        if action=='list':return await reply(i,', '.join(items) or 'No loadouts saved.')
        if action=='save':
            if name not in items and len(items)>=5:return await reply(i,'Maximum five loadouts.')
            items[name]=cards.style(i.guild_id,i.user.id);p.setdefault('card_loadout_items',{})[name]=p.get('equipped','')
        elif action=='delete':
            items.pop(name,None);p.setdefault('card_loadout_items',{}).pop(name,None)
        else:
            if name not in items:return await reply(i,'Loadout not found.')
            style=copy.deepcopy(items[name])
            try:validate_style(style);clean_text(store,i.guild_id,style['status']);cards.banner(i.guild_id,i.user.id,style,True)
            except ValueError as error:return await reply(i,str(error))
            saved_item=p.get('card_loadout_items',{}).get(name,p.get('equipped',''))
            if saved_item and saved_item not in p.get('owned',[]):return await reply(i,'The shop cosmetic saved in this loadout is no longer owned.')
            p['equipped']=saved_item;p['card_style']=style
        store.save_profile(i.guild_id,i.user.id,p);await reply(i,'Loadout action completed. Field visibility settings were preserved.')
    @group.command(name='banner_submit',description='Upload a PNG/JPEG/WebP banner for staff approval before profile use.')
    async def banner_submit(i:discord.Interaction,attachment:discord.Attachment):
        if not await service.need(i,'profiles'):return
        if attachment.size>4*1024*1024:return await reply(i,'Use an image no larger than 4 MiB.')
        rows=[r for r in store.records(i.guild_id,'profile_banner') if r['data']['user']==i.user.id]
        if len(rows)>=5:return await reply(i,'Delete a banner submission first; maximum five per member.')
        await i.response.defer(ephemeral=True)
        try:
            body=await attachment.read()
            if len(body)>4*1024*1024:raise ValueError('Image exceeds 4 MiB.')
            body=await asyncio.to_thread(normalize_banner,body)
        except (ValueError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):return await reply(i,'Use a valid PNG/JPEG/WebP image under 4 MiB and eight million pixels.')
        # Recheck the limit after network and image processing.
        if sum(r['data']['user']==i.user.id for r in store.records(i.guild_id,'profile_banner'))>=5:return await reply(i,'You now have five banner submissions. Delete one first.')
        ident=secrets.token_hex(16);path=store.path.parent/'profile-banners'/str(i.guild_id)/(ident+'.png');atomic_private(path,body)
        store.put_record(i.guild_id,'profile_banner',dict(user=i.user.id,status='pending',created=time.time(),history=[]),ident)
        await reply(i,f'Banner `{ident}` submitted. A staff member must approve it with /profile → banner review. After approval select background `upload:{ident}`. Approved images become visible when you display your card.')
    @group.command(name='banners',description='List your banner submissions, or the review queue as Manage Messages staff.')
    async def banners(i:discord.Interaction,review_queue:bool=False):
        if review_queue and not i.user.guild_permissions.manage_messages:return await reply(i,'Manage Messages permission is required.')
        rows=[r for r in store.records(i.guild_id,'profile_banner') if review_queue or r['data']['user']==i.user.id]
        await reply(i,'\n'.join(f'{r["id"]}: {r["data"]["status"]} · {r["data"].get("reason","")[:100]}' for r in rows[:15]) or 'No banner submissions.')
    @group.command(name='banner_review',description='Privately preview a banner or approve/reject/revoke it with a reason.')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.choices(action=[app_commands.Choice(name=x,value=x) for x in ['preview','approve','reject']])
    async def banner_review(i:discord.Interaction,banner_id:str,action:str='preview',reason:app_commands.Range[str,3,500]=None):
        if not i.user.guild_permissions.manage_messages:return await reply(i,'Manage Messages permission is required.')
        try:row=scoped(store,i.guild_id,banner_id,'profile_banner')
        except ValueError as error:return await reply(i,str(error))
        path=store.path.parent/'profile-banners'/str(i.guild_id)/(row['id']+'.png')
        if action=='preview':
            if not path.is_file():return await reply(i,'Banner file is unavailable.')
            return await i.response.send_message(file=discord.File(path,filename='banner-review.png'),ephemeral=True)
        if row['data']['user']==i.user.id:return await reply(i,'Ask another staff member to review your own banner.')
        if not reason:return await reply(i,'A review reason is required.')
        if action=='approve' and not path.is_file():return await reply(i,'The banner file is unavailable.')
        row['data'].update(status='approved' if action=='approve' else 'rejected',reason=reason,reviewer=i.user.id)
        row['data']['history']=(row['data']['history']+[dict(actor=i.user.id,action=action,reason=reason,at=time.time())])[-20:];store.put_record(i.guild_id,'profile_banner',row['data'],row['id'])
        await reply(i,'Banner decision saved. Rejected/revoked banners cannot render on profile cards.')
    @group.command(name='banner_delete',description='Delete one of your submitted banners and its local image file.')
    async def banner_delete(i:discord.Interaction,banner_id:str):
        try:row=scoped(store,i.guild_id,banner_id,'profile_banner')
        except ValueError as error:return await reply(i,str(error))
        if row['data']['user']!=i.user.id:return await reply(i,'This is not your banner.')
        (store.path.parent/'profile-banners'/str(i.guild_id)/(row['id']+'.png')).unlink(missing_ok=True);store.delete_record(row['id']);await reply(i,'Banner deleted. Cards using it fall back to a starter background.')
    @group.command(name='moderate',description='Clear a member’s profile status with a recorded moderation reason.')
    @app_commands.default_permissions(manage_messages=True)
    async def moderate(i:discord.Interaction,member:discord.Member,reason:app_commands.Range[str,3,500]):
        if not i.user.guild_permissions.manage_messages:return await reply(i,'Manage Messages permission is required.')
        p=store.profile(i.guild_id,member.id);style=cards.style(i.guild_id,member.id);style['status']='';p['card_style']=style
        for item in p.get('card_loadouts',{}).values():item['status']=''
        store.save_profile(i.guild_id,member.id,p);case=store.add_case(i.guild_id,member.id,i.user.id,'profile status cleared',reason);await reply(i,f'Profile status cleared, including saved loadouts. Case #{case}.')
    bot.tree.add_command(group)
