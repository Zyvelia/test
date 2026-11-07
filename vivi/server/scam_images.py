"""Guild-scoped reference-image hashes. No OCR, external image URLs or cloud classification."""
import asyncio
import hashlib
import io
import secrets
import time
import warnings
from collections import OrderedDict
import discord
from discord import app_commands
from PIL import Image,ImageOps,ImageStat
from vivi.bot import reply
from vivi.core.features import enabled

MAX_BYTES=4*1024*1024
MAX_PIXELS=8_000_000
MAX_REFERENCES=100

def fingerprint(body):
    if len(body)>MAX_BYTES:raise ValueError('Use a static PNG, JPEG or WebP image no larger than 4 MiB.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(body)) as original:
            if original.format not in {'PNG','JPEG','WEBP'} or getattr(original,'is_animated',False) or original.width*original.height>MAX_PIXELS:
                raise ValueError('Use a static PNG, JPEG or WebP up to eight million pixels.')
            picture=ImageOps.exif_transpose(original).convert('RGBA')
            base=Image.new('RGBA',picture.size,'white');base.alpha_composite(picture);rgb=base.convert('RGB')
            gray=rgb.convert('L').resize((9,8),Image.Resampling.LANCZOS);pixels=list(gray.getdata());bits=0
            for r in range(8):
                for c in range(8):bits=(bits<<1)|int(pixels[r*9+c]>pixels[r*9+c+1])
            return dict(sha256=hashlib.sha256(body).hexdigest(),pixels=hashlib.sha256(rgb.width.to_bytes(4,'big')+rgb.height.to_bytes(4,'big')+rgb.tobytes()).hexdigest(),dhash=f'{bits:016x}',width=rgb.width,height=rgb.height,contrast=ImageStat.Stat(rgb.convert('L').resize((64,64))).stddev[0])

def compare(candidate,reference,distance=0):
    if candidate['sha256']==reference['sha256']:return 'exact file'
    if candidate['pixels']==reference['pixels']:return 'exact pixels'
    if distance and candidate['contrast']>=20 and reference['contrast']>=20:
        ratio=(candidate['width']/candidate['height'])/(reference['width']/reference['height'])
        difference=(int(candidate['dhash'],16)^int(reference['dhash'],16)).bit_count()
        if .95<=ratio<=1.05 and difference<=distance:return f'similar image ({difference}/64 bits differ)'
    return None

class ScamImages:
    def __init__(self,service):self.service=service;self.store=service.store;self.slots=asyncio.Semaphore(2);self.deleted=OrderedDict();self.audit_last={}
    def references(self,guild):return self.store.records(guild,'scam_image')
    async def add(self,guild,actor,attachment,label):
        if attachment.size>MAX_BYTES:raise ValueError('Reference images must be no larger than 4 MiB.')
        if len(self.references(guild))>=MAX_REFERENCES:raise ValueError('Maximum 100 references per server. Remove an old reference first.')
        async with self.slots:
            body=await asyncio.wait_for(attachment.read(),15)
            try:result=await asyncio.to_thread(fingerprint,body)
            except (OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as error:raise ValueError('Use a valid static PNG, JPEG or WebP within the image limits.') from error
        for row in self.references(guild):
            if row['data']['pixels']==result['pixels']:return row['id'],row['data'],False
        if len(self.references(guild))>=MAX_REFERENCES:raise ValueError('Reference limit reached while processing this image.')
        result.update(label=label,actor=actor,created=time.time());ident=secrets.token_hex(8)
        self.store.put_record(guild,'scam_image',result,ident);return ident,result,True
    def remove(self,guild,ident):
        row=self.store.record(ident)
        if not row or row['guild']!=guild or row['kind']!='scam_image':raise ValueError('Reference not found in this server.')
        self.store.delete_record(ident)
    async def inspect(self,message):
        guild=message.guild
        if not enabled(self.store,guild.id,'scam_images') or message.author.guild_permissions.manage_messages:return False
        message_key=(guild.id,message.id)
        if message_key in self.deleted:return True
        refs=self.references(guild.id)
        if not refs:return False
        found=None
        for attachment in getattr(message,'attachments',[])[:10]:
            if attachment.size>MAX_BYTES:continue
            if not ((attachment.content_type or '').startswith('image/') or attachment.filename.lower().endswith(('.png','.jpg','.jpeg','.webp'))):continue
            try:
                async with self.slots:
                    body=await asyncio.wait_for(attachment.read(),15)
                    if len(body)>MAX_BYTES:continue
                    exact=next((r for r in refs if r['data']['sha256']==hashlib.sha256(body).hexdigest()),None)
                    if exact:found=(exact,'exact file')
                    else:
                        image=await asyncio.to_thread(fingerprint,body)
                        distance=self.store.option(guild.id,'scam_image_distance',0)
                        for row in refs:
                            match=compare(image,row['data'],distance)
                            if match:found=(row,match);break
                if found:break
            except (discord.HTTPException,asyncio.TimeoutError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):continue
        if not found:return False
        # Recheck the switch and reference after attachment I/O; removing a reference cancels pending matches.
        reference=self.store.record(found[0]['id'])
        if not enabled(self.store,guild.id,'scam_images') or not reference or reference['guild']!=guild.id or reference['kind']!='scam_image':return False
        if found[1].startswith('similar') and not compare(image,reference['data'],self.store.option(guild.id,'scam_image_distance',0)):return False
        if message_key in self.deleted:return True
        self.deleted[message_key]=time.time()
        while len(self.deleted)>2048:self.deleted.popitem(last=False)
        action='scam image deleted'
        try:await message.delete()
        except discord.NotFound:return True
        except discord.HTTPException as error:
            self.deleted.pop(message_key,None);self.service.productivity.error('scam image deletion',error)
            action='scam image detected (delete failed)'
        now=time.time();key=(guild.id,message.author.id)
        self.audit_last={k:v for k,v in self.audit_last.items() if now-v<60}
        if now-self.audit_last.get(key,0)>=30:
            self.audit_last[key]=now
            await self.service.case(guild,message.author.id,self.service.bot.user.id,action,f'Reference {reference["id"]}; {found[1]}; message {message.id}; channel {message.channel.id}.',message.author)
        return True


def actions(bot):
    service=bot.community.scam_images
    async def admin(i):
        if not i.user.guild_permissions.administrator:raise app_commands.MissingPermissions(['administrator'])
        return True
    def command(name,description):
        def decorate(callback):
            result=app_commands.Command(name=name,description=description,callback=callback);result.default_permissions=discord.Permissions(administrator=True);result.checks.append(admin);return result
        return decorate
    @command('scam_image_add','Upload a known scam image; save its file and pixel hashes as a server reference.')
    async def add(i:discord.Interaction,image:discord.Attachment,label:app_commands.Range[str,1,100]):
        await i.response.defer(ephemeral=True)
        try:ident,data,created=await service.add(i.guild_id,i.user.id,image,label)
        except (ValueError,asyncio.TimeoutError,discord.HTTPException) as error:return await reply(i,str(error) or 'Could not read the image.')
        await reply(i,f'{"Saved" if created else "Already saved"}: `{ident}`\nImage code (SHA-256): `{data["sha256"]}`\nEnable Scam Images in /settings → Features to delete matching member attachments. Exact matching is the default. Original images are not retained.')
    @command('scam_image_list','List saved scam-image reference IDs and SHA-256 codes for this server.')
    async def listing(i:discord.Interaction,page:app_commands.Range[int,1,20]=1):
        rows=service.references(i.guild_id);selected=rows[(page-1)*8:page*8]
        await reply(i,'\n'.join(f'`{r["id"]}` · {discord.utils.escape_markdown(r["data"]["label"])[:80]}\nSHA-256: `{r["data"]["sha256"]}`' for r in selected) or 'No references on this page.')
    @command('scam_image_remove','Remove one saved image reference by its ID; other servers are unaffected.')
    async def remove(i:discord.Interaction,reference_id:str):
        try:service.remove(i.guild_id,reference_id)
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Scam-image reference removed.')
    return {c.name:c for c in [add,listing,remove]}
