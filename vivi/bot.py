import asyncio
import datetime
import io
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from .storage import Store, database_path
from .policy import safe_self_role, may_moderate, may_close

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger('vivi')


class StartupConfigurationError(RuntimeError):
    """An actionable setup failure that should not trigger automatic crash retries."""


async def reply(interaction, text):
    from .i18n import interaction_language,localize_message
    text = localize_message(interaction_language(interaction),str(text))[:1950]
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


async def audit(bot, guild, text, **kwargs):
    config = bot.store.settings(guild.id)
    channel = guild.get_channel(config['logs']) if config else None
    if channel:
        if channel.permissions_for(guild.default_role).view_channel:
            LOG.warning('Staff log channel is visible to @everyone in guild %s; withholding private log', guild.id)
            return False
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none(), **kwargs)
        except discord.HTTPException:
            LOG.warning('Could not write moderation log in guild %s', guild.id)


class RoleView(discord.ui.View):
    def __init__(self, bot, guild_id, role_id, label='Toggle role'):
        super().__init__(timeout=None)
        self.bot, self.guild_id, self.role_id = bot, guild_id, role_id
        button = discord.ui.Button(label=label[:80], style=discord.ButtonStyle.secondary,
                                   custom_id=f'aurora:role:{guild_id}:{role_id}')
        button.callback = self.toggle
        self.add_item(button)

    async def toggle(self, i):
        if not i.guild or i.guild.id != self.guild_id:
            return await reply(i, 'This role button is unavailable here.')
        if not await self.bot.community.need(i,'roles'): return
        role = i.guild.get_role(self.role_id)
        config = self.bot.store.settings(i.guild.id)
        if (not config or not role or role.id == config['staff']
                or not safe_self_role(role, i.guild.me)):
            return await reply(i, 'This role is unavailable or no longer safe to self-assign. Ask an admin.')
        await i.response.defer(ephemeral=True)
        key = (i.guild.id, i.user.id, role.id)
        async with self.bot.role_locks.setdefault(key, asyncio.Lock()):
            try:
                member = await i.guild.fetch_member(i.user.id)
                if role in member.roles:
                    await member.remove_roles(role, reason='Vivi self-service role')
                    await reply(i, f'Removed {role.name}.')
                else:
                    await member.add_roles(role, reason='Vivi self-service role')
                    await reply(i, f'Added {role.name}.')
            except discord.HTTPException:
                await reply(i, 'I could not update the role. Check Manage Roles and my role position.')


class OpenTicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Open a support ticket', style=discord.ButtonStyle.primary,
                       custom_id='aurora:ticket:open')
    async def open_ticket(self, i, button):
        if i.guild:
            from .features import enabled
            categories=self.bot.store.option(i.guild.id,'ticket_categories',{})
            if enabled(self.bot.store,i.guild.id,'ticket_tools') and categories:
                if not await self.bot.community.need(i,'tickets'): return
                from .operations import TicketCategoryView
                return await i.response.send_message('Choose a support category:',view=TicketCategoryView(self.bot,categories),ephemeral=True)
        await self.create_ticket(i)

    async def create_ticket(self, i, category_label='General'):
        if not i.guild:
            return await reply(i, 'Tickets work inside the server.')
        if not await self.bot.community.need(i,'tickets'): return
        config = self.bot.store.settings(i.guild.id)
        if not config:
            return await reply(i, 'An administrator must run /setup first.')
        await i.response.defer(ephemeral=True)
        async with self.bot.ticket_lock:
            old = self.bot.store.ticket_for_user(i.guild.id, i.user.id)
            if old:
                try:
                    channel = await i.guild.fetch_channel(old['channel'])
                    return await reply(i, f'You already have a ticket: {channel.mention}')
                except discord.NotFound:
                    self.bot.store.remove_ticket(old['channel'])
                except discord.HTTPException:
                    return await reply(i, 'Could not check your existing ticket. Try again shortly.')
            categories=self.bot.store.option(i.guild.id,'ticket_categories',{})
            category = i.guild.get_channel(categories.get(category_label,config['category']))
            staff = i.guild.get_role(config['staff'])
            if not isinstance(category, discord.CategoryChannel) or not staff:
                return await reply(i, 'Ticket category or staff role is missing. Ask an admin to rerun /setup.')
            overwrites = {
                i.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                            read_message_history=True, attach_files=True),
                staff: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                            read_message_history=True),
                i.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                            read_message_history=True, manage_channels=True, attach_files=True),
            }
            channel = None
            recorded = False
            try:
                channel = await i.guild.create_text_channel(f'ticket-{i.user.id}',
                    category=category, overwrites=overwrites, reason='Vivi support ticket')
                self.bot.store.add_ticket(i.guild.id, i.user.id, channel.id)
                recorded = True
                self.bot.community.operations.save_ticket_meta(i.guild.id,channel.id,dict(category=category_label,priority='normal',claimed=0,tags=[]),actor=i.user.id)
                await channel.send(f'Welcome {i.user.mention}! Describe your issue below. '
                    'Server administrators and the configured support staff can see this channel. '
                    'Closing saves the most recent 1,000 messages, then deletes the channel.',
                    view=CloseTicketView(self.bot),
                    allowed_mentions=discord.AllowedMentions(users=[i.user], roles=False, everyone=False))
            except Exception:
                LOG.exception('Ticket creation failed')
                if channel:
                    try:
                        await channel.delete(reason='Incomplete Vivi ticket cleanup')
                        if recorded:
                            self.bot.store.remove_ticket(channel.id)
                            self.bot.store.delete_record(f'ticket:{channel.id}')
                    except discord.HTTPException:
                        LOG.warning('Incomplete ticket channel needs cleanup: %s', channel.id)
                return await reply(i, 'Ticket creation failed. Ask staff to check my channel permissions.')
            await reply(i, f'Your private ticket is ready: {channel.mention}')
            await audit(self.bot, i.guild, f'Ticket opened by {i.user} ({i.user.id}): {channel.mention}')


class CloseTicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label='Close ticket', style=discord.ButtonStyle.danger,
                       custom_id='aurora:ticket:close')
    async def close_ticket(self, i, button):
        ticket = self.bot.store.ticket_for_channel(i.channel_id)
        config = self.bot.store.settings(i.guild_id)
        if not ticket or not config or not may_close(i.user, ticket, config['staff']):
            return await reply(i, 'Only the ticket owner or support staff can close this ticket.')
        await i.response.send_message('Save a transcript and permanently delete this ticket channel?',
                                     view=ConfirmClose(self.bot, i.user.id), ephemeral=True)


class ConfirmClose(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=60)
        self.bot, self.user_id = bot, user_id

    @discord.ui.button(label='Save transcript and close', style=discord.ButtonStyle.danger)
    async def confirm(self, i, button):
        if i.user.id != self.user_id:
            return await reply(i, 'This confirmation belongs to another user.')
        await i.response.defer(ephemeral=True)
        async with self.bot.ticket_lock:
            ticket = self.bot.store.ticket_for_channel(i.channel_id)
            config = self.bot.store.settings(i.guild_id)
            if not ticket or not config or not may_close(i.user, ticket, config['staff']):
                return await reply(i, 'You cannot close this ticket now.')
            try:
                # Fetch newest messages, then put the limited transcript in chronological order.
                messages = [m async for m in i.channel.history(limit=1000)]
                from .suite import ticket_event,timeline
                ticket_event(self.bot.store,i.guild_id,i.channel_id,i.user.id,'closing','Transcript requested')
                activity=timeline(self.bot.store,i.guild_id,i.channel_id,i.user.id,True)
                lines = [activity,f'Ticket {i.channel_id}; owner {ticket["user"]}; closed by {i.user.id}',
                         'Most recent 1,000 messages. Attachments are links, not downloaded copies.',
                         str(self.bot.community.operations.ticket_meta(i.channel_id))]
                for m in reversed(messages):
                    lines.append(f'[{m.created_at.isoformat()}] {m.author} ({m.author.id}): {m.content}')
                    lines.extend(a.url for a in m.attachments)
                data = '\n'.join(lines).encode('utf-8')
                folder = ROOT / 'data' / 'transcripts'
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f'{i.channel_id}.txt'
                path.write_bytes(data)
                # A local transcript is required; Discord upload failure does not erase it.
                await audit(self.bot, i.guild, f'Ticket {i.channel_id} closed by {i.user} ({i.user.id}).',
                            file=discord.File(io.BytesIO(data), filename=path.name))
                await i.channel.delete(reason=f'Vivi ticket closed by {i.user.id}')
                self.bot.store.remove_ticket(i.channel_id)
                await self.bot.community.operations.closed(i.guild,ticket)
            except Exception:
                LOG.exception('Ticket close failed')
                return await reply(i, 'Could not finish closing. The ticket record is retained; ask staff to check logs.')
            self.stop()
            await reply(i, 'Ticket closed. Transcript saved on the host PC.')


class ViviBot(commands.Bot):
    def __init__(self, store):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True  # Needed only for readable ticket transcripts.
        super().__init__(command_prefix=commands.when_mentioned, intents=intents,
                         allowed_mentions=discord.AllowedMentions.none())
        self.store = store
        self.ticket_lock = asyncio.Lock()
        self.role_locks = {}
        from .community import Community
        self.community = Community(self)
        self.tree.interaction_check = self.command_allowed

    async def setup_hook(self):
        self.add_view(OpenTicketView(self))
        self.add_view(CloseTicketView(self))
        for record in self.store.roles():
            self.add_view(RoleView(self, record['guild'], record['role']))
        register_commands(self)
        from .community import register_extra
        register_extra(self)
        from .operations import register_operations
        from .music import register_voice
        register_operations(self); register_voice(self)
        from .productivity import register_productivity
        from .i18n import ViviTranslator
        register_productivity(self)
        from .customization import register_customization
        register_customization(self)
        from .suite import register_suite
        from .game_hub import register_games
        register_suite(self); register_games(self)
        from .competitions import register_competitions
        from .guild_library import register_library
        from .invites import register_invites
        from .profiles import register_profiles
        register_competitions(self);register_library(self);register_invites(self);register_profiles(self)
        await self.tree.set_translator(ViviTranslator())
        synced = await self.sync_application_commands()
        await self.community.start()
        await self.community.productivity.start_aliases()
        LOG.info('Registered %s slash commands', len(synced))

    async def sync_application_commands(self):
        dev = os.getenv('DEV_GUILD_ID', '').strip()
        guild = None
        if dev:
            try:
                ident = int(dev)
                if not 0 < ident < 2**64: raise ValueError
            except ValueError:
                raise StartupConfigurationError('DEV_GUILD_ID must be blank or a positive Discord server ID.') from None
            guild = discord.Object(id=ident)
            self.tree.copy_global_to(guild=guild)
        try:
            return await self.tree.sync(guild=guild) if guild else await self.tree.sync()
        except app_commands.CommandSyncFailure as error:
            raise StartupConfigurationError(
                'Discord rejected the slash-command definitions. Update Vivi to the latest version; '
                'restarting repeatedly will not fix an invalid command payload. '
                f'Details: {error}'
            ) from error
        except (discord.Forbidden, discord.NotFound) as error:
            application = self.application_id
            identity = f'Application {application}' if application else 'This bot application'
            if guild:
                message = (
                    f'{identity} cannot register slash commands in DEV_GUILD_ID={guild.id} '
                    f'(HTTP {error.status}, Discord code {error.code}). '
                    'Invite this bot to that server with BOTH bot and applications.commands scopes '
                    '(Server Install), and confirm DEV_GUILD_ID is the server ID, not a channel or application ID. '
                    'If unsure, leave DEV_GUILD_ID= blank for global commands; the bot must still be invited '
                    'to your server. Confirm DISCORD_TOKEN belongs to the intended application. '
                    'Startup stopped; fix .env or the server installation, then restart once.'
                )
            else:
                message = (
                    f'{identity} cannot register global slash commands '
                    f'(HTTP {error.status}, Discord code {error.code}). '
                    'Confirm DISCORD_TOKEN belongs to the intended application and reinstall the bot '
                    'with both bot and applications.commands scopes (Server Install). '
                    'Startup stopped; fix the installation, then restart once.'
                )
            raise StartupConfigurationError(message) from error

    async def on_ready(self):
        LOG.info('Connected as %s. Keep this window open.', self.user)

    async def on_member_join(self, member):
        await self.community.on_join(member)

    async def command_allowed(self, i):
        from .features import enabled
        if not i.guild or i.command is None: return True
        self.store.actor.set(f'discord:{i.user.id}')
        mapping = {'role_button':'roles', 'ticket_panel':'tickets',
                   'warn':'moderation','warnings':'moderation','timeout':'moderation',
                   'untimeout':'moderation','kick':'moderation','ban':'moderation','purge':'moderation'}
        feature = mapping.get(i.command.name)
        if feature and not enabled(self.store,i.guild_id,feature):
            await reply(i,f'{feature} is disabled here. An admin can use /admin feature.')
            return False
        return True

    async def close(self):
        await self.community.close()
        await super().close()


def register_commands(bot):
    tree = bot.tree

    @tree.command(name='ping', description='Check whether the bot is online.')
    async def ping(i: discord.Interaction):
        await reply(i, f'Online! Gateway latency: {bot.latency * 1000:.0f} ms.')

    @tree.command(name='help', description='See setup, member, and moderator commands.')
    async def help_command(i: discord.Interaction):
        await reply(i, '**Vivi**\nMembers: /ping, role buttons, ticket buttons.\n'
                    'Admins: /setup, /role_button, /ticket_panel.\n'
                    'Moderators: /warn, /warnings, /timeout, /untimeout, /kick, /ban, /purge.\n'
                    'Search everything with /tools commands. Vivi also has /ticket, /music, /room and /notify. Admins configure /admin features and the dashboard. '
                    'AI is optional and off by default. The host PC must stay awake.')

    @tree.command(name='setup', description='Configure welcome, support, and private staff logging channels.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(i: discord.Interaction, welcome: discord.TextChannel,
                    ticket_category: discord.CategoryChannel, staff: discord.Role,
                    logs: discord.TextChannel):
        if staff.is_default() or staff.managed:
            return await reply(i, 'Choose a dedicated human support role, not @everyone or a managed role.')
        if logs.permissions_for(i.guild.default_role).view_channel:
            return await reply(i, 'Choose a private log channel: deny View Channel for @everyone first.')
        for channel in (welcome, logs):
            perms = channel.permissions_for(i.guild.me)
            if not (perms.view_channel and perms.send_messages):
                return await reply(i, f'I need View Channel and Send Messages in {channel.mention}.')
        perms = ticket_category.permissions_for(i.guild.me)
        if not (perms.view_channel and perms.manage_channels):
            return await reply(i, 'I need View Channel and Manage Channels in the ticket category.')
        if not logs.permissions_for(i.guild.me).attach_files:
            return await reply(i, 'I need Attach Files in the log channel for transcripts.')
        bot.store.configure(i.guild.id, welcome.id, ticket_category.id, staff.id, logs.id)
        await reply(i, 'Configuration saved. Run /ticket_panel and /role_button where you want member buttons.')

    @tree.command(name='role_button', description='Post a self-service button for a safe, non-staff role.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def role_button(i: discord.Interaction, channel: discord.TextChannel,
                          role: discord.Role, label: app_commands.Range[str, 1, 80]):
        config = bot.store.settings(i.guild.id)
        if (not config or role.id == config['staff'] or not safe_self_role(role, i.guild.me)):
            return await reply(i, 'Run /setup first and choose a non-staff role with no moderation or management permissions below my role.')
        await i.response.defer(ephemeral=True)
        bot.store.add_role(i.guild.id, role.id)
        view = RoleView(bot, i.guild.id, role.id, label)
        await channel.send(f'Choose your **{discord.utils.escape_markdown(role.name)}** role:', view=view)
        await reply(i, f'Role button posted in {channel.mention}.')

    @tree.command(name='ticket_panel', description='Post a persistent button to open private support tickets.')
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(i: discord.Interaction, channel: discord.TextChannel):
        if not bot.store.settings(i.guild.id):
            return await reply(i, 'Run /setup first.')
        await i.response.defer(ephemeral=True)
        embed = discord.Embed(title='Need a hand?', description='Open a private ticket for the support team. One open ticket per member.', color=0x87CEEB)
        await channel.send(embed=embed, view=OpenTicketView(bot))
        await reply(i, f'Ticket panel posted in {channel.mention}.')

    async def guard(i, member):
        if not may_moderate(i.user, member, i.guild.me, i.guild.owner_id):
            await reply(i, 'You or I lack the role hierarchy needed to moderate this member.')
            return False
        return True

    @tree.command(name='warn', description='Record a persistent warning for a member.')
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(i: discord.Interaction, member: discord.Member, reason: app_commands.Range[str, 1, 500]):
        if not await guard(i, member): return
        ident = bot.store.warn(i.guild.id, member.id, i.user.id, reason)
        await i.response.defer(ephemeral=True)
        case = await bot.community.case(i.guild, member.id, i.user.id, 'warning', reason, member)
        await reply(i, f'Warning #{ident} recorded for {member}. Case #{case}.')
        await bot.community.operations.warning_threshold(i.guild,member,i.user.id)

    @tree.command(name='warnings', description='Show the most recent ten warnings for a member.')
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(i: discord.Interaction, member: discord.Member):
        rows = bot.store.warnings(i.guild.id, member.id)
        text = '\n'.join(f'#{r["id"]} · {r["created"]} · {r["reason"][:120]}' for r in rows)
        await reply(i, text or 'No warnings recorded.')

    @tree.command(name='timeout', description='Temporarily prevent a member from talking, up to 28 days.')
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(i: discord.Interaction, member: discord.Member,
                      minutes: app_commands.Range[int, 1, 40320], reason: app_commands.Range[str, 1, 500]):
        if not await guard(i, member): return
        await i.response.defer(ephemeral=True)
        await member.timeout(datetime.timedelta(minutes=minutes), reason=f'{i.user.id}: {reason}'[:512])
        await reply(i, f'Timed out {member} for {minutes} minutes.')
        await bot.community.case(i.guild, member.id, i.user.id, 'timeout', f'{minutes} minutes: {reason}', member)

    @tree.command(name='untimeout', description='Remove an active member timeout.')
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(i: discord.Interaction, member: discord.Member):
        if not await guard(i, member): return
        await i.response.defer(ephemeral=True)
        await member.timeout(None, reason=f'Vivi timeout removed by {i.user.id}')
        await reply(i, f'Removed timeout for {member}.')
        await bot.community.case(i.guild, member.id, i.user.id, 'timeout removed', 'Removed by moderator', member)

    @tree.command(name='kick', description='Remove a member from this server.')
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(i: discord.Interaction, member: discord.Member, reason: app_commands.Range[str, 1, 500]):
        if not await guard(i, member): return
        await i.response.defer(ephemeral=True)
        await member.kick(reason=f'{i.user.id}: {reason}'[:512])
        await reply(i, f'Kicked {member}.')
        await bot.community.case(i.guild, member.id, i.user.id, 'kick', reason, member)

    @tree.command(name='ban', description='Ban a current member without deleting their message history.')
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(i: discord.Interaction, member: discord.Member, reason: app_commands.Range[str, 1, 500]):
        if not await guard(i, member): return
        await i.response.defer(ephemeral=True)
        await member.ban(reason=f'{i.user.id}: {reason}'[:512], delete_message_seconds=0)
        await reply(i, f'Banned {member}.')
        await bot.community.case(i.guild, member.id, i.user.id, 'ban', reason, member)

    @tree.command(name='purge', description='Delete up to 100 recent messages in this channel.')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(i: discord.Interaction, count: app_commands.Range[int, 1, 100]):
        if not isinstance(i.channel, discord.TextChannel):
            return await reply(i, 'Use purge in a server text channel.')
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=count, check=lambda m: (discord.utils.utcnow()-m.created_at).days<14)
        await reply(i, f'Deleted {len(deleted)} messages. Messages older than 14 days are left alone.')
        await bot.community.case(i.guild, 0, i.user.id, 'purge', f'{len(deleted)} messages in {i.channel_id}')

    @tree.error
    async def errors(i, error):
        if isinstance(error, app_commands.MissingPermissions):
            return await reply(i, 'You do not have permission to use this command.')
        if isinstance(error, app_commands.BotMissingPermissions):
            return await reply(i, 'I am missing permissions: ' + ', '.join(error.missing_permissions))
        if isinstance(error, app_commands.CommandOnCooldown):
            return await reply(i, f'Try again in {error.retry_after:.0f} seconds.')
        original = getattr(error, 'original', error)
        if isinstance(original, discord.Forbidden):
            return await reply(i, 'Discord denied that action. Check my channel permissions and role position.')
        if isinstance(original, ValueError):
            return await reply(i, str(original)[:1800])
        LOG.error('Command failed', exc_info=(type(original), original, original.__traceback__))
        await reply(i, 'That action failed. Check the bot terminal for details, then retry.')


def main():
    load_dotenv(ROOT / '.env')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    token = os.getenv('DISCORD_TOKEN', '').strip()
    if not token or token == 'paste_your_token_here':
        LOG.error('Add DISCORD_TOKEN to .env first. Never share the token in chat or commit it.'); raise SystemExit(2)
    dev = os.getenv('DEV_GUILD_ID', '').strip()
    if dev and (not dev.isdigit() or int(dev) <= 0):
        LOG.error('DEV_GUILD_ID must be blank or a positive Discord server ID.'); raise SystemExit(2)
    from .runtime import SingleInstance
    try:
        instance=SingleInstance(ROOT/'data'/'vivi.lock')
        store = Store(database_path(ROOT))
    except ValueError as error:
        LOG.error('%s',error); raise SystemExit(2)
    bot = ViviBot(store)
    try:
        bot.run(token, log_handler=None)
    except StartupConfigurationError as error:
        LOG.error('%s', error); raise SystemExit(2)
    except discord.PrivilegedIntentsRequired:
        LOG.error('Enable Server Members Intent and Message Content Intent in the Discord Developer Portal, then restart.'); raise SystemExit(2)
    except discord.LoginFailure:
        LOG.error('Discord rejected DISCORD_TOKEN. Reset it in the Developer Portal and update .env.'); raise SystemExit(2)
    finally:
        store.close()
        instance.close()


if __name__ == '__main__':
    main()
