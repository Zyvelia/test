"""Private global-ban controls, bound to a configured numeric Discord account."""
import contextlib
from collections import Counter
import discord
from discord import app_commands
from vivi.bot import reply
from vivi.server.action_menus import OwnedView
from vivi.server.global_bans import is_operator,operator_id,user_id

class OperatorView(OwnedView):
    async def interaction_check(self,i):
        if not is_operator(i.user):await reply(i,'Global-ban controls are restricted to Vivi’s configured operator account.');return False
        return await super().interaction_check(i)

class ConfirmGlobal(OperatorView):
    def __init__(self,service,i,target,reason,evidence='',remove=False,undo=False):
        super().__init__(i.user.id,i.guild_id);self.service=service;self.target=target;self.reason=reason;self.evidence=evidence;self.remove=remove;self.undo=undo;self.used=False
        self.guild_ids=[g.id for g in service.bot.guilds if service.participating(g)]
        button=discord.ui.Button(label='Confirm removal' if remove else 'Confirm global ban',style=discord.ButtonStyle.danger)
        async def confirm(i):
            if not await self.interaction_check(i):return
            if self.used:return await reply(i,'This confirmation was already used.')
            self.used=True
            try:count=service.remove(target,reason,undo,i.user.id) if remove else service.add(target,reason,evidence,i.user.id,[g.id for g in service.bot.guilds if service.participating(g)])
            except (ValueError,PermissionError) as error:return await reply(i,str(error))
            self.stop();await i.response.edit_message(content=f'Global entry {"removed" if remove else "saved"}. {count} server job(s) queued. Open /globalban → Results to check outcomes. '+('Existing bans remain unless verified undo was selected.' if remove else 'Only currently opted-in servers are included. Future owner opt-ins can enforce this entry.'),embed=None,view=None)
        button.callback=confirm;self.add_item(button)
        cancel=discord.ui.Button(label='Cancel')
        async def stop(i):
            if not await self.interaction_check(i):return
            self.used=True;self.stop();await i.response.edit_message(content='Cancelled. Nothing changed.',embed=None,view=None)
        cancel.callback=stop;self.add_item(cancel)

class GlobalForm(discord.ui.Modal):
    def __init__(self,view,remove=False):
        super().__init__(title='Remove global entry' if remove else 'Add global ban');self.view=view;self.remove=remove
        self.target=discord.ui.TextInput(label='Discord user ID',max_length=20)
        self.reason=discord.ui.TextInput(label='Reason',min_length=10,max_length=500,style=discord.TextStyle.paragraph)
        self.add_item(self.target);self.add_item(self.reason)
        if remove:
            self.undo=discord.ui.Select(options=[discord.SelectOption(label='Remove from blocklist only',value='no',default=True),discord.SelectOption(label='Also undo verifiable Vivi-issued bans',value='yes')])
            self.add_item(discord.ui.Label(text='Existing server bans',component=self.undo))
        else:
            self.evidence=discord.ui.TextInput(label='Evidence reference (link or case ID)',min_length=3,max_length=1000,style=discord.TextStyle.paragraph);self.add_item(self.evidence)
    async def on_submit(self,i):
        if not await self.view.interaction_check(i):return
        try:target=user_id(str(self.target))
        except ValueError as error:return await reply(i,str(error))
        if not self.remove and target in {operator_id(),self.view.service.bot.user.id}:return await reply(i,'Vivi and its operator are protected accounts.')
        await i.response.defer(ephemeral=True,thinking=True)
        if not self.remove:
            try:user=self.view.service.bot.get_user(target) or await self.view.service.bot.fetch_user(target)
            except discord.HTTPException:return await i.followup.send('Discord could not verify that user ID. No action was taken.',ephemeral=True)
            name=discord.utils.escape_markdown(str(user))
        else:name=str(target)
        undo=self.remove and bool(self.undo.values and self.undo.values[0]=='yes')
        view=ConfirmGlobal(self.view.service,i,target,str(self.reason),'' if self.remove else str(self.evidence),self.remove,undo)
        embed=discord.Embed(title='Review global removal' if self.remove else 'Review global ban',description=f'Account: **{name}**\nUser ID: `{target}`\nReason: {discord.utils.escape_markdown(str(self.reason))}',color=0xff65ad)
        if self.remove:embed.add_field(name='Server bans',value='Undo only verifiable Vivi-issued bans in still-participating servers; independent, unverified and opted-out server bans stay.' if undo else 'Remove the global entry only. Existing server bans stay.',inline=False)
        else:
            embed.add_field(name='Scope',value=f'{len(view.guild_ids)} currently opted-in server(s); membership can change before confirmation. Ban Members and role hierarchy are checked per server. No historical messages will be deleted.',inline=False)
            embed.add_field(name='Evidence',value=discord.utils.escape_markdown(str(self.evidence))[:1000],inline=False)
        embed.set_footer(text='No changes until you confirm. Results are saved per server.')
        view.message=await i.followup.send(embed=embed,view=view,ephemeral=True,wait=True,allowed_mentions=discord.AllowedMentions.none())

class GlobalMenu(OperatorView):
    def __init__(self,service,i):
        super().__init__(i.user.id,i.guild_id);self.service=service
        for label,action in [('Add global ban','add'),('Remove entry','remove'),('Blocklist','list'),('Results','results'),('Retry jobs','retry')]:
            button=discord.ui.Button(label=label)
            async def click(i,value=action):
                if not await self.interaction_check(i):return
                if value in {'add','remove'}:return await i.response.send_modal(GlobalForm(self,value=='remove'))
                if value=='retry':
                    count=service.retry(i.user.id)
                    return await reply(i,f'{count} eligible failed/skipped jobs queued for retry; consent and active entries are checked again.')
                embed=discord.Embed(title='Vivi · Global blocklist' if value=='list' else 'Vivi · Global-ban results',color=0xff65ad)
                if value=='list':
                    rows=service.entries();embed.description=f'{len(rows)} active entries. Showing the latest 10.'
                    for row in rows[-10:]:
                        data=row['data'];embed.add_field(name=str(data['target']),value=(discord.utils.escape_markdown(data['reason'])[:150]+'\nEvidence: '+discord.utils.escape_markdown(data['evidence'])[:200]),inline=False)
                else:
                    rows=service.store.records(kind='global_ban_job');counts=Counter(row['data']['status'] for row in rows);embed.description=' · '.join(f'{key}: {value}' for key,value in counts.items()) or 'No global-ban jobs yet.'
                    for row in sorted(rows,key=lambda r:r['data'].get('created',0))[-15:]:
                        data=row['data'];embed.add_field(name=discord.utils.escape_markdown(data['guild_name'])[:80]+f' · {data["action"]}',value=f'User {data["target"]} · {data["status"]}\n'+data.get('result','Waiting for the worker.')[:180],inline=False)
                await i.response.send_message(embed=embed,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
            button.callback=click;self.add_item(button)

def register_global_bans(bot):
    @bot.tree.command(name='globalban',description='Operator-only global blocklist, confirmations and per-server enforcement results.')
    async def globalban(i:discord.Interaction):
        if not is_operator(i.user):return await reply(i,'Global-ban controls are restricted to Vivi’s configured operator account.')
        view=GlobalMenu(bot.community.global_bans,i)
        embed=discord.Embed(title='Vivi · Global-ban controls',description='Only your configured Discord account can use these controls. Server owners must opt in before any network ban is enforced. Additions require a user ID, reason, evidence and confirmation.',color=0xff65ad)
        await i.response.send_message(embed=embed,view=view,ephemeral=True)
        with contextlib.suppress(discord.HTTPException):view.message=await i.original_response()


class ConfirmParticipation(OwnedView):
    def __init__(self,service,i):
        super().__init__(i.user.id,i.guild_id);self.service=service;self.used=False
        button=discord.ui.Button(label='Confirm owner opt-in',style=discord.ButtonStyle.danger)
        async def confirm(i):
            if not await self.interaction_check(i):return
            if self.used:return await reply(i,'This consent confirmation was already used.')
            self.used=True
            try:service.set_participation(i.guild,i.user.id,True,confirmed=True)
            except (PermissionError,ValueError) as error:return await reply(i,str(error))
            self.stop();await i.response.edit_message(content='Owner consent saved. Active global entries are queued for this server. Disabling enforcement later does not undo existing bans.',view=None)
        button.callback=confirm;self.add_item(button)

async def confirm_participation(service,i):
    if i.user.id!=i.guild.owner_id:return await reply(i,'Only the server owner can opt in to this network.')
    await i.response.send_message(f'Opt in to global bans controlled by Discord user `{operator_id()}`? There are currently {len(service.entries())} active entries. Existing and future entries may be banned from this server. Disabling later stops enforcement but does not undo existing bans.',view=ConfirmParticipation(service,i),ephemeral=True)
