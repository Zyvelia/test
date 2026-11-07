import asyncio
import copy
import io
import json
import random
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
import discord
from PIL import Image
from vivi.card_games import Blackjack,GoFish,total,RANKS
from vivi.network_puzzles import NETWORK_TYPES,SIZES,rotate
from vivi.game_design import presentation,render
from vivi.game_hub import GameHub,GameView,CoordinateView
from vivi.storage import Store

def game(kind,engine):return dict(key=(1,10),kind=kind,engine=engine,players=[10,20] if kind in {'blackjack','go_fish'} else [10],accepted=True,ready=True,theme='velvet',expires=time.time()+1800,vs_vivi=kind in {'blackjack','go_fish'})

class CardRules(unittest.TestCase):
    def test_aces_and_faces(self):
        self.assertEqual(total(['AH','AS','9C']),21)
        self.assertEqual(total(['AH','KS']),21)
        self.assertEqual(total(['QH','JS','2D']),22)
    def test_blackjack_turns_push_and_bust(self):
        engine=Blackjack();engine.hands=[['KH','QC'],['KS','QD']]
        engine.move('stand');self.assertEqual(engine.turn,1);engine.move('stand')
        self.assertTrue(engine.done);self.assertEqual(engine.winners,[])
        with self.assertRaises(ValueError):engine.move('hit')
        engine=Blackjack(vs_vivi=False);engine.hands=[['KH','QC'],['AS','7D']];engine.deck=['5H']
        engine.move('hit');self.assertEqual(engine.turn,1);engine.move('stand');self.assertEqual(engine.winners,[1])
    def test_player_bust_ends_dealer_game_immediately(self):
        engine=Blackjack();engine.hands=[['KH','QC'],['9S','7D']];engine.deck=['8C','5H']
        engine.move('hit');self.assertTrue(engine.done);self.assertEqual(engine.winners,[1]);self.assertEqual(len(engine.hands[1]),2)
    def test_blackjack_ai_stands_on_soft_seventeen(self):
        engine=Blackjack();engine.hands=[['KH','QC'],['AS','6D']];engine.move('stand');engine.bot_move()
        self.assertTrue(engine.done);self.assertEqual(len(engine.hands[1]),2);self.assertEqual(engine.winners,[0])
    def test_go_fish_transfer_and_books(self):
        engine=GoFish();engine.hands=[['AH','AS','AD'],['AC','2S']];engine.deck=['3H','4H']
        engine.move('A');self.assertEqual(engine.books[0],['A']);self.assertEqual(engine.turn,0)
        self.assertNotIn('AC',engine.hands[1]);self.assertTrue(engine.hands[0])
        with self.assertRaises(ValueError):engine.move('K')
    def test_go_fish_draw_match_keeps_turn(self):
        engine=GoFish();engine.hands=[['5H'],['2H']];engine.deck=['7S','5C']
        engine.move('5');self.assertEqual(engine.turn,0);self.assertIn('5C',engine.hands[0])
        engine.move('5');self.assertEqual(engine.turn,1)
    def test_go_fish_random_games_finish_and_conserve_cards(self):
        for seed in range(30):
            engine=GoFish(rng=random.Random(seed));rng=random.Random(seed)
            for _ in range(500):
                active=len(engine.deck)+sum(map(len,engine.hands))+4*sum(map(len,engine.books))
                self.assertEqual(active,52)
                if engine.done:break
                ranks=[c[:-1] for c in engine.hands[engine.turn]]
                engine.move(rng.choice(ranks))
            self.assertTrue(engine.done,seed);self.assertEqual(sum(map(len,engine.books)),13)
    def test_public_and_private_hands_do_not_leak(self):
        for kind,factory in [('blackjack',Blackjack),('go_fish',GoFish)]:
            engine=factory();g=game(kind,engine);before=presentation(g);private=presentation(g,10)
            if kind=='blackjack':engine.hands[1][1]='2C'
            else:engine.hands[1]=['2C']*len(engine.hands[1])
            self.assertEqual(before,presentation(g));self.assertEqual(private,presentation(g,10))
            with self.assertRaises(ValueError):presentation(g,99)
            self.assertNotIn('deck',before)
    def test_card_images_render_public_private_and_finished(self):
        for kind,factory in [('blackjack',Blackjack),('go_fish',GoFish)]:
            g=game(kind,factory())
            for viewer in [None,10,20]:
                image=Image.open(io.BytesIO(render(presentation(g,viewer))))
                self.assertEqual(image.size,(960,760))
            g['engine'].done=True;render(presentation(g))

class ProceduralRules(unittest.TestCase):
    def test_generated_solution_works_for_every_size_and_difficulty(self):
        for kind,factory in NETWORK_TYPES.items():
            for size in SIZES:
                for difficulty in ['easy','medium','hard']:
                    for seed in range(8):
                        with self.subTest(kind=kind,size=size,difficulty=difficulty,seed=seed):
                            engine=factory(difficulty,size,str(seed));self.assertFalse(engine.solved())
                            self.assertEqual(len(engine.cells),SIZES[size]);engine.cells=copy.deepcopy(engine.solution);self.assertTrue(engine.solved())
    def test_solutions_can_be_reached_through_legal_rotation_moves(self):
        for kind,factory in NETWORK_TYPES.items():
            engine=factory('hard','large','rotation-test');n=engine.size
            for r in range(n):
                for c in range(n):
                    if engine.done:break
                    target=engine.solution[r][c];current=engine.cells[r][c]
                    turns=next((turns for turns in range(4) if (3-current if turns%2 and current in {1,2} else current)==target),None) if kind=='laser_locks' else next(turns for turns in range(4) if rotate(current,turns)==target)
                    if turns:engine.move(f'{chr(65+c)}{n-r} {turns}')
            self.assertTrue(engine.done,kind);self.assertIn('solved',engine.result)
    def test_seed_reproducibility_and_fresh_randomness(self):
        for factory in NETWORK_TYPES.values():
            first=factory(seed='same');second=factory(seed='same');self.assertEqual(first.cells,second.cells)
            fresh=[factory() for _ in range(12)];self.assertEqual(len({p.seed for p in fresh}),12)
            self.assertGreater(len({json.dumps(p.cells) for p in fresh}),10)
    def test_saved_boards_preserve_rotations_and_deadline(self):
        for kind,factory in NETWORK_TYPES.items():
            engine=factory(size='large');loaded=factory.load(json.loads(json.dumps(engine.dump())))
            self.assertEqual(engine.cells,loaded.cells);self.assertEqual(engine.deadline,loaded.deadline)
            self.assertEqual(engine.solution,loaded.solution)
    def test_timer_cannot_be_reset_by_resume(self):
        engine=NETWORK_TYPES['pipe_connector']();engine.deadline=time.time()-1
        loaded=type(engine).load(json.loads(json.dumps(engine.dump())))
        with self.assertRaises(ValueError):loaded.move('A1')
        self.assertTrue(loaded.done);self.assertIn('Water arrived',loaded.result)
    def test_rotation_and_coordinate_validation(self):
        self.assertEqual(rotate(1,4),1);self.assertEqual(rotate(1),2)
        for factory in NETWORK_TYPES.values():
            engine=factory()
            for text in ['Z99','A0','A1 9','bad','A1 1 extra']:
                before=copy.deepcopy(engine.cells)
                with self.assertRaises(ValueError):engine.move(text)
                self.assertEqual(before,engine.cells)
    def test_mirrors_walls_and_loops_are_bounded(self):
        engine=NETWORK_TYPES['laser_locks']();engine.cells=[[0]*engine.size for _ in range(engine.size)];engine.cells[0][0]=3
        self.assertFalse(engine.beam()[1])
        with self.assertRaises(ValueError):engine.move('A6')
        engine.cells=[[1]*engine.size for _ in range(engine.size)];self.assertLessEqual(len(engine.beam()[0]),4*engine.size**2)
    def test_network_presentations_never_include_solutions_or_seeds(self):
        for kind,factory in NETWORK_TYPES.items():
            g=game(kind,factory(size='large'));data=presentation(g)
            self.assertNotIn('solution',data);self.assertNotIn('seed',data)
            png=render(data);self.assertEqual(Image.open(io.BytesIO(png)).size,(960,760))

class NewInteractions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3');self.store.set_option(1,'feature:games',True)
        self.service=NS(store=self.store,bot=NS(user=NS(id=99)),need=AsyncMock(return_value=True),productivity=NS(error=lambda *a:None))
        self.hub=GameHub(self.service)
        self.i=NS(user=NS(id=10),guild_id=1,response=NS(is_done=lambda:False,defer=AsyncMock(),send_message=AsyncMock()),followup=NS(send=AsyncMock(return_value=NS(edit=AsyncMock()))))
    async def asyncTearDown(self):await self.hub.close();self.store.close();self.tmp.cleanup()
    async def start(self,kind,opponent=None,**kwargs):
        with patch.object(self.hub,'card',new=AsyncMock(return_value={'content':'Safe preview'})):
            await self.hub.start(self.i,kind,opponent,**kwargs)
        return self.hub.sessions[(1,10)]
    async def test_default_vivi_opponent_and_pvp_consent(self):
        g=await self.start('blackjack');self.assertTrue(g['vs_vivi']);self.assertEqual(g['players'],[10,99]);self.hub.sessions.clear()
        g=await self.start('go_fish',NS(id=20,bot=False));self.assertFalse(g['accepted']);self.assertFalse(g.get('vs_vivi',False))
        with patch.object(g['engine'],'move') as move:await self.hub.move(self.i,'A');move.assert_not_called()
        self.i.user.id=20;self.i.response.edit_message=AsyncMock()
        with patch.object(self.hub,'update',new=AsyncMock()):await GameView(self.hub,g['key'],True).children[0].callback(self.i)
        self.assertTrue(g['accepted'])
    async def test_vivi_can_play_multiple_members(self):
        await self.start('blackjack');self.i.user.id=11
        with patch.object(self.hub,'card',new=AsyncMock(return_value={'content':'Safe preview'})):await self.hub.start(self.i,'go_fish',NS(id=99,bot=True))
        self.assertEqual(len(self.hub.sessions),2)
    async def test_blackjack_ai_and_chip_settlement_once(self):
        g=await self.start('blackjack');g['engine'].hands=[['AH','KS'],['9C','8S']]
        with patch.object(self.hub,'update',new=AsyncMock()),patch.object(self.hub,'card',new=AsyncMock(return_value={'content':'Private hand'})):
            await self.hub.move(self.i,'stand')
        self.assertTrue(g['engine'].done);self.assertNotIn(g['key'],self.hub.sessions)
        self.hub.settle_cards(g);self.assertEqual(self.store.profile(1,10)['arcade_cards']['blackjack'],{'played':1,'wins':1,'chips':10})
        self.assertNotIn('arcade_cards',self.store.profile(1,99))
    async def test_large_map_controls_fit_component_limits(self):
        g=await self.start('circuit_repair',size='large')
        for view in [GameView(self.hub,g['key']),CoordinateView(self.hub,g['key'],10,14)]:
            self.assertLessEqual(len(view.children),25)
            for row in view.to_components():self.assertLessEqual(len(row['components']),5)
        row=CoordinateView(self.hub,g['key'],10,14);self.i.user.id=55
        with patch.object(self.hub,'move',new=AsyncMock()) as move:await row.children[0].callback(self.i);move.assert_not_awaited()
    async def test_network_progress_resumes_and_expired_pipe_finishes(self):
        g=await self.start('pipe_connector',size='large',difficulty='hard');seed=g['engine'].seed;deadline=g['engine'].deadline;self.hub.sessions.clear()
        g=await self.start('pipe_connector');self.assertEqual(g['engine'].seed,seed);self.assertEqual(g['engine'].deadline,deadline)
        g['engine'].deadline=time.time()-1
        with patch.object(self.hub,'finish',new=AsyncMock()):await self.hub.tick()
        self.assertNotIn(g['key'],self.hub.sessions);self.assertIsNone(self.store.record('puzzle:1:10:pipe_connector'))
