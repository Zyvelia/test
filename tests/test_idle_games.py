import copy
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
from PIL import Image
from vivi.games.idle_games import GAMES,CAP_MS,new_game,advance,act,cost,rates,prestige_goal,render,IdleService,IdleView,PrestigeView
from vivi.core.storage import Store

class IdleRules(unittest.TestCase):
    def test_starting_automation_earns_offline_without_collecting(self):
        for kind in GAMES:
            state=new_game(1000);report=advance(kind,state,61000)
            self.assertEqual(report['sold'],2000 if kind=='farm' else 1000)
            self.assertEqual(report['income'],4000 if kind=='farm' else 3000)
            self.assertEqual(state['cash'],100000+report['income'])
            self.assertEqual(state['stock'],2000)
    def test_duplicate_refresh_and_backwards_clock_do_not_mint_money(self):
        state=new_game(1000);advance('farm',state,61000);saved=copy.deepcopy(state)
        advance('farm',state,61000);self.assertEqual(saved,state)
        advance('farm',state,1);self.assertEqual(saved,state)
    def test_small_intervals_preserve_fractional_progress(self):
        first=new_game(0);second=new_game(0)
        advance('farm',first,60000)
        for now in range(1,60001):advance('farm',second,now)
        self.assertEqual(first,second)
    def test_offline_cap_and_storage_are_enforced(self):
        state=new_game(0);report=advance('farm',state,CAP_MS*20)
        expected=new_game(0);advance('farm',expected,CAP_MS)
        self.assertTrue(report['capped']);self.assertEqual(report['credited_ms'],CAP_MS)
        self.assertEqual(state['cash'],expected['cash']);self.assertEqual(state['stock'],400000)
        advance('farm',state,CAP_MS*20);self.assertEqual(state['cash'],expected['cash'])
    def test_upgrade_spends_once_and_applies_only_to_future_production(self):
        state=new_game(0);price=cost(state,'production');act('farm',state,'production')
        self.assertEqual(state['cash'],100000-price);self.assertEqual(state['levels']['production'],2)
        before=copy.deepcopy(state)
        with self.assertRaises(ValueError):act('farm',state,'production')
        self.assertEqual(before,state)
        advance('farm',state,60000);self.assertEqual(state['stock'],6000)
    def test_collect_transfers_stock_only_once(self):
        state=new_game(0);advance('market',state,60000);before=state['cash'];stock=state['stock'];act('market',state,'collect')
        self.assertEqual(state['cash'],before+stock*3);before=state['cash'];act('market',state,'collect');self.assertEqual(state['cash'],before)
    def test_prestige_requires_milestone_and_preserves_lifetime_earnings(self):
        state=new_game(0)
        with self.assertRaises(ValueError):act('farm',state,'prestige')
        state['earned']=prestige_goal(state);earned=state['earned'];state['levels']['production']=10
        act('farm',state,'prestige');self.assertEqual(state['prestige'],1);self.assertEqual(state['levels']['production'],1)
        self.assertEqual(state['cash'],100000);self.assertEqual(state['earned'],earned);self.assertEqual(state['stock'],0)
        self.assertEqual(rates('farm',state)['production'],500)
        with self.assertRaises(ValueError):act('farm',state,'prestige')
    def test_research_limits_and_invalid_actions_do_not_mutate(self):
        state=new_game(0);state['cash']=10**20;state['levels']['variety']=5;before=copy.deepcopy(state)
        for action in ['variety','unknown']:
            with self.assertRaises(ValueError):act('farm',state,action)
            self.assertEqual(state,before)
    def test_both_games_render_distinct_portable_cards(self):
        images=[]
        for kind in GAMES:
            body=render(kind,new_game(0));self.assertEqual(Image.open(io.BytesIO(body)).size,(1000,640));images.append(body)
        self.assertNotEqual(*images)

class IdlePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'idle.sqlite3';self.store=Store(self.path);self.service=IdleService(NS(store=self.store))
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_games_members_and_servers_are_isolated(self):
        for guild,user,kind in [(1,10,'farm'),(1,10,'market'),(2,10,'farm'),(1,11,'farm')]:self.service.perform(guild,user,kind,now=1000)
        self.service.perform(1,10,'farm','production',now=1000)
        self.assertEqual(self.store.profile(1,10)['idle_games']['farm']['levels']['production'],2)
        for guild,user,kind in [(1,10,'market'),(2,10,'farm'),(1,11,'farm')]:self.assertEqual(self.store.profile(guild,user)['idle_games'][kind]['levels']['production'],1)
    def test_restart_retains_profiles_and_earns_elapsed_time(self):
        self.service.perform(1,10,'farm',now=1000);self.store.close();self.store=Store(self.path);self.service=IdleService(NS(store=self.store))
        state,report,_=self.service.perform(1,10,'farm',now=61000);self.assertEqual(state['cash'],104000);self.assertEqual(report['income'],4000)
    def test_repeated_purchase_cannot_double_spend(self):
        self.service.perform(1,10,'market','production',now=1000)
        with self.assertRaises(ValueError):self.service.perform(1,10,'market','production',now=1000)
        state=self.store.profile(1,10)['idle_games']['market'];self.assertEqual(state['levels']['production'],2);self.assertGreaterEqual(state['cash'],0)
    def test_old_upgrade_and_reset_cards_cannot_spend_or_reset_again(self):
        self.service.perform(1,10,'farm',now=1000)
        profile=self.store.profile(1,10);profile['idle_games']['farm']['cash']=10**9;profile['idle_games']['farm']['earned']=10**9;self.store.save_profile(1,10,profile)
        self.service.perform(1,10,'farm','production',now=1000,expected_level=1)
        before=self.store.profile(1,10)['idle_games']['farm']['cash']
        with self.assertRaises(ValueError):self.service.perform(1,10,'farm','production',now=1000,expected_level=1)
        self.assertEqual(self.store.profile(1,10)['idle_games']['farm']['cash'],before)
        self.service.perform(1,10,'farm','prestige',now=1000,expected_prestige=0)
        with self.assertRaises(ValueError):self.service.perform(1,10,'farm','prestige',now=1000,expected_prestige=0)
        self.assertEqual(self.store.profile(1,10)['idle_games']['farm']['prestige'],1)
    def test_render_snapshot_does_not_mutate_saved_profile(self):
        state,_,_=self.service.perform(1,10,'farm',now=1000);state['cash']=999999
        self.assertEqual(self.store.profile(1,10)['idle_games']['farm']['cash'],100000)
    def test_personal_data_deletion_removes_both_game_profiles(self):
        self.service.perform(1,10,'farm',now=1000);self.service.perform(1,10,'market',now=1000)
        self.store.delete_personal(1,10);self.assertNotIn('idle_games',self.store.profile(1,10))

class IdleControls(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'idle.sqlite3');self.service=IdleService(NS(store=self.store,need=AsyncMock(return_value=True)))
        self.i=NS(user=NS(id=10),guild_id=1,response=NS(is_done=lambda:False,defer=AsyncMock(),send_message=AsyncMock()),followup=NS(send=AsyncMock()),edit_original_response=AsyncMock())
    async def asyncTearDown(self):self.store.close();self.tmp.cleanup()
    async def test_private_profile_and_owner_bound_controls(self):
        await self.service.show(self.i,'farm');options=self.i.followup.send.call_args.kwargs;self.assertTrue(options['ephemeral']);options['file'].close()
        self.i.user.id=20
        with patch.object(self.service,'show',new=AsyncMock()) as show:await options['view'].children[1].callback(self.i);show.assert_not_awaited()
    async def test_wrong_guild_controls_are_rejected(self):
        self.i.guild_id=2;view=IdleView(self.service,1,10,'market')
        with patch.object(self.service,'show',new=AsyncMock()) as show:await view.children[0].callback(self.i);show.assert_not_awaited()
    async def test_disabled_games_do_not_create_profiles(self):
        self.service.service.need.return_value=False;await self.service.show(self.i,'farm')
        self.assertNotIn('idle_games',self.store.profile(1,10));self.i.followup.send.assert_not_awaited()
    async def test_prestige_confirmation_is_single_use(self):
        view=PrestigeView(self.service,1,10,'farm')
        with patch.object(self.service,'show',new=AsyncMock()) as show:
            await view.children[0].callback(self.i);await view.children[0].callback(self.i);show.assert_awaited_once()
    async def test_buttons_fit_component_limits(self):
        view=IdleView(self.service,1,10,'farm');self.assertEqual(len(view.children),7)
        for row in view.to_components():self.assertLessEqual(len(row['components']),5)
