"""Bounded welcome-card layouts and structured announcements, shared by preview and publish."""
import io
import re
from PIL import Image, ImageDraw, ImageFont

DEFAULT_LAYOUT={'background':'#121826','elements':[
    {'type':'avatar','x':30,'y':50,'size':160,'color':'#ffffff','value':''},
    {'type':'header','x':220,'y':40,'size':28,'color':'#87ceeb','value':''},
    {'type':'server','x':220,'y':90,'size':20,'color':'#ffffff','value':''},
    {'type':'message','x':220,'y':130,'size':18,'color':'#c8d2e6','value':''},
    {'type':'brand','x':20,'y':232,'size':12,'color':'#aab4c8','value':''}]}

def validate_layout(layout):
    if not isinstance(layout,dict) or set(layout)-{'background','elements'}: raise ValueError('Invalid welcome layout.')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(layout.get('background',''))): raise ValueError('Use a hex background color.')
    elements=layout.get('elements')
    if not isinstance(elements,list) or not 1<=len(elements)<=12: raise ValueError('Use 1–12 welcome elements.')
    for e in elements:
        if not isinstance(e,dict) or set(e)-{'type','x','y','size','color','value'} or e.get('type') not in {'avatar','header','server','message','brand','text'}: raise ValueError('Unsupported welcome element.')
        for key,low,high in [('x',0,899),('y',0,259),('size',24 if e['type']=='avatar' else 10,220 if e['type']=='avatar' else 64)]:
            if type(e.get(key)) is not int or not low<=e[key]<=high: raise ValueError('Element coordinates or size are outside the card.')
        if e['type']=='avatar' and (e['x']+e['size']>900 or e['y']+e['size']>260): raise ValueError('Avatar must fit on the card.')
        if not isinstance(e.get('value',''),str) or len(e.get('value',''))>200 or not re.fullmatch(r'#[0-9a-fA-F]{6}',str(e.get('color',''))): raise ValueError('Invalid element text or color.')
    return layout

def render_layout(layout,name,server,message,avatar=None,greeting=None,brand='Vivi'):
    validate_layout(layout); image=Image.new('RGB',(900,260),layout['background']); draw=ImageDraw.Draw(image)
    values=dict(header=greeting or f'Welcome, {name[:30]}!',server=server[:60],message=message[:160],brand=brand[:60])
    for e in layout['elements']:
        if e['type']=='avatar':
            size=e['size']; mask=Image.new('L',(size,size)); ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
            picture=Image.new('RGB',(size,size),e['color'])
            if avatar:
                with Image.open(io.BytesIO(avatar)) as source: picture=source.convert('RGB').resize((size,size))
            image.paste(picture,(e['x'],e['y']),mask)
        else:
            text=e.get('value','') if e['type']=='text' else values[e['type']]
            width=max(1,(900-e['x'])//max(6,e['size']//2)); lines=[text[n:n+width] for n in range(0,len(text),width)]
            draw.multiline_text((e['x'],e['y']),'\n'.join(lines[:4]),font=ImageFont.load_default(size=e['size']),fill=e['color'],spacing=3)
    out=io.BytesIO(); image.save(out,format='PNG'); return out.getvalue()

def validate_announcement(blocks):
    if not isinstance(blocks,list) or not 1<=len(blocks)<=12: raise ValueError('Use 1–12 announcement blocks.')
    total=0; titles=0
    for block in blocks:
        if not isinstance(block,dict) or set(block)-{'type','name','value'} or block.get('type') not in {'title','text','field','divider'}: raise ValueError('Unsupported announcement block.')
        name=block.get('name',''); value=block.get('value','')
        if not isinstance(name,str) or not isinstance(value,str) or len(name)>256 or len(value)>(1024 if block['type']=='field' else 256 if block['type']=='title' else 1500): raise ValueError('Announcement field is too long.')
        if block['type']=='title': titles+=1
        if block['type']!='divider' and not value.strip(): raise ValueError('Text blocks cannot be empty.')
        if block['type']=='field' and not name.strip(): raise ValueError('Give fields a name.')
        total+=len(name)+len(value)
    if titles>1 or total>4000: raise ValueError('Use one title and at most 4,000 total characters.')
    if any(b['type']=='title' and n!=0 for n,b in enumerate(blocks)): raise ValueError('The announcement title must be the first block.')
    if sum(len(b.get('value',''))+len(b.get('name',''))+8 for b in blocks)>4096: raise ValueError('The formatted announcement exceeds Discord’s description limit.')
    return blocks

def announcement_embed(blocks):
    import discord
    validate_announcement(blocks); embed=discord.Embed(color=0xB980FF); description=[]
    for b in blocks:
        if b['type']=='title': embed.title=b['value']
        elif b['type']=='text': description.append(b['value'])
        elif b['type']=='divider': description.append('──────────')
        else: description.append('**'+discord.utils.escape_markdown(b['name'])+'**\n'+b['value'])
    if description: embed.description='\n\n'.join(description)
    return embed
