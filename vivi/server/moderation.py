"""Private, single-use confirmation for removing current server members."""
import contextlib
import logging
import discord
from vivi.core.policy import may_moderate

LOG=logging.getLogger('vivi')
class ModerationConfirm(discord.ui.View):
    def __init__(self,bot,interaction,member,action,reason):
        super().__init__(timeout=120)
        if action not in {'kick','ban'}:raise ValueError('Unsupported moderation action.')
        self.bot=bot;self.owner=interaction.user.id;self.guild_id=interaction.guild_id;self.target=member.id;self.action=action;self.reason=reason;self.used=False;self.message=None
        confirm=discord.ui.Button(label='Confirm '+action,style=discord.ButtonStyle.danger)
        cancel=discord.ui.Button(label='Cancel',style=discord.ButtonStyle.secondary)
        confirm.callback=self.confirm;cancel.callback=self.cancel;self.add_item(confirm);self.add_item(cancel)
    async def interaction_check(self,i):
        from vivi.bot import reply
        if i.user.id!=self.owner or i.guild_id!=self.guild_id:
            await reply(i,'Only the moderator who requested this action can confirm or cancel it.');return False
        if self.used or self.is_finished():
            await reply(i,'This confirmation was already used or expired. Run the command again.');return False
        return True
    async def cancel(self,i):
        if not await self.interaction_check(i):return
        self.used=True;self.stop();await i.response.edit_message(content='Cancelled. No action was taken or case logged.',view=None)
    async def confirm(self,i):
        if not await self.interaction_check(i):return
        self.used=True;self.stop()
        await i.response.defer()
        async def result(text):await i.edit_original_response(content=text,view=None)
        if not await self.bot.community.need(i,'moderation'):return await result('Moderation is disabled. No action was taken or case logged.')
        try:
            target=await i.guild.fetch_member(self.target)
        except discord.NotFound:return await result('That member is no longer in this server. No action was taken or case logged.')
        except discord.HTTPException:return await result('Discord could not verify the member. No action was taken or case logged.')
        try:
            actor=await i.guild.fetch_member(self.owner);bot_member=await i.guild.fetch_member(i.guild.me.id)
        except discord.HTTPException:return await result('Current moderator/bot permissions could not be verified. No action was taken or case logged.')
        required='kick_members' if self.action=='kick' else 'ban_members'
        if not all(p.guild_permissions.administrator or getattr(p.guild_permissions,required,False) for p in (actor,bot_member)):
            return await result('You or Vivi no longer have permission for this action. No case was logged.')
        if not may_moderate(actor,target,bot_member,i.guild.owner_id):return await result('The role hierarchy no longer allows this action. No case was logged.')
        if not await self.bot.community.need(i,'moderation'):return await result('Moderation is disabled. No action was taken or case logged.')
        try:
            options=dict(reason=f'{self.owner}: {self.reason}'[:512])
            if self.action=='ban':options['delete_message_seconds']=0
            await getattr(target,self.action)(**options)
        except discord.HTTPException:
            LOG.exception('Confirmed %s failed in guild %s',self.action,self.guild_id)
            return await result('Discord rejected the action. Nothing was logged as a successful case.')
        try:case=await self.bot.community.case(i.guild,target.id,self.owner,self.action,self.reason,target)
        except Exception:
            LOG.exception('Case logging failed after successful %s in guild %s',self.action,self.guild_id)
            return await result(f'{self.action.title()} succeeded, but case logging failed. Check the host error log; do not repeat the action.')
        await result(f'{self.action.title()} completed for user {target.id}. Case #{case}.')
    async def on_timeout(self):
        self.used=True
        for child in self.children:child.disabled=True
        if self.message:
            with contextlib.suppress(discord.HTTPException):await self.message.edit(content='Confirmation expired. No action was taken or case logged.',view=self)

async def request_removal(bot,i,member,action,reason):
    if not await bot.community.need(i,'moderation'):return
    view=ModerationConfirm(bot,i,member,action,reason)
    content=f'Confirm {action} for **{discord.utils.escape_markdown(str(member))}** (user ID `{member.id}`)?\nReason: {discord.utils.escape_markdown(reason)}\nNo action is taken until you confirm. This request expires in two minutes.'
    await i.response.send_message(content,view=view,ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    with contextlib.suppress(discord.HTTPException):view.message=await i.original_response()
