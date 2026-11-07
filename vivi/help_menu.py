"""Private, owner-bound help browser built from the live slash-command registry."""
import contextlib
import math
import discord
from discord import app_commands
from .bot import reply

PAGE_SIZE=10
CATEGORIES={
 'games':('Games & idle worlds',{'games','cards','puzzles','idle','competition'}),
 'profile':('Profiles & shop',{'profile','economy'}),
 'community':('Community',{'community','social','teams','library','lfg'}),
 'support':('Tickets & support',{'ticket','support','appeals','reports'}),
 'voice':('Music & voice',{'music','room'}),
 'notifications':('Notifications',{'notify'}),
 'moderation':('Moderation',{'mod','cases','warn','warnings','timeout','untimeout','kick','ban','purge'}),
 'settings':('Server settings',{'admin','setup','role_button','ticket_panel','alias'}),
 'tools':('Tools & privacy',set())}

def category(command):
    root=command.qualified_name.split()[0]
    return next((key for key,(_,roots) in CATEGORIES.items() if root in roots),'tools')

def visible(command,interaction):
    """Discovery filter only: command execution still enforces all original checks."""
    node=command;permissions=getattr(interaction.user,'guild_permissions',discord.Permissions.none())
    while node:
        if interaction.guild_id is None and getattr(node,'guild_only',False):return False
        required=node.default_permissions
        if required is not None and not permissions.administrator and (required.value==0 or permissions.value&required.value!=required.value):return False
        node=node.parent
    return True

class SearchModal(discord.ui.Modal,title='Find a Vivi command'):
    query=discord.ui.TextInput(label='Command or feature',placeholder='Try farm, blackjack, birthday, or privacy',max_length=100)
    def __init__(self,menu):super().__init__();self.menu=menu
    async def on_submit(self,i):
        if not await self.menu.interaction_check(i):return
        self.menu.query=str(self.query).strip();self.menu.section='all';self.menu.page=0;self.menu.selected=None
        await self.menu.update(i)

class HelpMenu(discord.ui.View):
    def __init__(self,bot,owner,guild):
        super().__init__(timeout=900);self.bot=bot;self.owner=owner;self.guild=guild
        self.section='home';self.query='';self.page=0;self.selected=None;self.message=None
    async def interaction_check(self,i):
        if i.user.id!=self.owner or i.guild_id!=self.guild:
            await reply(i,'This help menu belongs to another member. Open your own with /help.');return False
        if self.is_finished():
            await reply(i,'This help menu has expired. Open /help again.');return False
        return True
    def commands(self,i):
        commands=list(self.bot.tree.walk_commands())
        if self.guild is not None:
            for root in self.bot.tree.get_commands(guild=discord.Object(id=self.guild)):
                commands.extend(root.walk_commands() if isinstance(root,app_commands.Group) else [root])
        return sorted([c for c in commands if isinstance(c,app_commands.Command) and visible(c,i)],key=lambda c:c.qualified_name)
    def favorites(self):
        return self.bot.store.profile(self.guild,self.owner).get('favorites',[]) if self.guild is not None else []
    def rows(self,i):
        commands=self.commands(i)
        if self.section=='favorites':commands=[c for c in commands if c.qualified_name in self.favorites()]
        elif self.section in CATEGORIES:commands=[c for c in commands if category(c)==self.section]
        terms=self.query.lower().split()
        return [c for c in commands if all(term in (c.qualified_name+' '+c.description).lower() for term in terms)]
    def draw(self,i):
        self.clear_items();all_commands=self.commands(i);rows=self.rows(i)
        last=max(0,math.ceil(len(rows)/PAGE_SIZE)-1);self.page=min(max(self.page,0),last)
        page=rows[self.page*PAGE_SIZE:(self.page+1)*PAGE_SIZE]
        selected=next((c for c in all_commands if c.qualified_name==self.selected),None)
        embed=discord.Embed(title='Vivi · Help menu',color=0xff65ad)
        if selected:
            embed.title='Vivi · /'+selected.qualified_name;embed.description=selected.description
            if selected.parameters:
                for parameter in selected.parameters[:12]:
                    choices=', '.join(str(choice.value) for choice in parameter.choices[:12])
                    description=parameter.description
                    if description=='…':description='Choose a value in Discord’s command form.'
                    embed.add_field(name=parameter.display_name+(' · required' if parameter.required else ' · optional'),value=(description+('\nChoices: '+choices if choices else ''))[:200],inline=False)
            else:embed.add_field(name='Arguments',value='No arguments required.',inline=False)
            embed.add_field(name='How to use',value=f'Type `/{selected.qualified_name}` in Discord and select it from the command picker. This help menu does not run the command.',inline=False)
        elif self.section=='home':
            embed.description='What would you like help with? Choose a category below, search by name, or open your saved favorites.'
            for key,(name,_) in CATEGORIES.items():
                count=sum(category(c)==key for c in all_commands)
                if count:embed.add_field(name=name,value=f'{count} commands',inline=True)
            embed.add_field(name='Getting started',value='Administrators: start with `/setup` and choose modules with `/admin feature`.\nGames: browse `/cards`, `/puzzles` and `/idle`.\nMenus show instructions; existing slash commands remain available.',inline=False)
        else:
            title='Favorites' if self.section=='favorites' else CATEGORIES.get(self.section,('All commands',))[0]
            embed.description=f'**{title}**'+(f' · Search: {discord.utils.escape_markdown(self.query)}' if self.query else '')+f'\nPage {self.page+1}/{last+1} · {len(rows)} matching commands'
            for command in page:embed.add_field(name='/'+command.qualified_name,value=command.description[:250],inline=False)
            if not page:embed.add_field(name='No matches',value='Try another category or search. Save favorites from a command’s detail page.',inline=False)
        embed.set_footer(text='Private menu · expires after 15 minutes idle · commands check permissions and feature settings when run')
        options=[discord.SelectOption(label='Home',value='home',default=self.section=='home'),discord.SelectOption(label='All commands',value='all',default=self.section=='all')]
        options += [discord.SelectOption(label=name,value=key,default=self.section==key) for key,(name,_) in CATEGORIES.items() if any(category(c)==key for c in all_commands)]
        menu=discord.ui.Select(placeholder='Choose a help category',row=0,options=options)
        async def choose(i):
            self.section=i.data['values'][0];self.query='';self.page=0;self.selected=None;await self.update(i)
        menu.callback=choose;self.add_item(menu)
        if self.section!='home' and page:
            detail=discord.ui.Select(placeholder='View command instructions',row=1,options=[discord.SelectOption(label='/'+c.qualified_name,value=c.qualified_name,description=c.description[:100]) for c in page])
            async def pick(i):self.selected=i.data['values'][0];await self.update(i)
            detail.callback=pick;self.add_item(detail)
        for label,action in [('Home','home'),('Back','back'),('Previous','previous'),('Next','next'),('Search','search'),('Favorites','favorites'),('Close','close')]:
            disabled=(action in {'previous','next'} and (self.section=='home' or (self.page==0 if action=='previous' else self.page>=last))) or (action=='back' and not self.selected)
            button=discord.ui.Button(label=label,row=2 if action in {'home','back','previous','next','search'} else 3,disabled=disabled,style=discord.ButtonStyle.primary if action=='search' else discord.ButtonStyle.secondary)
            async def click(i,value=action):
                if value=='search':return await i.response.send_modal(SearchModal(self))
                if value=='close':
                    self.stop();return await i.response.edit_message(embed=discord.Embed(title='Help menu closed',description='Open /help whenever you need it.',color=0xff65ad),view=None)
                if value=='back':self.selected=None
                elif value in {'previous','next'}:self.page+=1 if value=='next' else -1;self.selected=None
                else:self.section=value;self.page=0;self.query='';self.selected=None
                await self.update(i)
            button.callback=click;self.add_item(button)
        if selected and self.guild is not None:
            name=selected.qualified_name;is_favorite=name in self.favorites()
            button=discord.ui.Button(label='Remove favorite' if is_favorite else 'Save favorite',row=3,style=discord.ButtonStyle.success)
            async def favorite(i):
                profile=self.bot.store.profile(self.guild,self.owner);values=profile.get('favorites',[])
                if name in values:values.remove(name)
                elif len(values)>=20:return await reply(i,'You already have 20 favorites. Remove one first.')
                else:values.append(name)
                profile['favorites']=values;self.bot.store.save_profile(self.guild,self.owner,profile);await self.update(i)
            button.callback=favorite;self.add_item(button)
        return embed
    async def update(self,i):await i.response.edit_message(embed=self.draw(i),view=self)
    async def on_timeout(self):
        for item in self.children:item.disabled=True
        if self.message:
            with contextlib.suppress(discord.HTTPException):await self.message.edit(view=self)

async def open_help(bot,i):
    view=HelpMenu(bot,i.user.id,i.guild_id)
    await i.response.send_message(embed=view.draw(i),view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    with contextlib.suppress(discord.HTTPException):view.message=await i.original_response()
