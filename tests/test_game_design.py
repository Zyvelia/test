"""Image privacy boundaries, game controls and final-state presentation."""
import asyncio
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock,patch
import discord
from PIL import Image
from vivi.games.game_design import presentation,legacy_presentation,render,payload,embed,THEMES
from vivi.games.game_engines import Chess,Checkers,ConnectFour,Memory,Hangman,Sudoku,Battleship,TicTacToe
from vivi.games.more_games import Reversi,Minesweeper,WordSearch,Crossword,Spelling
from vivi.games.game_hub import GameHub,GameView,CoordinateView
from vivi.core.storage import Store

FACTORIES=dict(chess=Chess,checkers=Checkers,connect_four=ConnectFour,memory=Memory,hangman=Hangman,sudoku=Sudoku,battleship=Battleship,reversi=Reversi,minesweeper=Minesweeper,word_search=WordSearch,crossword=Crossword,spelling=Spelling,tictactoe=TicTacToe)
def game(kind,engine=None):return dict(key=(1,10),kind=kind,engine=engine or FACTORIES[kind](),players=[10,20] if kind in {'chess','checkers','connect_four','battleship','reversi','tictactoe'} else [10],accepted=True,theme='velvet',expires=time.time()+300,ready=True)

class DesignPrivacy(unittest.TestCase):
 def test_every_engine_has_a_portable_png_card(self):
  for kind in FACTORIES:
   data=presentation(game(kind));body=render(data)
   with Image.open(io.BytesIO(body)) as image:self.assertEqual(image.size,(960,760));self.assertEqual(image.mode,'RGB')
   self.assertLess(len(body),1024*1024)
 def test_themes_are_visually_distinct(self):
  data=presentation(game('connect_four'));images=[render(dict(data,theme=name)) for name in THEMES];self.assertEqual(len(set(images)),len(THEMES))
 def test_public_battleship_never_contains_either_fleet(self):
  g=game('battleship');before=presentation(g);self.assertNotIn('own',before);self.assertNotIn('target',before)
  g['engine'].fleets=[{(0,0)},{(5,5)}];after=presentation(g);self.assertEqual(before,after);self.assertEqual(render(before),render(after))
 def test_private_battleship_target_hides_unshot_enemy_ships(self):
  g=game('battleship');g['engine'].fleets=[{(0,0)},{(1,1)}];before=presentation(g,10)
  self.assertEqual(before['own'][0][0],'ship');self.assertTrue(all(x is None for row in before['target'] for x in row))
  g['engine'].fleets[1]={(5,5)};self.assertEqual(before,presentation(g,10))
  with self.assertRaises(ValueError):presentation(g,99)
 def test_hidden_memory_cards_are_removed_before_rendering(self):
  g=game('memory');before=presentation(g);g['engine'].cards.reverse();self.assertEqual(before,presentation(g))
  self.assertTrue(all(cell['face'] is None for row in before['grid'] for cell in row))
  g['engine'].shown=[0];shown=presentation(g);self.assertIsNotNone(shown['grid'][0][0]['face']);self.assertIsNone(shown['grid'][0][1]['face'])
 def test_unrevealed_mines_do_not_enter_presentation(self):
  g=game('minesweeper');before=presentation(g);g['engine'].mines=[0,1,2,3,4,5];self.assertEqual(before,presentation(g))
  self.assertNotIn('mine',json.dumps(before['grid']))
 def test_hangman_secret_stays_hidden_until_revealed(self):
  g=game('hangman');g['engine'].word='planet';before=presentation(g);g['engine'].word='silver';self.assertEqual(before,presentation(g))
  self.assertNotIn('silver',json.dumps(before));g['engine'].done=True;self.assertEqual(''.join(presentation(g)['letters']),'SILVER')
 def test_spelling_and_crossword_answers_are_not_serialized(self):
  self.assertNotIn('garden',json.dumps(presentation(game('spelling'))).lower())
  data=presentation(game('crossword'));self.assertEqual(data['grid'][0][0],'');self.assertNotIn('answers',data)
 def test_sudoku_solution_is_not_serialized(self):
  data=presentation(game('sudoku'));self.assertNotIn('solution',data);self.assertEqual(len(data['grid']),9)
 def test_anagram_secret_and_live_scores_stay_private(self):
  g=dict(kind='anagram',players=[10,20],round=1,rounds=5,word='planet',scramble='telnap',scores={10:29,20:0},shown_scores={10:0,20:0},deadline=time.time()+10)
  data=presentation(g);self.assertNotIn('planet',json.dumps(data));self.assertEqual(data['scores'],[('Player 1',0),('Player 2',0)])
  g['finished']=True;self.assertEqual(presentation(g)['scores'][0][1],29)
 def test_trivia_correct_answer_is_hidden_until_completion(self):
  view=NS(trivia=('Question',['First','Second'],1),done=False,turn=0,players=[10]);data=legacy_presentation(view);self.assertIsNone(data['correct'])
  view.done=True;self.assertEqual(legacy_presentation(view)['correct'],1)
  public=embed(data).to_dict();self.assertIn('Question',public['description']);self.assertTrue(any(x['name']=='Answers' for x in public['fields']))
 def test_tictactoe_engine_enforces_turns_and_wins(self):
  g=TicTacToe()
  for move in ['A3','B3','A2','B2','A1']:g.move(move)
  self.assertTrue(g.done);self.assertIn('Player 1',g.result)
  with self.assertRaises(ValueError):g.move('A3')

class ArcadeInteractions(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'vivi.sqlite3');self.store.set_option(1,'feature:games',True)
  self.service=NS(store=self.store,bot=NS(),need=AsyncMock(return_value=True),productivity=NS(error=lambda *args:None));self.hub=GameHub(self.service)
  self.i=NS(user=NS(id=10),guild_id=1,response=NS(is_done=lambda:False,defer=AsyncMock(),send_message=AsyncMock(),edit_message=AsyncMock()),followup=NS(send=AsyncMock(return_value=NS(edit=AsyncMock()))),data={'values':['C4']})
 async def asyncTearDown(self):await self.hub.close();self.store.close();self.tmp.cleanup()
 def active(self,kind):
  g=game(kind);g['message']=NS(edit=AsyncMock());self.hub.sessions[g['key']]=g;return g
 async def test_start_sends_embed_png_with_accessibility_description(self):
  await self.hub.start(self.i,'word_search');kwargs=self.i.followup.send.call_args.kwargs
  self.assertIsInstance(kwargs['embed'],discord.Embed);self.assertEqual(kwargs['file'].filename,'vivi-game.png');self.assertIn('Text board',kwargs['file'].description);kwargs['file'].close()
 async def test_reversi_quick_move_rejects_an_outsider(self):
  g=self.active('reversi');view=GameView(self.hub,g['key']);menu=next(x for x in view.children if isinstance(x,discord.ui.Select));self.i.user.id=99
  with patch.object(self.hub,'move',new=AsyncMock()) as move:await menu.callback(self.i);move.assert_not_awaited()
 async def test_private_coordinate_controls_are_owner_bound(self):
  g=self.active('minesweeper');view=CoordinateView(self.hub,g['key'],10,4);self.i.user.id=99
  with patch.object(self.hub,'move',new=AsyncMock()) as move:await view.children[-1].callback(self.i);move.assert_not_awaited()
 async def test_mine_flag_mode_uses_selected_coordinate(self):
  g=self.active('minesweeper');view=CoordinateView(self.hub,g['key'],10,4);await view.children[1].callback(self.i)
  with patch.object(self.hub,'move',new=AsyncMock()) as move:await view.children[3].callback(self.i);move.assert_awaited_once_with(self.i,'flag A4')
 async def test_mine_row_picker_response_is_private(self):
  g=self.active('minesweeper');view=GameView(self.hub,g['key']);menu=next(x for x in view.children if isinstance(x,discord.ui.Select));self.i.data={'values':['4']};await menu.callback(self.i)
  self.assertTrue(self.i.response.send_message.call_args.kwargs['ephemeral']);self.assertIsInstance(self.i.response.send_message.call_args.kwargs['view'],CoordinateView)
 async def test_component_rows_fit_discord_limits(self):
  for kind in FACTORIES:
   g=self.active(kind);view=GameView(self.hub,g['key']);self.assertLessEqual(len(view.children),25)
   for row in view.to_components():self.assertLessEqual(len(row['components']),5)
 async def test_board_text_mode_does_not_render_an_image(self):
  g=self.active('battleship');await self.hub.send_board(self.i,g,'text');self.i.followup.send.assert_not_awaited();self.assertIn('Your fleet',self.i.response.send_message.call_args.args[0])
 async def test_board_images_are_ephemeral(self):
  g=self.active('battleship');await self.hub.send_board(self.i,g);kwargs=self.i.followup.send.call_args.kwargs;self.assertTrue(kwargs['ephemeral']);self.assertTrue(any(x.name=='Private board' for x in kwargs['embed'].fields));kwargs['file'].close()
 async def test_update_replaces_old_attachments(self):
  g=self.active('chess');await self.hub.update(g);kwargs=g['message'].edit.call_args.kwargs;self.assertEqual(len(kwargs['attachments']),1);self.assertIsNone(kwargs['content']);kwargs['attachments'][0].close()
 async def test_old_game_removed_during_render_cannot_receive_new_controls(self):
  g=self.active('chess')
  async def delayed_card(game):self.hub.sessions.pop(game['key']);return dict(content='Stale')
  with patch.object(self.hub,'card',side_effect=delayed_card):await self.hub.update(g)
  g['message'].edit.assert_not_awaited()
 async def test_render_failure_falls_back_to_text(self):
  g=self.active('chess')
  with patch('vivi.games.game_hub.payload',side_effect=OSError('Missing asset')):options=await self.hub.card(g)
  self.assertTrue(g['text_only']);self.assertIn('content',options)
 async def test_missing_attachment_permissions_fall_back_without_losing_game(self):
  forbidden=discord.Forbidden(NS(status=403,reason='Forbidden'),'No attachments');message=NS(edit=AsyncMock());self.i.followup.send.side_effect=[forbidden,message]
  await self.hub.start(self.i,'hangman');g=self.hub.sessions[(1,10)];self.assertTrue(g['text_only']);self.assertTrue(g['ready']);self.assertIs(g['message'],message)
 async def test_tictactoe_win_retains_existing_achievement(self):
  g=self.active('tictactoe');self.service.reward=MagicMock()
  for user,move in [(10,'A3'),(20,'B3'),(10,'A2'),(20,'B2'),(10,'A1')]:
   self.i.user.id=user;await self.hub.move(self.i,move)
  self.service.reward.assert_called_once_with(1,10,0,'Tic-tac-toe winner');self.assertNotIn(g['key'],self.hub.sessions)
 async def test_initial_render_cancelled_before_send_does_not_post_an_active_game(self):
  async def cancel(game,viewer=None):self.hub.sessions.pop(game['key']);return dict(content='Cancelled')
  with patch.object(self.hub,'card',side_effect=cancel):await self.hub.start(self.i,'hangman')
  self.i.followup.send.assert_not_awaited()
 async def test_declined_challenge_replaces_the_waiting_card(self):
  g=self.active('chess');g['accepted']=False;view=GameView(self.hub,g['key'],True);self.i.user.id=20;await view.children[1].callback(self.i)
  self.assertNotIn(g['key'],self.hub.sessions);kwargs=g['message'].edit.call_args.kwargs;self.assertEqual(kwargs['embed'].description,'Challenge declined.');self.assertIsNone(kwargs['view']);kwargs['attachments'][0].close()
 async def test_completed_trivia_is_not_overwritten_by_timeout(self):
  from vivi.server.community import GameView as TriviaView
  self.service.reward=MagicMock();view=TriviaView(self.service,10,trivia=('Question',['First','Second'],0));view.message=NS(edit=AsyncMock())
  await view.play(self.i,0);await view.on_timeout();view.message.edit.assert_not_awaited()
  self.i.response.edit_message.call_args.kwargs['attachments'][0].close()
 async def test_finished_game_card_clears_interactive_view(self):
  g=self.active('tictactoe');g['engine'].done=True;g['engine'].result='Draw!';await self.hub.update(g);self.assertIsNone(g['message'].edit.call_args.kwargs['view']);g['message'].edit.call_args.kwargs['attachments'][0].close()
