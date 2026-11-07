"""Live, private profile drafts. Existing profile renderers and validation stay authoritative."""
import asyncio
import copy
import io
import discord
from vivi.bot import reply
from vivi.core.features import enabled
from vivi.server.guild_library import clean_text
from vivi.server.profiles import BACKGROUNDS,GRADIENTS,FONTS,LAYOUTS,STICKERS,validate_style,render_profile
from vivi.server.action_menus import OwnedView

class TextEditor(discord.ui.Modal):
    def __init__(self,editor,kind):
        super().__init__(title='Profile status' if kind=='status' else 'Custom gradient');self.editor=editor;self.kind=kind
        self.input=discord.ui.TextInput(label='Status (blank clears it)' if kind=='status' else 'Two colors: #RRGGBB,#RRGGBB',required=kind!='status',max_length=120 if kind=='status' else 15,default=editor.draft['status'] if kind=='status' else '#bb99ee,#ffb6cc')
        self.add_item(self.input)
    async def on_submit(self,i):
        if not await self.editor.interaction_check(i):return
        value=str(self.input)
        def change(style):style['status' if self.kind=='status' else 'gradient']=value
        await self.editor.update(i,change=change)

class ProfileEditor(OwnedView):
    def __init__(self,bot,i):
        super().__init__(i.user.id,i.guild_id);self.bot=bot;self.cards=bot.community.profiles;self.baseline=copy.deepcopy(self.cards.style(self.guild,self.owner));self.draft=copy.deepcopy(self.baseline)
        self.property='background';self.lock=asyncio.Lock();self.avatar=None;self.avatar_loaded=False
    def options(self):
        if self.property=='background':
            values=list(BACKGROUNDS)
            values += ['upload:'+row['id'] for row in self.bot.store.records(self.guild,'profile_banner') if row['data']['user']==self.owner and row['data']['status']=='approved']
            return values[:25]
        if self.property=='gradient':return list(GRADIENTS)+([self.draft['gradient']] if self.draft['gradient'] not in GRADIENTS else [])+['custom']
        return list({'font':FONTS,'layout':LAYOUTS,'stickers':STICKERS}[self.property])
    def controls(self):
        self.clear_items()
        selector=discord.ui.Select(placeholder='Choose what to edit',row=0,options=[discord.SelectOption(label=name.title(),value=name,default=self.property==name) for name in ['background','gradient','font','layout','stickers']])
        async def property_pick(i):
            value=i.data['values'][0]
            if value not in {'background','gradient','font','layout','stickers'}:return await reply(i,'Choose a supported profile property.')
            await self.update(i,property=value)
        selector.callback=property_pick;self.add_item(selector)
        values=discord.ui.Select(placeholder='Choose '+self.property,row=1,options=[discord.SelectOption(label=('Custom colors…' if value=='custom' else 'Approved upload '+value[7:15] if value.startswith('upload:') else value.replace('_',' ').title())[:100],value=value,default=self.property!='stickers' and value==self.draft.get(self.property)) for value in self.options()])
        async def pick(i,key=self.property,options=set(self.options())):
            if key!=self.property:return await reply(i,'This selection changed. Use the current dropdown.')
            value=i.data['values'][0]
            if value not in options:return await reply(i,'Choose a supported appearance option.')
            if value=='custom':return await i.response.send_modal(TextEditor(self,'gradient'))
            def change(style):
                if key=='stickers':
                    if len(style['stickers'])>=6:raise ValueError('Maximum six stickers. Clear them or use the Sticker action for precise removal.')
                    style['stickers'].append(dict(item=value,x=800,y=35+len(style['stickers'])*35))
                else:style[key]=value
            await self.update(i,change=change)
        values.callback=pick;self.add_item(values)
        for label,action in [('Edit status','status'),('Clear stickers','stickers'),('Save changes','save'),('Revert draft','revert'),('Close without saving' if self.draft!=self.baseline else 'Close','close')]:
            button=discord.ui.Button(label=label,row=2,style=discord.ButtonStyle.success if action=='save' else discord.ButtonStyle.secondary,disabled=action=='save' and self.draft==self.baseline)
            async def click(i,value=action):
                if value=='status':return await i.response.send_modal(TextEditor(self,'status'))
                if value=='close':
                    self.stop();return await i.response.edit_message(content='Profile editor closed. Unsaved draft changes were discarded.',embed=None,attachments=[],view=None)
                def change(style):style['stickers']=[]
                await self.update(i,change=change if value=='stickers' else None,save=value=='save',revert=value=='revert')
            button.callback=click;self.add_item(button)
    async def update(self,i,change=None,save=False,revert=False,property=None,initial=False):
        if not await self.bot.community.need(i,'profiles'):return
        await i.response.defer(ephemeral=True,thinking=initial)
        async with self.lock:
            if self.is_finished():return await i.followup.send('This editor is closed. Open /profile again.',ephemeral=True)
            if property:self.property=property
            working=copy.deepcopy(self.draft)
            if revert:self.baseline=copy.deepcopy(self.cards.style(self.guild,self.owner));working=copy.deepcopy(self.baseline)
            try:
                if change:change(working)
                validate_style(working);clean_text(self.bot.store,self.guild,working['status']);banner=self.cards.banner(self.guild,self.owner,working,bool(change or save))
                if save:
                    if self.cards.style(self.guild,self.owner)!=self.baseline:raise ValueError('Your saved style changed in another menu. Revert the draft to load it before saving.')
                    p=self.bot.store.profile(self.guild,self.owner);p['card_style']=copy.deepcopy(working);self.bot.store.save_profile(self.guild,self.owner,p);self.baseline=copy.deepcopy(working)
            except ValueError as error:return await i.followup.send(str(error),ephemeral=True)
            self.draft=working
            p=self.bot.store.profile(self.guild,self.owner)
            if not self.avatar_loaded:
                self.avatar_loaded=True
                if p.get('card_visibility',{}).get('avatar',True):
                    try:self.avatar=await i.user.display_avatar.with_size(128).with_format('png').read()
                    except (discord.HTTPException,AttributeError):pass
            showcase=self.cards.showcases(self.guild,self.owner,p,working)
            body=await asyncio.to_thread(render_profile,i.user.display_name,p,copy.deepcopy(working),self.avatar,banner,showcase)
            if self.is_finished():return
            if not enabled(self.bot.store,self.guild,'profiles'):return await i.followup.send('Profile editing was disabled while the preview was rendering.',ephemeral=True)
            self.controls();dirty=self.draft!=self.baseline
            card=discord.Embed(title='Vivi · Live profile editor',description=('**Unsaved draft** — choose Save changes to keep this appearance.' if dirty else 'This preview matches your saved appearance.')+f"\nBackground: {working['background']} · Font: {working['font']} · Layout: {working['layout']}",color=0xff65ad)
            card.set_image(url='attachment://profile-preview.png');card.set_footer(text='Private preview · field visibility is respected · drafts expire after 15 minutes idle')
            file=discord.File(io.BytesIO(body),filename='profile-preview.png',description=f"Private profile preview with {working['layout']} layout, {working['font']} font and {len(working['stickers'])} stickers.")
            if initial:
                self.message=await i.followup.send(embed=card,file=file,view=self,ephemeral=True,wait=True,allowed_mentions=discord.AllowedMentions.none())
            else:await i.edit_original_response(embed=card,attachments=[file],view=self)

async def open_editor(bot,i):
    if not i.guild_id:return await reply(i,'Open the profile editor inside a server.')
    view=ProfileEditor(bot,i);await view.update(i,initial=True)
