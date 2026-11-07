import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from vivi.core.storage import Store
from vivi.core.policy import may_close, may_moderate, safe_self_role
from vivi.bot import ViviBot, OpenTicketView, RoleView, CloseTicketView, ConfirmClose, register_commands


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'database.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_settings_survive_restart(self):
        self.store.configure(1, 2, 3, 4, 5)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(dict(self.store.settings(1)), dict(guild=1, welcome=2, category=3, staff=4, logs=5))
        self.assertIsNone(self.store.settings(2))

    def test_ticket_uniqueness_and_closure(self):
        self.store.add_ticket(1, 8, 9)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_ticket(1, 8, 10)
        self.assertEqual(self.store.ticket_for_channel(9)['user'], 8)
        self.store.remove_ticket(9)
        self.store.add_ticket(1, 8, 10)
        self.assertEqual(self.store.ticket_for_user(1, 8)['channel'], 10)

    def test_warnings_are_scoped_and_limited(self):
        self.store.warn(2, 8, 5, 'Other guild')
        self.store.warn(1, 9, 5, 'Other member')
        for x in range(12):
            self.store.warn(1, 8, 5, f'Warning {x}')
        rows = self.store.warnings(1, 8)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]['reason'], 'Warning 11')
        self.assertTrue(all(row['guild'] == 1 and row['user'] == 8 for row in rows))

    def test_role_registration_is_idempotent(self):
        self.store.add_role(1, 42)
        self.store.add_role(1, 42)
        self.assertEqual(len(self.store.roles()), 1)


class Role:
    def __init__(self, rank=1, ident=10, managed=False, default=False, **perms):
        self.rank, self.id, self.managed, self.default = rank, ident, managed, default
        self.permissions = NS(**perms)
    def is_default(self): return self.default
    def __lt__(self, other): return self.rank < other.rank
    def __gt__(self, other): return self.rank > other.rank
    def __ge__(self, other): return self.rank >= other.rank


class PolicyTests(unittest.TestCase):
    def test_self_role_rejects_privilege_and_hierarchy(self):
        bot = NS(top_role=Role(10))
        self.assertTrue(safe_self_role(Role(1), bot))
        for role in [Role(10), Role(1, managed=True), Role(1, default=True),
                     Role(1, administrator=True), Role(1, manage_roles=True), Role(1, moderate_members=True)]:
            self.assertFalse(safe_self_role(role, bot))

    def test_moderation_hierarchy_and_protected_members(self):
        actor = NS(id=1, top_role=Role(5))
        bot = NS(id=2, top_role=Role(10))
        self.assertTrue(may_moderate(actor, NS(id=3, top_role=Role(2)), bot, 99))
        for target in [NS(id=99, top_role=Role(1)), actor, bot, NS(id=3, top_role=Role(5)), NS(id=3, top_role=Role(11))]:
            self.assertFalse(may_moderate(actor, target, bot, 99))
        self.assertTrue(may_moderate(NS(id=99, top_role=Role(1)), NS(id=3, top_role=Role(5)), bot, 99))

    def test_ticket_close_restricted_to_owner_staff_or_manager(self):
        user = NS(id=8, roles=[], guild_permissions=NS(manage_channels=False))
        self.assertTrue(may_close(user, {'user': 8}, 20))
        self.assertFalse(may_close(user, {'user': 9}, 20))
        user.roles = [NS(id=20)]
        self.assertTrue(may_close(user, {'user': 9}, 20))


class InteractionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'db.sqlite3')
        self.bot = ViviBot(self.store)
        await self.bot.__aenter__()
        self.store.configure(1, 2, 3, 4, 5)
        self.channel = NS(id=55, mention='<#55>', send=AsyncMock(), delete=AsyncMock())
        category = MagicMock(spec=discord.CategoryChannel)
        self.guild = NS(id=1, default_role=MagicMock(), me=MagicMock(),
                        get_channel=lambda ident: category if ident == 3 else None,
                        get_role=lambda ident: MagicMock(),
                        fetch_channel=AsyncMock(return_value=self.channel),
                        create_text_channel=AsyncMock(return_value=self.channel))
        self.user = MagicMock()
        self.user.id=8
        self.user.mention='<@8>'

    async def asyncTearDown(self):
        await self.bot.close()
        self.store.close()
        self.tmp.cleanup()

    def interaction(self):
        return NS(guild=self.guild, guild_id=1, user=self.user, channel_id=55,
                  response=NS(defer=AsyncMock(), is_done=lambda: True, send_message=AsyncMock()),
                  followup=NS(send=AsyncMock()))

    async def test_concurrent_ticket_clicks_create_one_private_channel(self):
        view = OpenTicketView(self.bot)
        await asyncio.gather(view.open_ticket.callback(self.interaction()), view.open_ticket.callback(self.interaction()))
        self.guild.create_text_channel.assert_awaited_once()
        overwrites=self.guild.create_text_channel.call_args.kwargs['overwrites']
        self.assertFalse(overwrites[self.guild.default_role].view_channel)
        self.assertTrue(overwrites[self.user].view_channel)
        self.assertEqual(self.store.ticket_for_user(1,8)['channel'],55)

    async def test_failed_ticket_welcome_cleans_up_channel_and_record(self):
        self.channel.send.side_effect = RuntimeError('Simulated failure')
        with self.assertLogs('vivi', level='ERROR'):
            await OpenTicketView(self.bot).open_ticket.callback(self.interaction())
        self.channel.delete.assert_awaited_once()
        self.assertIsNone(self.store.ticket_for_user(1,8))

    async def test_ticket_access_denial_does_not_drop_existing_record(self):
        self.store.add_ticket(1,8,55)
        self.guild.fetch_channel.side_effect = discord.Forbidden(NS(status=403, reason='Forbidden'), 'Denied')
        await OpenTicketView(self.bot).open_ticket.callback(self.interaction())
        self.guild.create_text_channel.assert_not_awaited()
        self.assertIsNotNone(self.store.ticket_for_user(1,8))

    async def test_staff_role_cannot_be_self_assigned_from_old_button(self):
        i=self.interaction()
        self.guild.get_role=lambda ident: Role(1, ident=4)
        await RoleView(self.bot,1,4).toggle(i)
        i.response.defer.assert_not_awaited()
        self.assertIn('unavailable', i.followup.send.call_args.args[0])

    async def test_ticket_close_denies_unrelated_member(self):
        self.store.add_ticket(1,9,55)
        self.user.roles=[]
        self.user.guild_permissions=NS(manage_channels=False)
        i=self.interaction()
        await CloseTicketView(self.bot).close_ticket.callback(i)
        i.response.send_message.assert_not_awaited()
        self.assertIn('Only the ticket owner',i.followup.send.call_args.args[0])

    async def test_failed_transcript_keeps_ticket(self):
        self.store.add_ticket(1,8,55)
        i=self.interaction()
        async def broken_history(**kwargs):
            raise RuntimeError('Simulated transcript failure')
            yield
        i.channel=NS(history=broken_history, delete=AsyncMock())
        with self.assertLogs('vivi',level='ERROR'):
            await ConfirmClose(self.bot,8).confirm.callback(i)
        i.channel.delete.assert_not_awaited()
        self.assertIsNotNone(self.store.ticket_for_channel(55))

    async def test_successful_close_saves_transcript_before_deletion(self):
        self.store.add_ticket(1,8,55)
        i=self.interaction()
        now=discord.utils.utcnow()
        async def history(**kwargs):
            self.assertEqual(kwargs['limit'],1000)
            yield NS(created_at=now,author=NS(id=8),content='new message',attachments=[])
            yield NS(created_at=now,author=NS(id=8),content='old message',attachments=[NS(url='https://example.com/file')])
        path=Path(self.tmp.name)/'data/transcripts/55.txt'
        async def delete(**kwargs):
            self.assertTrue(path.exists())
        i.channel=NS(history=history, delete=AsyncMock(side_effect=delete))
        with patch('vivi.bot.ROOT',Path(self.tmp.name)), patch('vivi.bot.audit',new_callable=AsyncMock):
            await ConfirmClose(self.bot,8).confirm.callback(i)
        self.assertLess(path.read_text().index('old message'),path.read_text().index('new message'))
        self.assertIn('https://example.com/file',path.read_text())
        i.channel.delete.assert_awaited_once()
        self.assertIsNone(self.store.ticket_for_channel(55))

    async def test_role_button_adds_and_removes_role(self):
        role=Role(1,ident=33)
        role.name='Gaming'
        self.guild.me=NS(top_role=Role(10))
        self.guild.get_role=lambda ident: role
        member=NS(roles=[],add_roles=AsyncMock(),remove_roles=AsyncMock())
        self.guild.fetch_member=AsyncMock(return_value=member)
        view=RoleView(self.bot,1,33)
        await view.toggle(self.interaction())
        member.add_roles.assert_awaited_once_with(role,reason='Vivi self-service role')
        member.roles=[role]
        await view.toggle(self.interaction())
        member.remove_roles.assert_awaited_once_with(role,reason='Vivi self-service role')

    async def test_welcome_event_mentions_only_joining_member(self):
        welcome=NS(send=AsyncMock())
        self.guild.get_channel=lambda ident: welcome if ident==2 else None
        self.guild.name='Test Server'
        self.user.guild=self.guild
        await self.bot.on_member_join(self.user)
        welcome.send.assert_awaited_once()
        mentions=welcome.send.call_args.kwargs['allowed_mentions']
        self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.roles)
        self.assertEqual(mentions.users,[self.user])

    async def test_persistent_views_restore_and_sync_is_offline_mocked(self):
        self.store.add_role(1,33)
        self.bot.tree.sync=AsyncMock(return_value=[])
        with patch.dict(os.environ, {'DEV_GUILD_ID':'123'}):
            await self.bot.setup_hook()
        self.assertEqual(len(self.bot.persistent_views),3)
        self.assertEqual(self.bot.tree.sync.call_args.kwargs['guild'].id,123)
        self.assertIn('admin', {c.name for c in self.bot.tree.get_commands()})
        self.assertIn('ai', {c.name for c in self.bot.tree.get_commands()})

    async def test_moderation_commands_enforce_runtime_permissions(self):
        register_commands(self.bot)
        i=self.interaction()
        i.permissions=discord.Permissions.none()
        i.app_permissions=discord.Permissions.all()
        for name in ['setup','role_button','ticket_panel','warn','warnings','timeout','untimeout','kick','ban','purge']:
            checks=self.bot.tree.get_command(name).checks
            with self.assertRaises(discord.app_commands.MissingPermissions):
                for check in checks:
                    result=check(i)
                    if asyncio.iscoroutine(result): await result


if __name__ == '__main__':
    unittest.main()
