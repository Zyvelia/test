"""One administrator menu for saved embeds; uses the same library as the dashboard."""
import contextlib
import discord
from discord import app_commands
from .action_menus import OwnedView
from .bot import reply
from . import embed_writer as writer

class StaffView(OwnedView):
    async def interaction_check(self,i):
        if not await super().interaction_check(i):return False
        if not i.guild or not i.user.guild_permissions.administrator:
            await reply(i,'Administrator permission is required.');return False
        return True

class DraftForm(discord.ui.Modal):
    def __init__(self,view):
        super().__init__(title='Edit saved embed' if view.ident else 'Create saved embed');self.view=view;self.ident=view.ident
        data=writer.load(view.store,view.guild,view.ident)['data']['document'] if view.ident else {}
        self.data=data;self.inputs={}
        for key,label,maximum in [('name','Template name',80),('title','Embed title',256),('description','Message text (Discord markdown)',4000),('color','Accent color (#ff65ad)',7),('footer','Footer',2048)]:
            control=discord.ui.TextInput(label=label,default=data.get(key,'#ff65ad' if key=='color' else '')[:maximum],required=key in {'name','color'},max_length=maximum,style=discord.TextStyle.paragraph if key=='description' else discord.TextStyle.short)
            self.inputs[key]=control;self.add_item(control)
    async def on_submit(self,i):
        if not await self.view.interaction_check(i):return
        data={**self.data,**{key:str(control) for key,control in self.inputs.items()}}
        try:ident=writer.save(self.view.store,i.guild_id,data,i.user.id,self.ident)
        except ValueError as error:return await reply(i,str(error))
        await reply(i,'Template saved. Open /embed to preview or post it. Images and fields can be edited in the dashboard.')

class PostView(StaffView):
    def __init__(self,i,document):
        super().__init__(i.user.id,i.guild_id);self.document=document;self.channel=None;self.used=False
        selector=discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text],placeholder='Choose destination channel')
        async def selected(i):
            if not await self.interaction_check(i):return
            self.channel=selector.values[0].id;await reply(i,f'Selected <#{self.channel}>. Press Confirm post when ready.')
        selector.callback=selected;self.add_item(selector)
        button=discord.ui.Button(label='Confirm post',style=discord.ButtonStyle.success)
        async def post(i):
            if not await self.interaction_check(i):return
            if self.used:return await reply(i,'This posting confirmation was already used.')
            if not self.channel:return await reply(i,'Choose a destination channel first.')
            self.used=True;await i.response.defer(ephemeral=True,thinking=True)
            try:message=await writer.publish(i.guild,self.channel,self.document,i.user.id)
            except (ValueError,PermissionError,discord.HTTPException) as error:
                self.used=False;return await i.followup.send(f'Could not post the embed: {error}',ephemeral=True)
            self.stop();await i.followup.send(f'Embed posted: {message.jump_url}',ephemeral=True)
        button.callback=post;self.add_item(button)

class DeleteView(StaffView):
    def __init__(self,i,store,ident):
        super().__init__(i.user.id,i.guild_id);self.used=False
        button=discord.ui.Button(label='Confirm deletion',style=discord.ButtonStyle.danger)
        async def delete(i):
            if not await self.interaction_check(i):return
            if self.used:return await reply(i,'This confirmation was already used.')
            try:writer.load(store,i.guild_id,ident)
            except ValueError as error:return await reply(i,str(error))
            self.used=True;store.delete_record(ident);self.stop();await i.response.edit_message(content='Saved template deleted. Posted messages remain.',view=None)
        button.callback=delete;self.add_item(button)

class EmbedMenu(StaffView):
    def __init__(self,store,i,page=0,ident=''):
        super().__init__(i.user.id,i.guild_id);self.store=store;self.ident=ident;rows=store.records(i.guild_id,writer.KIND);self.page=max(0,min(page,max(0,(len(rows)-1)//20)))
        if rows:
            select=discord.ui.Select(placeholder=f'Saved embeds · page {self.page+1}',options=[discord.SelectOption(label=row['data']['document']['name'],value=row['id'],default=row['id']==ident) for row in rows[self.page*20:self.page*20+20]])
            async def selected(i):
                if not await self.interaction_check(i):return
                self.ident=select.values[0];await reply(i,'Template selected. Choose Preview, Edit, Post or Delete.')
            select.callback=selected;self.add_item(select)
        for label,action in [('New embed','new'),('Preview','preview'),('Edit','edit'),('Post','post'),('Delete','delete')]:
            button=discord.ui.Button(label=label)
            async def click(i,action=action):
                if not await self.interaction_check(i):return
                if action=='new':
                    fresh=EmbedMenu(store,i);return await i.response.send_modal(DraftForm(fresh))
                try:document=writer.load(store,i.guild_id,self.ident)['data']['document']
                except ValueError:return await reply(i,'Select an existing template first, or create a new embed.')
                if action=='edit':
                    if len(document.get('description',''))>4000:return await reply(i,'This long description needs the dashboard editor; Discord modal text boxes allow 4,000 characters.')
                    return await i.response.send_modal(DraftForm(self))
                if action=='preview':return await i.response.send_message(embed=writer.render(document),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
                if action=='post':return await i.response.send_message(content='Review this embed, select a destination, then confirm posting.',embed=writer.render(document),view=PostView(i,document),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
                await i.response.send_message('Delete this saved template? Posted Discord messages stay.',view=DeleteView(i,store,self.ident),ephemeral=True)
            button.callback=click;self.add_item(button)
        for label,delta in [('Previous',-1),('Next',1)]:
            button=discord.ui.Button(label=label,disabled=self.page+delta<0 or (self.page+delta)*20>=len(rows))
            async def move(i,delta=delta):
                if not await self.interaction_check(i):return
                view=EmbedMenu(store,i,self.page+delta);await i.response.edit_message(view=view)
            button.callback=move;self.add_item(button)

def register_embeds(bot):
    @bot.tree.command(name='embed',description='Write, save, preview and post reusable embeds such as rules and announcements.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def embed(i:discord.Interaction):
        if not i.user.guild_permissions.administrator:return await reply(i,'Administrator permission is required.')
        view=EmbedMenu(bot.community.store,i)
        await i.response.send_message('Vivi · Embed library\nCreate a template or choose a saved embed. The dashboard embed writer also supports images, links and fields.',view=view,ephemeral=True)
        with contextlib.suppress(discord.HTTPException):view.message=await i.original_response()
