import asyncio
import copy
import datetime as dt
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from aiohttp import web
from vivi.bot import ViviBot,register_commands
from vivi.server.community import register_extra
from vivi.server.operations import register_operations,subscription
from vivi.server.productivity import register_productivity
from vivi.server.customization import register_customization
from vivi.server.suite import register_suite,remove_warning,review_access,reminder_time,ticket_event,timeline,LFGView
from vivi.games.game_hub import register_games,GameView
from vivi.games.game_engines import ConnectFour,Chess,Checkers,Hangman,Memory,Sudoku,Battleship,solutions
from vivi.core.storage import Store
from vivi.site.studio_layout import DEFAULT_LAYOUT,validate_layout,render_layout,validate_announcement,announcement_embed
from vivi.site.dashboard import Dashboard
from vivi.core.a11y import audit_html
from vivi.core.updates import check_updates,version

class GameRules(unittest.TestCase):
 def test_connect_four_vertical_win_and_turns(self):
  game=ConnectFour()
  for text in ['1','2','1','2','1','2','1']: game.move(text)
  self.assertTrue(game.done); self.assertEqual(game.result,'Player 1 wins!')
 def test_full_column_and_invalid_moves_leave_board(self):
  game=ConnectFour()
  for _ in range(6): game.move('1')
  before=copy.deepcopy(game.cells)
  for text in ['1','0','8','hello']:
   with self.assertRaises(ValueError): game.move(text)
  self.assertEqual(before,game.cells)
 def test_connect_four_horizontal_and_diagonal(self):
  for coords in [[(5,0),(5,1),(5,2)],[(5,0),(4,1),(3,2)]]:
   game=ConnectFour()
   for r,c in coords:game.cells[r][c]=1
   if coords[1][0]==4:
    for r in [3,4,5]:game.cells[r][3]=2
   game.move('4');self.assertTrue(game.done)
 def test_chess_turn_and_illegal_move(self):
  game=Chess();game.move('e4');self.assertEqual(game.turn,1)
  before=game.position.fen()
  with self.assertRaises(ValueError):game.move('e4')
  self.assertEqual(before,game.position.fen());game.move('e7e5');game.move('Nf3')
 def test_chess_fools_mate(self):
  game=Chess()
  for text in ['f3','e5','g4','Qh4#']:game.move(text)
  self.assertTrue(game.done);self.assertEqual(game.result,'Player 2 wins!')
 def test_chess_castling_en_passant_and_promotion(self):
  game=Chess()
  for text in ['e4','a6','e5','d5','exd6']:game.move(text)
  self.assertEqual(game.position.piece_at(43).symbol(),'P');self.assertIsNone(game.position.piece_at(35))
  game=Chess()
  for text in ['e4','e5','Nf3','Nc6','Bc4','Nf6','O-O']:game.move(text)
  self.assertEqual(game.position.king(True),6)
  import chess
  game=Chess();game.position=chess.Board('7k/P7/8/8/8/8/8/7K w - - 0 1');game.move('a7a8q');self.assertEqual(game.position.piece_at(56).symbol(),'Q')
 def test_draw_claim_rejected_unless_valid(self):
  game=Chess()
  with self.assertRaises(ValueError):game.move('draw')
 def test_checkers_forced_multi_capture_is_atomic(self):
  game=Checkers();game.cells={(2,1):(0,False),(3,2):(1,False),(5,4):(1,False),(0,1):(0,False)}
  before=game.cells.copy()
  for move in ['b6-a5','b6-d4','b8-a7']:
   with self.assertRaises(ValueError):game.move(move)
   self.assertEqual(game.cells,before)
  game.move('b6-d4-f2');self.assertEqual(game.cells[(6,5)],(0,False));self.assertTrue(game.done)
 def test_checkers_crowning_ends_turn(self):
  game=Checkers();game.cells={(5,0):(0,False),(6,1):(1,False),(6,3):(1,False)}
  game.move('a3-c1');self.assertEqual(game.cells[(7,2)],(0,True));self.assertEqual(game.turn,1)
 def test_checkers_backward_man_capture_rejected(self):
  game=Checkers();game.cells={(4,3):(0,False),(3,2):(1,False)}
  with self.assertRaises(ValueError):game.move('d4-b6')
 def test_hangman_duplicate_and_wrong_word(self):
  game=Hangman();game.word='planet';game.move('p')
  with self.assertRaises(ValueError):game.move('p')
  game.move('wrong');self.assertEqual(game.errors,1);game.move('planet');self.assertTrue(game.done)
 def test_memory_mismatch_and_match(self):
  game=Memory();game.cards=list('abcdefghabcdefgh');game.move('a4');game.move('b4');self.assertEqual(len(game.shown),2)
  with self.assertRaises(ValueError):game.move('c4')
  game.shown=[];game.move('a4');game.move('a2');self.assertEqual(game.matched,{0,8})
 def test_sudoku_unique_and_clues_immutable(self):
  for difficulty in ['easy','medium','hard']:
   game=Sudoku(difficulty);self.assertEqual(solutions(game.cells[:]),1)
   n=next(iter(game.clues));r,c=divmod(n,9)
   with self.assertRaises(ValueError):game.move(f'{chr(97+c)}{9-r}=0')
   for n in set(range(81))-game.clues:
    r,c=divmod(n,9);game.move(f'{chr(97+c)}{9-r}={game.solution[n]}')
   self.assertTrue(game.done)
 def test_battleship_fleets_unique_and_private(self):
  game=Battleship();self.assertEqual([len(x) for x in game.fleets],[7,7]);game.move('A1');self.assertEqual(game.turn,1)
  self.assertEqual(game.board(0).split('Your shots:')[0].count('S')+game.board(0).split('Your shots:')[0].count('X'),7)
  game.move('B1')
  with self.assertRaises(ValueError):game.move('A1')
 def test_battleship_win(self):
  game=Battleship();game.fleets=[{(0,0)},{(5,0)}];game.move('A1');self.assertTrue(game.done)

class PurePolicies(unittest.TestCase):
 def test_relative_reminder_and_range(self):
  now=dt.datetime(2030,1,1,tzinfo=dt.timezone.utc)
  self.assertEqual(reminder_time('in 2h',now=now),now.timestamp()+7200)
  for text in ['0m','2030-01-01T00:00Z','800d','nonsense']:
   with self.assertRaises(ValueError):reminder_time(text,now=now)
 def test_dst_requires_offset(self):
  now=dt.datetime(2026,1,1,tzinfo=dt.timezone.utc)
  for text in ['2026-03-08T02:30','2026-11-01T01:30']:
   with self.assertRaises(ValueError):reminder_time(text,'America/New_York',now)
  self.assertGreater(reminder_time('2026-11-01T01:30-05:00','America/New_York',now),now.timestamp())
 def test_welcome_validation_and_png(self):
  layout=copy.deepcopy(DEFAULT_LAYOUT);validate_layout(layout)
  self.assertTrue(render_layout(layout,'Name','Server','Hello').startswith(bytes.fromhex('89504e47')))
  for key,value in [('x',-1),('size',1000),('color','red;evil'),('type','url')]:
   invalid=copy.deepcopy(layout);invalid['elements'][0][key]=value
   with self.assertRaises(ValueError):validate_layout(invalid)
 def test_announcement_order_and_bounds(self):
  blocks=[dict(type='title',value='News'),dict(type='field',name='When',value='Tomorrow'),dict(type='text',value='See you!')]
  embed=announcement_embed(blocks);self.assertLess(embed.description.index('When'),embed.description.index('See you'))
  for invalid in [[],[dict(type='html',value='<script>')],[dict(type='text',value='x'*1501)],list(reversed(blocks))]:
   with self.assertRaises(ValueError):validate_announcement(invalid)
 def test_static_audit_finds_real_issues(self):
  findings=audit_html('<h1>X</h1><h3>Y</h3><input name="secret"><img src="x"><p id="a"></p><p id="a"></p>')
  self.assertTrue(any('label' in x for x in findings));self.assertTrue(any('Duplicate' in x for x in findings));self.assertTrue(any('Heading' in x for x in findings))
  self.assertEqual(audit_html('<main><nav aria-label="Main"><a href="/">Home</a></nav><h1>X</h1><label for="x">Name</label><input id="x"><div role="status"></div><img alt=""></main>'),[])
 def test_steam_source_is_numeric_only(self):
  self.assertEqual(subscription('steam','730',1)['source'],'730')
  for value in ['https://evil','../1','0','1?x=2']:
   with self.assertRaises(ValueError):subscription('steam',value,1)
 def test_release_versions(self):
  self.assertGreater(version('v1.2.0'),version('1.1.9'));self.assertIsNone(version('nightly'))

class StorePolicies(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data/vivi.sqlite3')
 def tearDown(self):self.store.close();self.tmp.cleanup()
 def test_warning_removal_audited_and_scoped(self):
  ident=self.store.warn(1,10,20,'Original reason')
  with self.assertRaises(ValueError):remove_warning(self.store,2,ident,30,'Wrong server')
  case=remove_warning(self.store,1,ident,30,'Mistaken identity')
  self.assertEqual(len(self.store.warnings(1,10)),0)
  reason=self.store.db.execute('SELECT reason FROM cases WHERE id=?',(case,)).fetchone()[0]
  for text in ['Original reason','Mistaken identity','20']:self.assertIn(text,reason)
 def test_warning_audit_failure_rolls_back(self):
  ident=self.store.warn(1,10,20,'Keep this')
  self.store.db.execute("CREATE TRIGGER reject_case BEFORE INSERT ON cases BEGIN SELECT RAISE(ABORT,'reject'); END")
  with self.assertRaises(Exception):remove_warning(self.store,1,ident,30,'Correction')
  self.assertEqual(len(self.store.warnings(1,10)),1)
 def test_independent_review_conflicts(self):
  row=dict(guild=1,data=dict(author=10,target=20));self.store.set_option(1,'reviewer_role',40)
  for uid in [10,20]:self.assertFalse(review_access(NS(id=uid,guild_permissions=NS(administrator=True),roles=[]),row,self.store))
  self.assertTrue(review_access(NS(id=30,guild_permissions=NS(administrator=False),roles=[NS(id=40)]),row,self.store))
  self.assertFalse(review_access(NS(id=31,guild_permissions=NS(administrator=False),roles=[]),row,self.store))
 def test_ticket_timeline_owner_scope_and_retention(self):
  self.store.add_ticket(1,10,100);ticket_event(self.store,1,100,20,'opened','General');self.store.remove_ticket(100);ticket_event(self.store,1,100,20,'closed','Done')
  self.assertIn('closed',timeline(self.store,1,100,10))
  for guild,user in [(1,11),(2,10)]:
   with self.assertRaises(ValueError):timeline(self.store,guild,100,user)
 def test_ticket_event_cap(self):
  self.store.add_ticket(1,10,100)
  for n in range(205):ticket_event(self.store,1,100,20,'tag',str(n))
  self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM ticket_events').fetchone()[0],200)

class SuiteInteractions(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data/vivi.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__()
  register_commands(self.bot);register_extra(self.bot);register_operations(self.bot);register_productivity(self.bot);register_customization(self.bot);register_suite(self.bot);register_games(self.bot)
  self.service=self.bot.community;self.suite=self.service.suite
  self.member=MagicMock(spec=discord.Member);self.member.id=10;self.member.bot=False;self.member.roles=[];self.member.guild_permissions=discord.Permissions.all();self.member.send=AsyncMock()
  self.guild=NS(id=1,name='Example',get_member=lambda uid:self.member if uid==10 else None,fetch_member=AsyncMock(return_value=self.member),get_channel=lambda channel:None)
  self.bot.get_guild=lambda gid:self.guild if gid==1 else None
  self.i=NS(user=self.member,guild=self.guild,guild_id=1,channel_id=100,response=NS(is_done=lambda:False,send_message=AsyncMock(),defer=AsyncMock(),edit_message=AsyncMock(),send_modal=AsyncMock()),followup=NS(send=AsyncMock()))
 async def asyncTearDown(self):await self.bot.close();self.store.close();self.tmp.cleanup()
 async def call(self,group,command_name,**kwargs):return await self.bot.tree.get_command(group).get_command(command_name).callback(self.i,**kwargs)
 async def test_all_commands_fit_discord_limits(self):
  self.assertIn('cases',[x.name for x in self.bot.tree.get_commands()])
  for group in self.bot.tree.get_commands():
   if isinstance(group,discord.app_commands.Group):self.assertLessEqual(len(group.commands),25)
 async def test_reminders_private_durable_and_retried(self):
  self.store.set_option(1,'feature:reminders',True)
  ident=self.store.put_record(1,'reminder',dict(user=10,text='Remember',due=time.time()-60,status='pending'))
  await self.suite.tick();self.member.send.assert_awaited_once();self.assertIsNone(self.store.record(ident));self.assertFalse(self.member.send.call_args.kwargs['allowed_mentions'].everyone)
 async def test_reminder_failures_backoff_and_no_public_fallback(self):
  self.store.set_option(1,'feature:reminders',True)
  self.member.send.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'DMs closed')
  ident=self.store.put_record(1,'reminder',dict(user=10,text='Private',due=1,status='pending',attempts=2))
  await self.suite.tick();self.assertEqual(self.store.record(ident)['data']['status'],'failed')
 async def test_disabled_reminders_pause(self):
  ident=self.store.put_record(1,'reminder',dict(user=10,text='Private',due=1,status='pending'))
  await self.suite.tick();self.member.send.assert_not_awaited();self.assertIsNotNone(self.store.record(ident))
 async def test_reminder_cancellation_denies_other_members(self):
  ident=self.store.put_record(1,'reminder',dict(user=99,text='Secret',due=1,status='pending'))
  await self.call('social','reminder_cancel',reminder_id=ident);self.assertIsNotNone(self.store.record(ident))
 async def test_timezone_default_private_and_opt_out_while_disabled(self):
  await self.call('social','timezone',zone='Europe/London')
  self.assertFalse(self.store.profile(1,10)['directory_optin'])
  self.store.set_option(1,'feature:timezone_directory',True)
  await self.call('social','timezone',zone='Europe/London',public=True);self.assertTrue(self.store.profile(1,10)['directory_optin'])
  self.store.set_option(1,'feature:timezone_directory',False)
  await self.call('social','timezone',zone='Europe/London',public=False);self.assertFalse(self.store.profile(1,10)['directory_optin'])
 async def test_favorites_are_personal_and_validated(self):
  await self.call('social','favorite',command='social reminders');self.assertEqual(self.store.profile(1,10)['favorites'],['social reminders']);self.assertNotIn('favorites',self.store.profile(1,99))
  await self.call('social','favorite',command='nonexistent');self.assertEqual(len(self.store.profile(1,10)['favorites']),1)
 async def test_evidence_cross_server_and_permissions(self):
  self.store.put_record(2,'case_evidence',dict(case=1),'evidence')
  await self.call('cases','evidence_get',evidence_id='evidence');self.assertNotIn('file',self.i.response.send_message.call_args.kwargs)
  self.member.guild_permissions=discord.Permissions.none();await self.call('cases','evidence_get',evidence_id='evidence');self.assertNotIn('file',self.i.response.send_message.call_args.kwargs)
 async def test_evidence_round_trip_and_integrity(self):
  self.store.set_option(1,'feature:moderation',True);case=self.store.add_case(1,99,10,'warn','Reason')
  attachment=NS(filename='proof.txt',size=4,read=AsyncMock(return_value=b'Note'))
  await self.call('cases','evidence_add',case_id=case,attachment=attachment,note='Context')
  row=self.store.records(1,'case_evidence')[0];self.assertEqual(row['data']['note'],'Context')
  await self.call('cases','evidence_get',evidence_id=row['id']);file=self.i.response.send_message.call_args.kwargs['file'];self.assertEqual(file.fp.read(),b'Note');file.close()
  path=self.store.path.parent/'evidence'/'1'/str(case)/(row['id']+'.txt');path.write_bytes(b'Changed')
  self.i.response.send_message.reset_mock();await self.call('cases','evidence_get',evidence_id=row['id']);self.assertNotIn('file',self.i.response.send_message.call_args.kwargs)
 async def test_lfg_join_capacity_and_authorization(self):
  self.store.set_option(1,'feature:lfg',True)
  ident=self.store.put_record(1,'lfg',dict(owner=99,members=[99],slots=2,expires=time.time()+60,game='Game',description='Fun',availability='Evening'))
  view=LFGView(self.suite,ident);await view.click(self.i,'Join');self.assertEqual(self.store.record(ident)['data']['members'],[99,10])
  self.member.id=11;await view.click(self.i,'Join');self.assertEqual(len(self.store.record(ident)['data']['members']),2)
  self.member.guild_permissions=discord.Permissions.none();await view.click(self.i,'Close');self.assertFalse(self.store.record(ident)['data'].get('closed',False))
 async def test_game_turn_and_hidden_public_board(self):
  hub=self.service.games;engine=Battleship();key=(1,10);message=NS(edit=AsyncMock())
  game=dict(key=key,kind='battleship',engine=engine,players=[10,99],accepted=True,message=message,expires=time.time()+60);hub.sessions[key]=game
  self.assertNotIn('Your fleet',hub.public(game));self.assertIn('Your fleet',hub.private(game,10))
  self.store.set_option(1,'feature:games',True);self.member.id=99
  await hub.move(self.i,'A1');self.assertEqual(engine.shots[1],set())
 async def test_accepted_blocklist_appeal_keeps_decision_history(self):
  self.store.put_record(1,'blocklist',dict(user=99,active=True,history=[]),'blocklist:1:99')
  ident=self.store.put_record(1,'blocklist_appeal',dict(author=99,target=99,status='pending',history=[],incident='Appeal',context='Context'))
  await self.call('cases','review',review_id=ident,status='accepted',reason='Evidence supports removal')
  self.assertFalse(self.store.record('blocklist:1:99')['data']['active']);self.assertEqual(self.store.record(ident)['data']['history'][0]['actor'],10)
  self.i.response.send_message.call_args.kwargs['file'].close()
  await self.call('cases','review',review_id=ident,status='declined',reason='A later change')
  self.assertEqual(self.store.record(ident)['data']['status'],'accepted')
 async def test_accused_admin_cannot_read_or_decide_conduct_review(self):
  ident=self.store.put_record(1,'staff_conduct',dict(author=99,target=10,status='pending',history=[],incident='Private complaint',context='Context'))
  await self.call('cases','review',review_id=ident,status='accepted',reason='Self review')
  self.assertEqual(self.store.record(ident)['data']['status'],'pending');self.assertNotIn('file',self.i.response.send_message.call_args.kwargs)
 async def test_lfg_concurrent_join_cannot_overfill(self):
  self.store.set_option(1,'feature:lfg',True)
  ident=self.store.put_record(1,'lfg',dict(owner=99,members=[99],slots=2,expires=time.time()+60,game='Game',description='Fun',availability='Evening'))
  view=LFGView(self.suite,ident)
  other=NS(user=NS(id=11),guild=self.guild,guild_id=1,response=NS(edit_message=AsyncMock(),is_done=lambda:False,send_message=AsyncMock()))
  await asyncio.gather(view.click(self.i,'Join'),view.click(other,'Join'))
  self.assertEqual(len(self.store.record(ident)['data']['members']),2)
 async def test_stale_modal_cannot_move_replacement_game(self):
  from vivi.games.game_hub import MoveModal
  hub=self.service.games;key=(1,10);hub.sessions[key]=dict(kind='hangman',players=[10],engine=Hangman())
  modal=MoveModal(hub,key);hub.sessions[key]=dict(kind='hangman',players=[10],engine=Hangman())
  await modal.on_submit(self.i);self.assertEqual(hub.sessions[key]['engine'].guesses,set())
 async def test_memory_buttons_fit_components(self):
  hub=self.service.games;key=(1,10);hub.sessions[key]=dict(kind='memory',engine=Memory(),players=[10])
  view=GameView(hub,key);self.assertEqual(len(view.children),19);self.assertLessEqual(max(x.row or 0 for x in view.children),4)
 async def test_anagram_timed_rounds_and_score(self):
  hub=self.service.games;key=(1,10);g=dict(key=key,kind='anagram',players=[10,99],scores={10:0,99:0},round=0,rounds=2,words=['planet','forest'],expires=time.time()+60,accepted=True,message=NS(edit=AsyncMock()))
  self.store.set_option(1,'feature:games',True);hub.sessions[key]=g;hub.next_round(g)
  await hub.move(self.i,'planet');self.assertGreater(g['scores'][10],0);before=g['scores'][10];await hub.move(self.i,'planet');self.assertEqual(g['scores'][10],before)
  g['deadline']=1;await hub.tick();self.assertEqual(g['round'],2);g['deadline']=1;await hub.tick();self.assertNotIn(key,hub.sessions)
 async def test_steam_fixed_endpoint_fixture(self):
  response=NS(status=200,json=AsyncMock(return_value={'appnews':{'newsitems':[dict(gid='1',title='Update',url='https://store.steampowered.com/news/app/730')]}}))
  cm=MagicMock();cm.__aenter__=AsyncMock(return_value=response);cm.__aexit__=AsyncMock();self.service.session=NS(get=MagicMock(return_value=cm),close=AsyncMock())
  events=await self.service.operations.events(subscription('steam','730',100));self.assertEqual(events[0]['id'],'1');self.assertTrue(self.service.session.get.call_args.args[0].startswith('https://api.steampowered.com/'))
 async def test_release_404_and_cached_latest(self):
  response=NS(status=404);cm=MagicMock();cm.__aenter__=AsyncMock(return_value=response);cm.__aexit__=AsyncMock();self.service.session=NS(get=MagicMock(return_value=cm),close=AsyncMock())
  result=await check_updates(self.service);self.assertIn('no published release',result);await check_updates(self.service);self.assertEqual(self.service.session.get.call_count,1)

class StudioActions(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data/vivi.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__();self.dashboard=Dashboard(self.bot.community)
  self.session={'user_id':10,'csrf':'test','expires':time.time()+60};self.guild=NS(id=1,name='<Server>',text_channels=[],categories=[],roles=[],me=None,get_channel=lambda channel:None)
  self.bot.get_guild=lambda gid:self.guild if gid==1 else None
  self.dashboard.session=lambda request:self.session;self.dashboard.authorize=AsyncMock(return_value=self.session)
 async def asyncTearDown(self):await self.bot.close();self.store.close();self.tmp.cleanup()
 def request(self,**data):return NS(post=AsyncMock(return_value=dict(csrf='test',guild='1',**data)))
 async def test_layout_is_per_user_and_csrf_protected(self):
  with self.assertRaises(web.HTTPSeeOther):await self.dashboard.panel_layout(self.request(layout='["abcdef123456"]'))
  self.assertEqual(self.store.profile(1,10)['dashboard_layout'],['abcdef123456']);self.assertNotIn('dashboard_layout',self.store.profile(1,11))
  request=NS(post=AsyncMock(return_value=dict(csrf='wrong',guild='1',layout='[]')))
  with self.assertRaises(web.HTTPForbidden):await self.dashboard.panel_layout(request)
 async def test_invalid_panel_layout_rejected(self):
  with self.assertRaises(web.HTTPBadRequest):await self.dashboard.panel_layout(self.request(layout='["<script>"]'))
 async def test_announcement_escaped_and_confirmation_required(self):
  blocks=json.dumps([dict(type='text',value='<script>alert(1)</script>')])
  response=await self.dashboard.announcement_editor(self.request(document=blocks,action='preview'));self.assertIn('&lt;script&gt;',response.text);self.assertNotIn('<script>alert',response.text)
  with self.assertRaises(web.HTTPBadRequest):await self.dashboard.announcement_editor(self.request(document=blocks,action='publish'))
 async def test_announcement_draft_is_private_and_per_user(self):
  blocks=[dict(type='text',value='Draft')]
  with self.assertRaises(web.HTTPSeeOther):await self.dashboard.announcement_editor(self.request(document=json.dumps(blocks),action='draft'))
  self.assertEqual(self.store.profile(1,10)['announcement_draft'],blocks);self.assertNotIn('announcement_draft',self.store.profile(1,11))
 async def test_announcement_publish_checks_channel_and_permissions(self):
  channel=MagicMock(spec=discord.TextChannel);channel.guild=self.guild;channel.send=AsyncMock();channel.permissions_for=lambda member:NS(send_messages=True,embed_links=True)
  self.guild.get_channel=lambda cid:channel if cid==100 else None;self.guild.fetch_member=AsyncMock(return_value=NS(guild_permissions=NS(administrator=True)))
  blocks=[dict(type='text',value='Hello @everyone')]
  with self.assertRaises(web.HTTPSeeOther):await self.dashboard.announcement_editor(self.request(document=json.dumps(blocks),action='publish',confirm='yes',channel='100'))
  channel.send.assert_awaited_once();self.assertFalse(channel.send.call_args.kwargs['allowed_mentions'].everyone)
  self.guild.fetch_member.return_value.guild_permissions.administrator=False
  with self.assertRaises(web.HTTPForbidden):await self.dashboard.announcement_editor(self.request(document=json.dumps(blocks),action='publish',confirm='yes',channel='100'))
 async def test_welcome_preview_and_save(self):
  response=await self.dashboard.welcome_editor(self.request(document=json.dumps(DEFAULT_LAYOUT),action='preview'));self.assertEqual(response.content_type,'image/png');self.assertIsNone(self.store.option(1,'welcome_layout'))
  with self.assertRaises(web.HTTPSeeOther):await self.dashboard.welcome_editor(self.request(document=json.dumps(DEFAULT_LAYOUT),action='save'))
  self.assertEqual(self.store.option(1,'welcome_layout'),DEFAULT_LAYOUT)
 async def test_studio_script_is_external_and_csp_restricts_scripts(self):
  response=await self.dashboard.studio_script(None);self.assertIn('textContent',response.text);self.assertNotIn('innerHTML',response.text)
  response=self.dashboard.page('Test');self.dashboard.headers(response);self.assertIn("script-src 'self'",response.headers['Content-Security-Policy']);self.assertIn('<main id="main-content">',response.text)
