"""Owner-bound feature menus using the existing validated command handlers."""
import contextlib
import math
import os
from types import SimpleNamespace
from urllib.parse import urlsplit,urlunsplit
import discord
from discord import app_commands
from .bot import reply
from .help_menu import visible

PAGE=20
TITLES={'community':'Community','ticket':'Tickets & support','profile':'Your profile','settings':'Server settings'}
STAFF_COMMUNITY={'poll','poll_close','giveaway','giveaway_reroll','suggestion_decide','spotlight'}
PUBLIC_ACTIONS={'rules','role_menu','poll','poll_close','giveaway','giveaway_reroll','suggest','suggestion_decide','spotlight','lfg'}

class Invocation:
    """Give existing checks the selected action, while preserving Discord's response API."""
    def __init__(self,interaction,command,values):self.original=interaction;self.command=command;self.namespace=SimpleNamespace(**values)
    def __getattr__(self,key):return getattr(self.original,key)


def allowed(bot,command,i):
    if not visible(command,i):return False
    root=command.qualified_name.split()[0];name=command.name;permissions=i.user.guild_permissions
    if root=='community':
        if name in {'rules','role_menu'} and not permissions.administrator:return False
        if name in STAFF_COMMUNITY and not (permissions.administrator or permissions.manage_messages):return False
    if root=='ticket' and name!='status' and not bot.community.operations.staff(i):return False
    if root=='support' and name in {'tags','availability'} and not bot.community.operations.staff(i):return False
    return True

async def invoke(bot,command,i,values):
    if not allowed(bot,command,i):return await reply(i,'Your current permissions do not allow this action.')
    proxy=Invocation(i,command,values)
    try:
        if not await command._check_can_run(proxy):return await reply(i,'The action check denied this request.')
        if command.binding is None:return await command.callback(proxy,**values)
        return await command.callback(command.binding,proxy,**values)
    except app_commands.AppCommandError as error:return await reply(i,str(error))
    except (ValueError,TypeError) as error:return await reply(i,str(error))
    except discord.HTTPException:return await reply(i,'Discord could not complete this action. Check the bot’s permissions and try again.')


def scalar(parameter,value):
    typ=parameter.type
    if typ==discord.AppCommandOptionType.integer:
        if isinstance(value,bool):raise ValueError('Enter a whole number, not a boolean.')
        try:value=int(value)
        except (TypeError,ValueError):raise ValueError(f'{parameter.name}: enter a whole number.') from None
        if isinstance(value,bool) or abs(value)>2**53:raise ValueError('Integer is outside Discord’s supported range.')
    elif typ==discord.AppCommandOptionType.number:
        try:value=float(value)
        except (TypeError,ValueError):raise ValueError(f'{parameter.name}: enter a number.') from None
        if not math.isfinite(value):raise ValueError('Use a finite number.')
    elif typ==discord.AppCommandOptionType.boolean:
        if isinstance(value,str):
            if value not in {'true','false'}:raise ValueError('Choose true or false.')
            value=value=='true'
        elif not isinstance(value,bool):raise ValueError('Choose true or false.')
    elif typ==discord.AppCommandOptionType.string:value=str(value)
    measure=len(value) if typ==discord.AppCommandOptionType.string else value
    if typ in {discord.AppCommandOptionType.string,discord.AppCommandOptionType.integer,discord.AppCommandOptionType.number}:
        if parameter.min_value is not None and measure<parameter.min_value:raise ValueError(f'{parameter.name}: minimum {parameter.min_value}.')
        if parameter.max_value is not None and measure>parameter.max_value:raise ValueError(f'{parameter.name}: maximum {parameter.max_value}.')
    if parameter.choices and value not in [choice.value for choice in parameter.choices]:raise ValueError(f'{parameter.name}: choose one of the listed values.')
    return value

class OwnedView(discord.ui.View):
    def __init__(self,owner,guild):super().__init__(timeout=900);self.owner=owner;self.guild=guild;self.message=None
    async def interaction_check(self,i):
        if i.user.id!=self.owner or i.guild_id!=self.guild or self.is_finished():
            await reply(i,'This menu is not yours or has expired. Open a new menu.');return False
        return True
    async def on_error(self,i,error,item):await reply(i,'This menu action could not be completed. Open a new menu and try again.')
    async def on_timeout(self):
        for child in self.children:child.disabled=True
        if self.message:
            with contextlib.suppress(discord.HTTPException):await self.message.edit(view=self)

class ActionFlow:
    def __init__(self,menu,command):self.menu=menu;self.command=command;self.values={};self.cursor=0;self.used=False
    async def check(self,i):
        if not await self.menu.interaction_check(i):return False
        if self.menu.flow is not self or self.used:
            await reply(i,'This action was replaced or already submitted. Choose it again from the menu.');return False
        if not allowed(self.menu.bot,self.command,i):
            await reply(i,'Your permissions changed. Open the menu again.');return False
        return True
    @property
    def parameters(self):return self.command.parameters
    async def begin(self,i):
        if not await self.check(i):return
        if self.parameters:return await i.response.send_modal(ActionForm(self))
        await self.review(i)
    async def review(self,i):
        embed=discord.Embed(title='Review · '+self.command.name.replace('_',' ').title(),description=self.command.description,color=0xff65ad)
        for parameter in self.parameters[:20]:
            value=self.values.get(parameter.name,parameter.default)
            text=getattr(value,'mention',None) or getattr(value,'filename',None) or str(value)
            embed.add_field(name=parameter.name.replace('_',' '),value=(discord.utils.escape_markdown(str(text))[:200] or '(empty)'),inline=False)
        if self.command.name in PUBLIC_ACTIONS:embed.add_field(name='Public action',value='Confirmation may publish a message in the selected or current channel.',inline=False)
        embed.set_footer(text='Nothing is submitted until you confirm. Permissions are checked again.')
        view=FlowView(self)
        await i.response.send_message(embed=embed,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        with contextlib.suppress(discord.HTTPException):view.message=await i.original_response()

class ActionForm(discord.ui.Modal):
    def __init__(self,flow):
        super().__init__(title=(flow.command.name.replace('_',' ').title()+f' · step {flow.cursor//5+1}')[:45],timeout=900)
        self.flow=flow;self.start=flow.cursor;self.inputs=[];self.used=False
        for parameter in flow.parameters[self.start:self.start+5]:
            typ=parameter.type;default=flow.values.get(parameter.name,parameter.default);required=parameter.required
            if default is discord.utils.MISSING:default=None
            common=dict(required=required,min_values=1 if required else 0,max_values=1)
            if typ==discord.AppCommandOptionType.attachment:control=discord.ui.FileUpload(**common)
            elif typ==discord.AppCommandOptionType.user:control=discord.ui.UserSelect(**common)
            elif typ==discord.AppCommandOptionType.role:control=discord.ui.RoleSelect(**common)
            elif typ==discord.AppCommandOptionType.channel:control=discord.ui.ChannelSelect(channel_types=parameter.channel_types,**common)
            elif parameter.choices or typ==discord.AppCommandOptionType.boolean:
                choices=parameter.choices or [app_commands.Choice(name='Yes / On',value='true'),app_commands.Choice(name='No / Off',value='false')]
                current=str(default).lower() if typ==discord.AppCommandOptionType.boolean else str(default)
                control=discord.ui.Select(options=[discord.SelectOption(label=choice.name[:100],value=str(choice.value),default=str(choice.value)==current) for choice in choices],**common)
            else:
                text='' if default is None else str(default)
                maximum=min(4000,int(parameter.max_value or 4000)) if typ==discord.AppCommandOptionType.string else 100
                control=discord.ui.TextInput(default=text[:maximum],required=required,max_length=maximum,style=discord.TextStyle.paragraph if maximum>200 and typ==discord.AppCommandOptionType.string else discord.TextStyle.short)
            description=parameter.description if parameter.description!='…' else 'Leave optional fields empty to keep their default.'
            self.add_item(discord.ui.Label(text=(parameter.name.replace('_',' ').title()+(' *' if required else ' (optional)'))[:45],description=description[:100],component=control))
            self.inputs.append((parameter,control))
    async def on_submit(self,i):
        if not await self.flow.check(i):return
        if self.used or self.flow.cursor!=self.start:return await reply(i,'This form step has already been submitted.')
        try:
            values={}
            for parameter,control in self.inputs:
                raw=str(control) if isinstance(control,discord.ui.TextInput) else control.values[0] if control.values else None
                if raw is None or isinstance(raw,str) and not raw.strip():
                    if parameter.required:raise ValueError(f'{parameter.name} is required.')
                    values[parameter.name]=parameter.default;continue
                if parameter.type in {discord.AppCommandOptionType.channel,discord.AppCommandOptionType.user,discord.AppCommandOptionType.role}:
                    # Discord resolves native selectors; retain its typed transforms and guild checks.
                    if getattr(raw,'guild_id',i.guild_id)!=i.guild_id or getattr(getattr(raw,'guild',None),'id',i.guild_id)!=i.guild_id:raise ValueError('Choose an item from this server.')
                else:raw=scalar(parameter,raw)
                values[parameter.name]=await self.flow.command._params[parameter.name].transform(Invocation(i,self.flow.command,values),raw)
            self.flow.values.update(values)
        except (ValueError,app_commands.AppCommandError) as error:
            return await i.response.send_message(str(error)[:1800],view=FlowView(self.flow,retry=True),ephemeral=True)
        self.used=True;self.flow.cursor=self.start+len(self.inputs)
        if self.flow.cursor<len(self.flow.parameters):
            return await i.response.send_message('Step saved. Continue to the remaining options; nothing has run yet.',view=FlowView(self.flow,retry=True),ephemeral=True)
        await self.flow.review(i)
    async def on_error(self,i,error):await reply(i,'The form could not be processed. Open the menu and try again.')

class FlowView(OwnedView):
    def __init__(self,flow,retry=False):
        super().__init__(flow.menu.owner,flow.menu.guild);self.flow=flow
        button=discord.ui.Button(label='Continue form' if retry else 'Confirm action',style=discord.ButtonStyle.primary)
        async def submit(i):
            if not await flow.check(i):return
            if retry:
                if flow.cursor>=len(flow.parameters):return await reply(i,'The form is complete. Use its latest confirmation, or choose the action again.')
                return await i.response.send_modal(ActionForm(flow))
            flow.used=True
            await invoke(flow.menu.bot,flow.command,i,dict(flow.values))
            if self.message:
                with contextlib.suppress(discord.HTTPException):await self.message.edit(view=None)
            self.stop()
        button.callback=submit;self.add_item(button)
        cancel=discord.ui.Button(label='Cancel')
        async def cancel_action(i):
            if not await flow.check(i):return
            flow.used=True;self.stop();await i.response.edit_message(content='Action cancelled.',embed=None,view=None)
        cancel.callback=cancel_action;self.add_item(cancel)
    async def interaction_check(self,i):return await super().interaction_check(i) and await self.flow.menu.interaction_check(i)

class ActionMenu(OwnedView):
    def __init__(self,bot,kind,i):
        super().__init__(i.user.id,i.guild_id);self.bot=bot;self.kind=kind;self.guild_object=i.guild;self.page=0;self.selected=None;self.flow=None;self.actions=self.build_actions()
    def build_actions(self):
        group=self.bot.menu_groups[self.kind] if self.kind!='settings' else self.bot.tree.get_command('admin')
        result={c.qualified_name:c for c in group.walk_commands() if isinstance(c,app_commands.Command)}
        extras={'community':['social'],'ticket':['support'],'profile':[],'settings':[]}[self.kind]
        for root in extras:
            parent=self.bot.tree.get_command(root)
            if parent:result.update({c.qualified_name:c for c in parent.walk_commands() if isinstance(c,app_commands.Command)})
        if self.kind=='settings':
            from .scam_images import actions
            result.update(actions(self.bot))
            result.pop('admin feature',None);result.pop('admin features',None);result.pop('admin setting',None)
            result['setup']=self.bot.tree.get_command('setup')
        if self.kind=='profile':
            async def live_editor(i:discord.Interaction):
                from .profile_editor import open_editor
                await open_editor(self.bot,i)
            result['profile live_editor']=app_commands.Command(name='live_editor',description='Edit a private draft with a live preview after every appearance change.',callback=live_editor)
        if self.kind=='ticket':
            async def create(i:discord.Interaction):
                from .bot import OpenTicketView
                await OpenTicketView(self.bot).open_ticket.callback(i)
            async def close(i:discord.Interaction):
                from .bot import CloseTicketView
                await CloseTicketView(self.bot).close_ticket.callback(i)
            result['ticket open']=app_commands.Command(name='open',description='Open a private support ticket, choosing a category when configured.',callback=create)
            result['ticket close']=app_commands.Command(name='close',description='Request a transcript and close this ticket after a separate confirmation.',callback=close)
        return result
    async def interaction_check(self,i):
        if not await super().interaction_check(i):return False
        if self.kind=='settings' and not i.user.guild_permissions.administrator:
            await reply(i,'Administrator permission is required.');return False
        return True
    def draw(self,i):
        self.clear_items();items=[(key,c) for key,c in self.actions.items() if allowed(self.bot,c,i)]
        last=max(0,(len(items)-1)//PAGE);self.page=min(max(self.page,0),last);items=items[self.page*PAGE:(self.page+1)*PAGE]
        embed=discord.Embed(title='Vivi · '+TITLES[self.kind],description='Choose an action. Forms and confirmations stay private; public posts happen only after you confirm.',color=0xff65ad)
        if self.kind=='profile':
            p=self.bot.store.profile(i.guild_id,i.user.id);style=self.bot.community.profiles.style(i.guild_id,i.user.id)
            embed.add_field(name='Your current profile',value=f"Background: {style['background']}\nLayout: {style['layout']}\nProfile: {'public' if p['visible'] else 'private'}",inline=False)
        if self.kind=='ticket':embed.add_field(name='Ticket controls',value='Open a ticket here. Status, staff tools and close actions operate on the ticket channel you opened this menu in.',inline=False)
        if self.selected in self.actions:
            command=self.actions[self.selected]
            if allowed(self.bot,command,i):embed.add_field(name=command.name.replace('_',' ').title(),value=command.description,inline=False)
        if items:
            select=discord.ui.Select(placeholder='Choose an action',options=[discord.SelectOption(label=c.name.replace('_',' ').title()[:100],value=key,description=c.description[:100],default=self.selected==key) for key,c in items],row=0)
            async def choose(i):
                self.selected=i.data['values'][0];command=self.actions.get(self.selected)
                if not command or not allowed(self.bot,command,i):return await reply(i,'This action is unavailable to you.')
                self.flow=ActionFlow(self,command);await i.response.edit_message(embed=self.draw(i),view=self)
            select.callback=choose;self.add_item(select)
        for label,action in [('Previous','previous'),('Next','next'),('Open action','open'),('Close menu','close')]:
            button=discord.ui.Button(label=label,row=1,disabled=(action=='previous' and self.page==0) or (action=='next' and self.page>=last) or (action=='open' and self.selected is None),style=discord.ButtonStyle.primary if action=='open' else discord.ButtonStyle.secondary)
            async def clicked(i,value=action):
                if value=='close':self.stop();return await i.response.edit_message(content='Menu closed.',embed=None,view=None)
                if value=='open':
                    command=self.actions.get(self.selected)
                    if not command:return await reply(i,'Choose an action first.')
                    self.flow=ActionFlow(self,command);return await self.flow.begin(i)
                self.page+=1 if value=='next' else -1;self.selected=None;self.flow=None;await i.response.edit_message(embed=self.draw(i),view=self)
            button.callback=clicked;self.add_item(button)
        if self.kind=='profile':
            editor=discord.ui.Button(label='Live profile editor',row=2,style=discord.ButtonStyle.success)
            async def live(i):
                from .profile_editor import open_editor
                await open_editor(self.bot,i)
            editor.callback=live;self.add_item(editor)
        embed.set_footer(text=f'Private menu · page {self.page+1}/{last+1} · /{self.kind} to reopen')
        return embed

async def open_menu(bot,i,kind):
    if i.guild_id is None:return await reply(i,'Open this menu inside a server.')
    view=SettingsMenu(bot,kind,i) if kind=='settings' else ActionMenu(bot,kind,i)
    if not await view.interaction_check(i):return
    await i.response.send_message(embed=view.draw(i),view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    with contextlib.suppress(discord.HTTPException):view.message=await i.original_response()

class SettingForm(discord.ui.Modal):
    def __init__(self,menu,name):
        super().__init__(title=('Edit '+name.replace('_',' '))[:45]);self.menu=menu;self.name=name
        from .features import OPTION_TYPES
        from .settings import DEFAULTS
        import json
        typ=OPTION_TYPES[name];current=menu.bot.store.option(menu.guild,name,DEFAULTS.get(name,[] if typ is list else {} if typ is dict else False if typ is bool else 0 if typ is int else ''))
        self.original=current;self.used=False
        text=json.dumps(current) if typ is dict else ', '.join(map(str,current)) if typ is list else str(current).lower() if typ is bool else str(current)
        channels={'goodbye_channel':discord.ChannelType.text,'birthday_channel':discord.ChannelType.text,'daily_channel':discord.ChannelType.text,'raid_channel':discord.ChannelType.text,'review_channel':discord.ChannelType.text,'lfg_channel':discord.ChannelType.text,'voice_category':discord.ChannelType.category,'voice_lobby':discord.ChannelType.voice}
        self.native=name in channels or name in {'autorole','rules_role','reviewer_role'} or name=='ai_channels' and len(current)<=25
        if name in channels:self.input=discord.ui.ChannelSelect(channel_types=[channels[name]],required=False,min_values=0,max_values=1)
        elif name in {'autorole','rules_role','reviewer_role'}:self.input=discord.ui.RoleSelect(required=False,min_values=0,max_values=1)
        elif name=='ai_channels' and self.native:self.input=discord.ui.ChannelSelect(channel_types=[discord.ChannelType.text],required=False,min_values=0,max_values=25)
        elif typ is bool:self.input=discord.ui.Select(options=[discord.SelectOption(label='On',value='true',default=bool(current)),discord.SelectOption(label='Off',value='false',default=not current)])
        else:self.input=discord.ui.TextInput(default=text[:1800],required=False,max_length=1800,style=discord.TextStyle.paragraph if typ in {str,list,dict} else discord.TextStyle.short)
        if self.native:
            ids=current if name=='ai_channels' else [current] if current else []
            getter=self.menu.guild_object.get_role if name in {'autorole','rules_role','reviewer_role'} else self.menu.guild_object.get_channel
            self.input.default_values=[obj for ident in ids if (obj:=getter(ident)) is not None]
        hint='0 = exact only; 1–4 enables similarity and can match unrelated images.' if name=='scam_image_distance' else 'Select channels or roles; leave empty to clear this setting.' if self.native else 'Comma-separated values' if typ is list else 'JSON object' if typ is dict else 'Numeric server channel or role ID, or a number' if typ is int else 'Choose a value'
        self.add_item(discord.ui.Label(text=name.replace('_',' ').title()[:45],description=hint,component=self.input))
    async def on_error(self,i,error):await reply(i,'This setting could not be saved. Reopen the editor and try again.')
    async def on_submit(self,i):
        if not await self.menu.interaction_check(i):return
        if self.used:return await reply(i,'This setting form has already been saved.')
        from .settings import parse_value,validate_resources
        try:
            raw=(','.join(str(v.id) for v in self.input.values) if self.name=='ai_channels' else str(self.input.values[0].id) if self.input.values else '0') if self.native else self.input.values[0] if isinstance(self.input,discord.ui.Select) else str(self.input)
            value=parse_value(self.name,raw);validate_resources(self.menu.bot.store,i.guild,self.name,value)
            current=self.menu.bot.store.option(i.guild_id,self.name,self.original)
            if current!=self.original:raise ValueError('This setting changed in Discord or the dashboard. Reopen the editor before saving.')
        except (ValueError,KeyError,TypeError) as error:return await reply(i,str(error))
        self.used=True
        token=self.menu.bot.store.actor.set('discord:'+str(i.user.id))
        try:self.menu.bot.store.set_option(i.guild_id,self.name,value)
        finally:self.menu.bot.store.actor.reset(token)
        if self.name=='aliases':
            await i.response.defer(ephemeral=True);await self.menu.bot.community.productivity.refresh_aliases(i.guild_id)
        await reply(i,'Saved '+self.name.replace('_',' ')+'. Discord commands and the dashboard use this same setting.')

class SettingsMenu(ActionMenu):
    def __init__(self,*args):super().__init__(*args);self.tab='features';self.key=None
    def draw(self,i):
        if self.tab=='actions':
            embed=super().draw(i)
            back=discord.ui.Button(label='Feature settings',row=2)
            async def features(i):self.tab='features';self.page=0;self.selected=None;self.flow=None;await i.response.edit_message(embed=self.draw(i),view=self)
            back.callback=features;self.add_item(back);return embed
        self.clear_items()
        from .features import FEATURES,OPTION_TYPES,enabled
        keys=list(FEATURES) if self.tab=='features' else [key for key in OPTION_TYPES if key!='faq']
        last=max(0,(len(keys)-1)//PAGE);self.page=min(self.page,last);keys=keys[self.page*PAGE:(self.page+1)*PAGE]
        embed=discord.Embed(title='Vivi · Server settings',description='Manage feature switches and detailed settings here. Changes share the bot’s existing configuration and appear in the dashboard.',color=0xff65ad)
        if self.key:
            current=enabled(self.bot.store,i.guild_id,self.key) if self.tab=='features' else self.bot.store.option(i.guild_id,self.key,'Not set')
            embed.add_field(name=self.key.replace('_',' ').title(),value=discord.utils.escape_markdown(str(current))[:500] or '(empty)',inline=False)
        select=discord.ui.Select(placeholder='Choose a feature' if self.tab=='features' else 'Choose a setting',row=0,options=[discord.SelectOption(label=(key.replace('_',' ').title()+(' · ON' if enabled(self.bot.store,i.guild_id,key) else ' · OFF') if self.tab=='features' else key.replace('_',' ').title())[:100],value=key,default=key==self.key) for key in keys])
        async def choose(i):self.key=i.data['values'][0];await i.response.edit_message(embed=self.draw(i),view=self)
        select.callback=choose;self.add_item(select)
        for label,action in [('Features','features'),('Detailed settings','settings'),('Setup & backups','actions'),('Previous','previous'),('Next','next')]:
            button=discord.ui.Button(label=label,row=1,disabled=(action=='previous' and self.page==0) or (action=='next' and self.page>=last))
            async def tab(i,value=action):
                if value in {'previous','next'}:self.page+=1 if value=='next' else -1
                else:self.tab=value;self.page=0;self.key=None;self.selected=None;self.flow=None
                await i.response.edit_message(embed=self.draw(i),view=self)
            button.callback=tab;self.add_item(button)
        if self.key:
            for label,value in ([('Enable',True),('Disable',False)] if self.tab=='features' else [('Edit value',None)]):
                button=discord.ui.Button(label=label,row=2,style=discord.ButtonStyle.primary)
                async def save(i,on=value,key=self.key,tab=self.tab):
                    if self.key!=key or self.tab!=tab:return await reply(i,'This selection changed. Use its current controls.')
                    if tab!='features':return await i.response.send_modal(SettingForm(self,key))
                    if self.key not in FEATURES:return await reply(i,'Select a valid feature.')
                    token=self.bot.store.actor.set('discord:'+str(i.user.id))
                    try:self.bot.store.set_option(i.guild_id,'feature:'+self.key,on)
                    finally:self.bot.store.actor.reset(token)
                    if self.key=='invite_tracking':self.bot.community.invites.cache.pop(i.guild_id,None)
                    await i.response.edit_message(embed=self.draw(i),view=self)
                button.callback=save;self.add_item(button)
        if self.tab=='features' and self.key=='scam_images':
            references=discord.ui.Button(label='Manage scam-image references',row=2)
            async def manage(i):
                self.tab='actions';self.page=0;self.key=None;self.selected='scam_image_add';self.flow=None
                await i.response.edit_message(embed=self.draw(i),view=self)
            references.callback=manage;self.add_item(references)
        if os.getenv('DASHBOARD_ENABLED','').lower()=='true':
            from .webconfig import dashboard_endpoint
            try:
                uri=os.getenv('DASHBOARD_REDIRECT_URI','http://127.0.0.1:8765/callback');dashboard_endpoint(uri);parsed=urlsplit(uri)
                url=urlunsplit((parsed.scheme,parsed.netloc,'/dashboard','guild='+str(i.guild_id),''))
                self.add_item(discord.ui.Button(label='Open dashboard'+(' (host PC)' if parsed.hostname in {'127.0.0.1','localhost'} else ''),url=url,row=3))
            except ValueError:pass
        close=discord.ui.Button(label='Close menu',row=3)
        async def close_menu(i):self.stop();await i.response.edit_message(content='Settings menu closed.',embed=None,view=None)
        close.callback=close_menu;self.add_item(close)
        embed.set_footer(text=f'Administrator only · page {self.page+1}/{last+1} · values are saved only when you choose a save action')
        return embed

def register_menus(bot):
    bot.menu_groups={name:bot.tree.remove_command(name) for name in ['community','ticket','profile']}
    if any(not isinstance(group,app_commands.Group) for group in bot.menu_groups.values()):raise RuntimeError('Register original feature groups before installing menus.')
    for kind in ['community','ticket','profile','settings']:
        def make(kind):
            async def menu(i:discord.Interaction):await open_menu(bot,i,kind)
            return menu
        command=app_commands.Command(name=kind,description={'community':'Open community activities, polls, birthdays, reports and member tools.','ticket':'Open your private ticket menu, support tools and staff controls.','profile':'Open the live profile editor, privacy, loadouts, uploads and previews.','settings':'Manage features, scam-image filtering, server settings and backups in a private menu.'}[kind],callback=make(kind))
        command.guild_only=True
        if kind=='settings':command.default_permissions=discord.Permissions(administrator=True)
        bot.tree.add_command(command)
