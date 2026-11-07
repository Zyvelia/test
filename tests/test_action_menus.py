import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch,MagicMock
import discord
from discord import app_commands
from vivi.bot import ViviBot
from vivi.core.storage import Store
from vivi.server.action_menus import ActionMenu,SettingsMenu,ActionFlow,ActionForm,FlowView,SettingForm,allowed,invoke,scalar
from vivi.server.help_menu import HelpMenu

class ActionMenus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'menus.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
        self.bot.sync_application_commands=AsyncMock();self.bot.community.start=AsyncMock();self.bot.community.productivity.start_aliases=AsyncMock();await self.bot.setup_hook()
        self.user=NS(id=10,guild_permissions=discord.Permissions.all(),roles=[])
        self.guild=NS(id=1,get_member=lambda uid:self.user if uid==10 else None,get_role=lambda rid:None,get_channel=lambda cid:None)
        self.i=NS(user=self.user,guild_id=1,guild=self.guild,channel_id=20,permissions=discord.Permissions.all(),app_permissions=discord.Permissions.all(),data={},client=self.bot,
            response=NS(is_done=lambda:False,defer=AsyncMock(),send_message=AsyncMock(),edit_message=AsyncMock(),send_modal=AsyncMock()),followup=NS(send=AsyncMock()),original_response=AsyncMock(return_value=NS(edit=AsyncMock())))
        self.views=[]
    async def asyncTearDown(self):
        for view in self.views:view.stop()
        await self.bot.close();self.store.close();self.tmp.cleanup()
    def menu(self,kind):
        menu=SettingsMenu(self.bot,kind,self.i) if kind=='settings' else ActionMenu(self.bot,kind,self.i);self.views.append(menu);return menu
    def flow(self,menu,key):
        flow=ActionFlow(menu,menu.actions[key]);menu.flow=flow;return flow
    async def test_three_groups_are_replaced_by_four_private_entry_points(self):
        for kind in ['community','ticket','profile','settings']:
            command=self.bot.tree.get_command(kind);self.assertIsInstance(command,app_commands.Command)
            await command.callback(self.i);self.assertTrue(self.i.response.send_message.call_args.kwargs['ephemeral']);self.views.append(self.i.response.send_message.call_args.kwargs['view'])
        self.assertEqual(set(self.bot.menu_groups),{'community','ticket','profile','admin','notify'})
        self.assertIsNotNone(self.bot.menu_groups['profile'].get_command('banner_submit'))
    async def test_all_original_actions_have_valid_native_forms(self):
        types=set()
        for kind in ['community','ticket','profile','settings']:
            menu=self.menu(kind)
            for key,command in menu.actions.items():
                flow=self.flow(menu,key)
                for index in range(0,len(command.parameters),5):
                    flow.cursor=index;form=ActionForm(flow);self.views.append(form)
                    self.assertLessEqual(len(form.children),5)
                    json.dumps(form.to_dict())
                    for label in form.children:self.assertIsInstance(label,discord.ui.Label);types.add(type(label.component))
            json.dumps(menu.draw(self.i).to_dict())
            for row in menu.to_components():self.assertLessEqual(len(row['components']),5)
        for typ in [discord.ui.FileUpload,discord.ui.RoleSelect,discord.ui.UserSelect,discord.ui.ChannelSelect]:self.assertIn(typ,types)
    async def test_forms_validate_ranges_choices_and_required_values(self):
        menu=self.menu('community');flow=self.flow(menu,'community birthday');form=ActionForm(flow);self.views.append(form)
        form.inputs[0][1]._value='07-23';await form.on_submit(self.i)
        self.assertEqual(flow.values['date'],'07-23');self.assertNotIn('birthday',self.store.profile(1,10).get('idle_games',{}))
        review=self.i.response.send_message.call_args.kwargs['view'];self.views.append(review)
        self.assertIn('Review',self.i.response.send_message.call_args.kwargs['embed'].title)
        poll=menu.actions['community poll'];minutes=next(p for p in poll.parameters if p.name=='minutes')
        for invalid in ['0','10081','bad','1.5']:
            with self.assertRaises(ValueError):scalar(minutes,invalid)
        boolean=next(p for p in poll.parameters if p.name=='anonymous')
        with self.assertRaises(ValueError):scalar(boolean,'maybe')
        profile=self.menu('profile');field=next(p for p in profile.actions['profile visibility'].parameters if p.name=='field')
        with self.assertRaises(ValueError):scalar(field,'nonexistent')
    async def test_banner_upload_form_preserves_attachment_and_approval_flow(self):
        import io
        from PIL import Image
        self.store.set_option(1,'feature:profiles',True)
        body=io.BytesIO();Image.new('RGB',(30,20),'purple').save(body,'PNG')
        attachment=MagicMock(spec=discord.Attachment);attachment.size=len(body.getvalue());attachment.filename='banner.png';attachment.read=AsyncMock(return_value=body.getvalue())
        menu=self.menu('profile');flow=self.flow(menu,'profile banner_submit');form=ActionForm(flow);self.views.append(form);form.inputs[0][1]._values=[attachment]
        await form.on_submit(self.i);self.assertIs(flow.values['attachment'],attachment)
        confirm=self.i.response.send_message.call_args.kwargs['view'];self.views.append(confirm)
        await confirm.children[0].callback(self.i)
        rows=self.store.records(1,'profile_banner');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['data']['status'],'pending');self.assertEqual(rows[0]['data']['user'],10)
    async def test_channel_selection_uses_original_typed_transform(self):
        channel=MagicMock(spec=discord.TextChannel);channel.guild=self.guild;channel.id=20
        raw=NS(guild_id=1,resolve=lambda:channel)
        menu=self.menu('community');flow=self.flow(menu,'community rules');form=ActionForm(flow);self.views.append(form);form.inputs[0][1]._values=[raw]
        await form.on_submit(self.i);self.assertIs(flow.values['channel'],channel)
        self.views.append(self.i.response.send_message.call_args.kwargs['view'])
    async def test_multi_step_giveaway_stays_unsubmitted_until_confirmation(self):
        menu=self.menu('community');flow=self.flow(menu,'community giveaway');form=ActionForm(flow);self.views.append(form)
        for parameter,control in form.inputs:
            if isinstance(control,discord.ui.TextInput):control._value={'prize':'Test prize','minutes':'60','winners':'1','account_days':'0','member_days':'0'}[parameter.name]
        with patch.object(self.bot.community,'publish',new=AsyncMock()) as publish:
            await form.on_submit(self.i);self.assertEqual(flow.cursor,5);publish.assert_not_awaited()
            continuation=self.i.response.send_message.call_args.kwargs['view'];self.views.append(continuation)
            await continuation.children[0].callback(self.i)
            second=self.i.response.send_modal.call_args.args[0];self.views.append(second)
            for parameter,control in second.inputs:
                if isinstance(control,discord.ui.TextInput):control._value='0'
            await second.on_submit(self.i);publish.assert_not_awaited()
            self.views.append(self.i.response.send_message.call_args.kwargs['view'])
        self.assertEqual(flow.values['required_role'],None);self.assertEqual(flow.values['minimum_level'],0)
    async def test_profile_visibility_runs_original_handler_once(self):
        menu=self.menu('profile');flow=self.flow(menu,'profile visibility');flow.values={'field':'all','public':False};flow.cursor=2
        view=FlowView(flow);self.views.append(view);await view.children[0].callback(self.i)
        self.assertFalse(self.store.profile(1,10)['visible']);self.assertTrue(flow.used)
        self.store.save_profile(1,10,dict(self.store.profile(1,10),visible=True))
        await view.children[0].callback(self.i);self.assertTrue(self.store.profile(1,10)['visible'])
    async def test_revoked_permissions_and_failed_original_checks_do_not_execute(self):
        menu=self.menu('community');flow=self.flow(menu,'community rules');flow.values={'channel':NS(id=20)};view=FlowView(flow);self.views.append(view)
        self.user.guild_permissions=discord.Permissions.none();self.i.permissions=discord.Permissions.none()
        with patch.object(flow.command,'_callback',new=AsyncMock()) as callback:await view.children[0].callback(self.i);callback.assert_not_awaited()
        self.user.guild_permissions=discord.Permissions.all();self.i.permissions=discord.Permissions.all()
        command=menu.actions['community poll'];command.checks.append(lambda i:False)
        with patch.object(command,'_callback',new=AsyncMock()) as callback:await invoke(self.bot,command,self.i,{});callback.assert_not_awaited()
    async def test_menus_and_forms_are_owner_and_guild_bound(self):
        menu=self.menu('community');flow=self.flow(menu,'community birthday');self.user.id=11
        self.assertFalse(await menu.interaction_check(self.i));self.assertFalse(await flow.check(self.i))
        self.user.id=10;self.i.guild_id=2;self.assertFalse(await flow.check(self.i))
        self.i.guild_id=1;menu.flow=None;self.assertFalse(await flow.check(self.i))
    async def test_settings_feature_changes_are_shared_and_admin_only(self):
        menu=self.menu('settings');menu.key='games';menu.draw(self.i)
        button=next(c for c in menu.children if getattr(c,'label','')=='Enable');await button.callback(self.i)
        self.assertTrue(self.store.option(1,'feature:games'));self.assertIn('True',str(menu.draw(self.i).to_dict()))
        self.user.guild_permissions=discord.Permissions.none();self.assertFalse(await menu.interaction_check(self.i))
    async def test_setting_editor_prevents_stale_overwrites_and_uses_shared_validation(self):
        menu=self.menu('settings');self.store.set_option(1,'welcome_text','Before');form=SettingForm(menu,'welcome_text');self.views.append(form)
        form.input._value='After';await form.on_submit(self.i);self.assertEqual(self.store.option(1,'welcome_text'),'After')
        stale=SettingForm(menu,'welcome_text');self.views.append(stale);self.store.set_option(1,'welcome_text','Changed in dashboard');stale.input._value='Stale'
        await stale.on_submit(self.i);self.assertEqual(self.store.option(1,'welcome_text'),'Changed in dashboard')
        invalid=SettingForm(menu,'spam_limit');self.views.append(invalid);invalid.input._value='0';await invalid.on_submit(self.i);self.assertIsNone(self.store.option(1,'spam_limit'))
    async def test_setting_channel_and_role_selectors_are_native(self):
        menu=self.menu('settings')
        for name,typ in [('goodbye_channel',discord.ui.ChannelSelect),('autorole',discord.ui.RoleSelect),('ai_channels',discord.ui.ChannelSelect)]:
            form=SettingForm(menu,name);self.views.append(form);self.assertIsInstance(form.input,typ);json.dumps(form.to_dict())
    async def test_ticket_open_and_close_delegate_to_existing_permissions_and_confirmation(self):
        menu=self.menu('ticket')
        with patch('vivi.bot.OpenTicketView.create_ticket',new=AsyncMock()) as create:
            await invoke(self.bot,menu.actions['ticket open'],self.i,{});create.assert_awaited_once()
        await invoke(self.bot,menu.actions['ticket close'],self.i,{})
        self.assertIn('Only the ticket owner',self.i.response.send_message.call_args.args[0])
    async def test_legacy_favorites_resolve_to_new_menu_names(self):
        p=self.store.profile(1,10);p['favorites']=['profile customize','profile preview','ticket status','community birthday'];self.store.save_profile(1,10,p)
        view=HelpMenu(self.bot,10,1);self.views.append(view);view.section='favorites'
        self.assertEqual(view.favorites(),['profile','ticket','community']);self.assertEqual(len(view.rows(self.i)),3)
    async def test_ticket_alias_can_still_resolve_its_retired_internal_handler(self):
        self.store.set_option(1,'feature:custom_aliases',True);self.store.set_option(1,'aliases',{'myticket':{'target':'ticket','argument':''}})
        command=self.bot.menu_groups['ticket'].get_command('status')
        with patch.object(command,'_callback',new=AsyncMock()) as callback:await self.bot.community.productivity.run_alias(self.i,'myticket');callback.assert_awaited_once()

    async def test_admin_group_and_panel_commands_are_hidden_behind_private_menu(self):
        command=self.bot.tree.get_command('admin');self.assertIsInstance(command,app_commands.Command)
        self.assertIsNone(self.bot.tree.get_command('role_button'));self.assertIsNone(self.bot.tree.get_command('ticket_panel'));self.assertIsNone(self.bot.tree.get_command('notify'));self.assertIsNone(self.bot.tree.get_command('economy').get_command('channel_xp'))
        await command.callback(self.i);kwargs=self.i.response.send_message.call_args.kwargs;self.assertTrue(kwargs['ephemeral'])
        menu=kwargs['view'];self.views.append(menu);self.assertIsInstance(menu,SettingsMenu);self.assertEqual(menu.tab,'actions')
        self.assertIn('role_button',menu.actions);self.assertIn('ticket_panel',menu.actions)
        for name in ['notify add','notify list','notify remove','notify filters','economy channel_xp','alias add','alias remove']:self.assertIn(name,menu.actions)
        for name in ['backup','restore','health','history','rollback','backup_now','branding','updates','verify']:self.assertIn('admin '+name,menu.actions)
        self.assertNotIn('admin feature',menu.actions)
        from vivi.server.action_menus import action_label
        self.assertEqual(action_label(menu.actions['notify add']),'Notifications · Add');self.assertEqual(action_label(menu.actions['alias add']),'Aliases · Add')
        for name in ['setup','embed','globalban','warn','warnings','timeout','untimeout','kick','ban','purge']:self.assertIsInstance(self.bot.tree.get_command(name),app_commands.Command)
        for name in ['lockdown','unlock','slowmode','unban','tempban','history']:self.assertIsNotNone(self.bot.tree.get_command('mod').get_command(name))
    async def test_admin_menu_denies_nonadministrator_on_open_and_after_role_change(self):
        self.user.guild_permissions=discord.Permissions(moderate_members=True)
        await self.bot.tree.get_command('admin').callback(self.i);self.assertIn('Administrator',self.i.response.send_message.call_args.args[0])
        self.user.guild_permissions=discord.Permissions.all();menu=self.menu('settings');flow=self.flow(menu,'admin backup');self.user.guild_permissions=discord.Permissions(moderate_members=True)
        await flow.begin(self.i);self.i.response.send_modal.assert_not_awaited();self.assertFalse(await menu.interaction_check(self.i))
    async def test_hidden_role_panel_still_uses_original_checks_and_review(self):
        menu=self.menu('settings');flow=self.flow(menu,'role_button');await flow.begin(self.i)
        self.assertTrue(self.i.response.send_modal.called)
        self.user.guild_permissions=discord.Permissions.none()
        self.assertFalse(allowed(self.bot,menu.actions['role_button'],self.i))
    async def test_favorites_for_old_admin_and_panel_commands_resolve_to_admin_menu(self):
        from vivi.server.help_menu import normalize_favorites
        self.assertEqual(normalize_favorites(self.bot,['admin backup','role_button','ticket_panel','admin health','notify add','economy channel_xp','alias add']),['admin'])
