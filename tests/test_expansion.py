"""Offline behavior checks for the selected tournament, game, profile and community additions."""
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
from unittest.mock import AsyncMock,MagicMock,patch
import discord
from PIL import Image
from vivi.storage import Store
from vivi.bot import ViviBot,register_commands
from vivi.community import register_extra,DeleteView
from vivi.operations import register_operations
from vivi.productivity import register_productivity
from vivi.customization import register_customization
from vivi.suite import register_suite
from vivi.game_hub import register_games
from vivi.more_games import Reversi,Minesweeper,WordSearch,Crossword,Spelling,CROSSWORDS,SPELLING,SAVED_TYPES,coord
from vivi.competitions import schedule,report_result,register_competitions
from vivi.guild_library import register_library,TeamPanel,clean_text
from vivi.invites import estimate,register_invites
from vivi.profiles import gradient_colors,register_profiles,DEFAULT_STYLE,BACKGROUNDS,FONTS,LAYOUTS,render_profile,visible_fields,validate_style,normalize_banner


def competition(count,format='double'):
 return dict(name='Test',format=format,players=list(range(1,count+1)),losses={},matches=[],status='active',host=1,capacity=32)

def notation(r,c,size):return f'{chr(65+c)}{size-r}'

class MoreGameRules(unittest.TestCase):
 def test_reversi_opening_flips_and_invalid_move_is_atomic(self):
  game=Reversi();self.assertEqual(len(game.legal(0)),4);before=copy.deepcopy(game.cells)
  with self.assertRaises(ValueError):game.move('A1')
  self.assertEqual(before,game.cells);game.move('D6');self.assertEqual(game.cells[3][3],1);self.assertEqual(game.turn,1)
 def test_reversi_finishes_with_passes_and_consistent_counts(self):
  random.seed(40);game=Reversi();turns=0
  while not game.done:
   options=game.legal(game.turn);self.assertTrue(options);r,c=random.choice(options);game.move(notation(r,c,8));turns+=1;self.assertLessEqual(turns,60)
  self.assertFalse(game.legal(0));self.assertFalse(game.legal(1));self.assertIn('wins',game.result) if 'Draw' not in game.result else None
 def test_mines_first_reveal_and_neighbors_are_safe(self):
  for difficulty in ['easy','medium','hard']:
   game=Minesweeper(difficulty);game.move('C3');self.assertNotIn(20,game.mines);self.assertFalse(set(game.neighbors(20))&set(game.mines));self.assertFalse(game.done and 'Mine hit' in game.result)
 def test_mines_flags_and_invalid_moves(self):
  game=Minesweeper();game.move('flag A1');self.assertIn(30,game.flags)
  with self.assertRaises(ValueError):game.move('A1')
  game.move('unflag A1');game.move('A1');self.assertIn(30,game.revealed)
  with self.assertRaises(ValueError):game.move('Z9')
 def test_mines_win_and_loss_reveal(self):
  game=Minesweeper();game.move('A1')
  for n in range(36):
   if n not in game.mines and n not in game.revealed:game.move(notation(*divmod(n,6),6))
  self.assertTrue(game.done);self.assertIn('All safe',game.result)
  game=Minesweeper();game.move('A1');n=game.mines[0];game.move(notation(*divmod(n,6),6));self.assertTrue(game.done);self.assertIn('*',game.board())
 def test_wordsearch_all_placements_are_valid_and_reversible(self):
  game=WordSearch();self.assertEqual(len(game.words),8)
  for word,path in game.words.items():
   self.assertEqual(''.join(game.cells[r][c] for r,c in path),word)
   game.move(notation(*path[-1],10)+'-'+notation(*path[0],10))
  self.assertTrue(game.done)
 def test_wordsearch_duplicate_and_bounds(self):
  game=WordSearch();path=next(iter(game.words.values()));text=notation(*path[0],10)+'-'+notation(*path[-1],10);game.move(text)
  with self.assertRaises(ValueError):game.move(text)
  for text in ['A0-B1','K1-A1','A1-A11','garbage']:
   with self.assertRaises(ValueError):game.move(text)
 def test_crossword_saved_answers_and_crossings(self):
  game=Crossword();key,(answer,clue)=next(iter(CROSSWORDS[game.pack][1].items()));game.move(key+'='+answer)
  saved=json.loads(json.dumps(game.dump()));resumed=Crossword.load(saved);self.assertEqual(resumed.answers,game.answers)
  for key,(answer,clue) in CROSSWORDS[game.pack][1].items():
   if key not in resumed.answers:resumed.move(key+'='+answer)
  self.assertTrue(resumed.done);self.assertNotIn('.',resumed.board().split('```')[1])
 def test_crossword_wrong_guess_does_not_change_progress(self):
  game=Crossword()
  with self.assertRaises(ValueError):game.move('1A=ZZZ')
  self.assertEqual(game.answers,{})
 def test_spelling_progressively_harder_and_saved(self):
  game=Spelling()
  for word,clue in SPELLING:
   self.assertNotIn(word,game.board().lower());game.move(word);game=Spelling.load(json.loads(json.dumps(game.dump())))
  self.assertTrue(game.done)
 def test_spelling_three_mistakes_end_game(self):
  game=Spelling()
  for _ in range(3):game.move('incorrect')
  self.assertTrue(game.done)
 def test_puzzle_json_round_trip(self):
  for name,cls in SAVED_TYPES.items():
   game=cls();loaded=cls.load(json.loads(json.dumps(game.dump())));self.assertEqual(loaded.board(),game.board())

class BracketRules(unittest.TestCase):
 def test_single_and_double_for_non_power_of_two_sizes(self):
  rng=random.Random(27)
  for format in ['single','double']:
   for count in range(2,18):
    data=competition(count,format);schedule(data);steps=0
    while data['status']=='active':
     pending=[m for m in data['matches'] if m['winner'] is None];participants=[u for m in pending for u in [m['a'],m['b']]]
     self.assertEqual(len(set(participants)),len(participants))
     for match in pending:data=report_result(data,match['id'],rng.choice([match['a'],match['b']]),1,'Verified result');steps+=1
     self.assertLess(steps,2*count)
    self.assertIn(data['winner'],data['players']);self.assertEqual(len(data['matches']),count-1) if format=='single' else self.assertIn(len(data['matches']),[2*count-2,2*count-1])
    self.assertTrue(all(losses==(1 if format=='single' else 2) for user,losses in data['losses'].items() if int(user)!=data['winner']))
 def test_double_elimination_grand_final_reset(self):
  data=competition(2);schedule(data);data=report_result(data,1,1,1,'First match');data=report_result(data,2,2,1,'Lower bracket wins')
  self.assertEqual(data['status'],'active');self.assertEqual(len(data['matches']),3);self.assertEqual(data['matches'][-1]['bracket'],'grand final/reset')
  data=report_result(data,3,2,1,'Reset winner');self.assertEqual(data['winner'],2)
 def test_invalid_or_duplicate_result_does_not_mutate(self):
  data=competition(4);schedule(data);before=copy.deepcopy(data)
  with self.assertRaises(ValueError):report_result(data,1,999,1,'Invalid player')
  self.assertEqual(data,before);data=report_result(data,1,1,1,'Valid result')
  with self.assertRaises(ValueError):report_result(data,1,2,1,'Duplicate')

class InviteRules(unittest.TestCase):
 def test_exactly_one_increment_is_an_estimate(self):
  old={'abc':dict(uses=2,inviter=7)};new={'abc':dict(uses=3,inviter=7)};result=estimate(old,new);self.assertEqual(result['status'],'estimated');self.assertEqual(result['inviter'],7)
 def test_ambiguous_and_missing_snapshots_stay_unknown(self):
  old={'a':dict(uses=0,inviter=1),'b':dict(uses=0,inviter=2)}
  for previous,current in [(None,old),(old,old),(old,{'a':dict(uses=2,inviter=1),'b':dict(uses=0,inviter=2)}),(old,{}),(old,{'a':dict(uses=1,inviter=1),'b':dict(uses=1,inviter=2)}),(old,dict(old,c=dict(uses=1,inviter=3)))]:self.assertEqual(estimate(previous,current)['status'],'unknown')

class ProfileRendering(unittest.TestCase):
 def test_each_starter_background_font_and_layout_renders_portably(self):
  for n,background in enumerate(BACKGROUNDS):
   style=dict(copy.deepcopy(DEFAULT_STYLE),background=background,font=FONTS[n%3],layout=LAYOUTS[n%3],stickers=[dict(item='flower',x=800,y=200)])
   body=render_profile('Member',dict(xp=100,coins=4,achievements=['First words']),style)
   with Image.open(io.BytesIO(body)) as image:self.assertEqual(image.size,(900,360))
 def test_hidden_fields_are_omitted_from_public_values(self):
  p=dict(xp=999,coins=123,achievements=['Secret award'],card_style=dict(status='Private status'),card_visibility=dict(xp=False,coins=False,achievements=False,status=False,showcase=False))
  self.assertEqual(visible_fields(p,['Secret creation']),{})
 def test_style_validation_rejects_paths_and_out_of_bounds(self):
  for changes in [dict(background='../../private'),dict(font='system'),dict(stickers=[dict(item='star',x=900,y=2)]),dict(gradient='red;script'),dict(status='x'*121)]:
   with self.assertRaises(ValueError):validate_style(dict(copy.deepcopy(DEFAULT_STYLE),**changes))
 def test_custom_gradient_pairs_are_validated(self):
  style=dict(copy.deepcopy(DEFAULT_STYLE),gradient='#bb99ee,#ffb6cc');validate_style(style);self.assertEqual(gradient_colors(style['gradient']),['#bb99ee','#ffb6cc'])
  self.assertTrue(render_profile('Member',{},style).startswith(bytes.fromhex('89504e47')))
  with self.assertRaises(ValueError):gradient_colors('#ffffff,url(evil)')
 def test_normalization_strips_metadata_and_resizes(self):
  source=io.BytesIO();Image.new('RGB',(40,50),'pink').save(source,format='JPEG');body=normalize_banner(source.getvalue())
  with Image.open(io.BytesIO(body)) as image:self.assertEqual(image.size,(900,360));self.assertEqual(image.format,'PNG');self.assertFalse(image.getexif())
 def test_invalid_image_is_not_accepted(self):
  with self.assertRaises(OSError):normalize_banner(b'<html>not an image</html>')

class ExpansionInteractions(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'data/vivi.sqlite3');self.bot=ViviBot(self.store);await self.bot.__aenter__();self.service=self.bot.community
  for register in [register_commands,register_extra,register_operations,register_productivity,register_customization,register_suite,register_games,register_competitions,register_library,register_invites,register_profiles]:register(self.bot)
  self.member=MagicMock(spec=discord.Member);self.member.id=10;self.member.bot=False;self.member.display_name='Member';self.member.roles=[];self.member.guild_permissions=discord.Permissions.all()
  avatar=io.BytesIO();Image.new('RGB',(64,64),'pink').save(avatar,format='PNG');self.avatar=avatar.getvalue();self.member.display_avatar.with_size.return_value.with_format.return_value.read=AsyncMock(return_value=self.avatar)
  self.guild=NS(id=1,name='Example',get_member=lambda uid:self.member if uid==10 else None,invites=AsyncMock(return_value=[]));self.member.guild=self.guild
  self.bot.get_guild=lambda gid:self.guild if gid==1 else None
  self.i=NS(user=self.member,guild=self.guild,guild_id=1,channel_id=100,response=NS(is_done=lambda:False,send_message=AsyncMock(),defer=AsyncMock(),edit_message=AsyncMock()),followup=NS(send=AsyncMock(return_value=NS(edit=AsyncMock()))))
  for name in ['teams','library','profiles','games','competitions','invite_tracking']:self.store.set_option(1,'feature:'+name,True)
 async def asyncTearDown(self):await self.bot.close();self.store.close();self.tmp.cleanup()
 async def call(self,group,command_name,**kwargs):return await self.bot.tree.get_command(group).get_command(command_name).callback(self.i,**kwargs)
 def team(self,captain=10):return self.store.put_record(1,'team',dict(name='Violets',game='Example',captain=captain,roster=[dict(user=captain,position='starter',role='Captain')]))
 async def test_command_groups_stay_within_discord_limits(self):
  for command in self.bot.tree.get_commands():
   if isinstance(command,discord.app_commands.Group):self.assertLessEqual(len(command.commands),25)
   command.to_dict(self.bot.tree)
 async def test_competition_permission_and_server_isolation(self):
  ident=self.store.put_record(1,'bracket',dict(competition(2),status='registration',host=99))
  self.member.guild_permissions=discord.Permissions.none();await self.call('competition','start',competition_id=ident);self.assertEqual(self.store.record(ident)['data']['status'],'registration')
  self.i.guild_id=2;await self.call('competition','join',competition_id=ident);self.assertEqual(len(self.store.record(ident)['data']['players']),2)
 async def test_competition_persists_results(self):
  data=competition(2,'single');data['host']=10;schedule(data);ident=self.store.put_record(1,'bracket',data);winner=NS(id=1)
  await self.call('competition','result',competition_id=ident,match_id=1,winner=winner,reason='Confirmed score');self.assertEqual(self.store.record(ident)['data']['winner'],1)
 async def test_team_invitation_requires_target_consent(self):
  team=self.team(99);ident=self.store.put_record(1,'team_invite',dict(team=team,user=11,captain=99,position='substitute',role='Support',expires=time.time()+60,closed=False));view=TeamPanel(self.service,ident,'team_invite')
  await view.click(self.i);self.assertEqual(len(self.store.record(team)['data']['roster']),1)
  self.member.id=11;await view.click(self.i);self.assertEqual(len(self.store.record(team)['data']['roster']),2);self.assertTrue(self.store.record(ident)['data']['closed'])
 async def test_team_invitation_rechecks_changed_captain(self):
  team=self.team(99);ident=self.store.put_record(1,'team_invite',dict(team=team,user=10,captain=88,position='starter',role='Player',expires=time.time()+60,closed=False));await TeamPanel(self.service,ident,'team_invite').click(self.i);self.assertEqual(len(self.store.record(team)['data']['roster']),1)
 async def test_recruitment_requires_role_and_does_not_auto_join(self):
  team=self.team(99);ident=self.store.put_record(1,'team_recruitment',dict(team=team,required_role=40,expires=time.time()+60,closed=False));view=TeamPanel(self.service,ident,'team_recruitment')
  await view.click(self.i);self.assertEqual(self.store.records(1,'team_application'),[])
  self.member.roles=[NS(id=40)];await view.click(self.i);self.assertEqual(len(self.store.records(1,'team_application')),1);self.assertEqual(len(self.store.record(team)['data']['roster']),1)
 async def test_non_captain_cannot_change_roster(self):
  team=self.team(99);self.member.guild_permissions=discord.Permissions.none();await self.call('teams','captain',team_id=team,member=self.member);self.assertEqual(self.store.record(team)['data']['captain'],99)
 async def test_library_search_edit_and_ownership(self):
  await self.call('library','publish',kind='build',title='Healer setup',game='Example',content='Equip a staff and healing armor.')
  row=self.store.records(1,'library_entry')[0];await self.call('library','edit',entry_id=row['id'],content='Equip a staff and improved healing armor.');self.assertEqual(len(self.store.record(row['id'])['data']['history']),1)
  self.member.id=11;await self.call('library','edit',entry_id=row['id'],content='Unauthorized replacement text.');self.assertNotIn('Unauthorized',self.store.record(row['id'])['data']['content'])
 async def test_library_and_status_filters(self):
  self.store.set_option(1,'blocked_words',['forbidden'])
  await self.call('library','publish',kind='guide',title='Guide',game='Example',content='A forbidden word appears here.');self.assertEqual(self.store.records(1,'library_entry'),[])
  await self.call('profile','customize',status='forbidden');self.assertNotIn('card_style',self.store.profile(1,10))
 async def test_library_cross_server_read_is_denied(self):
  ident=self.store.put_record(2,'library_entry',dict(title='Secret',content='Other server'))
  await self.call('library','read',entry_id=ident);self.assertNotIn('embed',self.i.response.send_message.call_args.kwargs)
 async def test_invite_estimate_records_only_unambiguous_use(self):
  tracker=self.service.invites;tracker.cache[1]={'abc':dict(uses=0,inviter=20)};self.guild.invites.return_value=[NS(code='abc',uses=1,inviter=NS(id=20))]
  await tracker.on_join(self.member);self.assertEqual(self.store.record('invite_source:1:10')['data']['status'],'estimated')
 async def test_invite_permission_failure_is_unknown_and_clears_baseline(self):
  tracker=self.service.invites;tracker.cache[1]={};self.guild.invites.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'No permission')
  await tracker.on_join(self.member);self.assertNotIn(1,tracker.cache);self.assertEqual(self.store.record('invite_source:1:10')['data']['status'],'unknown')
 async def test_invite_source_private_to_self_or_staff(self):
  self.store.put_record(1,'invite_source',dict(status='estimated',code='private-code',inviter=99,reason='Estimate'),'invite_source:1:11');self.member.guild_permissions=discord.Permissions.none()
  await self.call('invites','source',member=NS(id=11));self.assertNotIn('private-code',self.i.response.send_message.call_args.args[0])
 async def test_crossword_saved_and_resumed_by_same_member(self):
  hub=self.service.games;await hub.start(self.i,'crossword');key=(1,10);game=hub.sessions[key];clue,(answer,_)=next(iter(CROSSWORDS[game['engine'].pack][1].items()));await hub.move(self.i,clue+'='+answer)
  saved=self.store.record('puzzle:1:10:crossword');self.assertIn(clue,saved['data']['state']['answers']);hub.sessions.clear();await hub.start(self.i,'crossword');self.assertIn(clue,hub.sessions[key]['engine'].answers)
 async def test_finished_puzzle_rejects_late_moves(self):
  hub=self.service.games;await hub.start(self.i,'spelling');game=hub.sessions[(1,10)];game['engine'].done=True;game['engine'].index=len(SPELLING)
  await hub.move(self.i,'word');self.assertEqual(game['engine'].index,len(SPELLING))
 async def test_stale_game_update_cannot_attach_new_session_controls(self):
  hub=self.service.games;await hub.start(self.i,'crossword');old=hub.sessions[(1,10)];hub.sessions[(1,10)]=dict(old)
  await hub.update(old);old['message'].edit.assert_not_awaited()
 async def test_profile_preview_does_not_save_temporary_changes(self):
  await self.call('profile','preview',background='moon_lake',font='mono');self.assertNotIn('card_style',self.store.profile(1,10));file=self.i.followup.send.call_args.kwargs['file'];self.assertTrue(file.fp.read().startswith(bytes.fromhex('89504e47')));file.close()
 async def test_whole_profile_privacy_applies_to_legacy_command(self):
  self.store.save_profile(1,11,dict(self.store.profile(1,11),visible=False));await self.call('economy','profile',member=NS(id=11));self.i.followup.send.assert_not_awaited();self.assertIn('private',self.i.response.send_message.call_args.args[0])
 async def test_profile_loadout_preserves_field_privacy(self):
  await self.call('profile','visibility',field='coins',public=False);await self.call('profile','customize',background='rose_dusk',font='serif');await self.call('profile','loadout',action='save',name='rose');await self.call('profile','customize',background='moon_lake');await self.call('profile','loadout',action='apply',name='rose')
  p=self.store.profile(1,10);self.assertEqual(p['card_style']['background'],'rose_dusk');self.assertFalse(p['card_visibility']['coins'])
 async def test_shop_cosmetic_is_preserved_by_loadouts(self):
  p=self.store.profile(1,10);p.update(owned=['royal'],equipped='royal');self.store.save_profile(1,10,p)
  await self.call('profile','loadout',action='save',name='royal');p=self.store.profile(1,10);p['equipped']='';self.store.save_profile(1,10,p)
  await self.call('profile','loadout',action='apply',name='royal');self.assertEqual(self.store.profile(1,10)['equipped'],'royal')
 async def test_hidden_xp_is_excluded_from_leaderboards(self):
  self.store.set_option(1,'feature:xp',True);p=self.store.profile(1,10);p.update(xp=999,card_visibility={'xp':False});self.store.save_profile(1,10,p)
  await self.call('economy','leaderboard');self.assertNotIn('999',self.i.response.send_message.call_args.args[0])
 async def test_invite_baseline_invalidated_after_configuration_restore(self):
  tracker=self.service.invites;tracker.cache[1]={'abc':dict(uses=0,inviter=20)};tracker.generations[1]=tracker.generation(1)
  backup=self.store.export_config(1);self.store.restore_config(1,backup);self.guild.invites.return_value=[NS(code='abc',uses=1,inviter=NS(id=20))]
  await tracker.on_join(self.member);self.assertEqual(self.store.record('invite_source:1:10')['data']['status'],'unknown')
 async def test_banner_review_ownership_approval_and_revocation(self):
  ident='a'*32;path=self.store.path.parent/'profile-banners'/'1'/(ident+'.png');path.parent.mkdir(parents=True);path.write_bytes(normalize_banner(self.avatar));self.store.put_record(1,'profile_banner',dict(user=11,status='pending',history=[]),ident)
  self.member.id=11;await self.call('profile','banner_review',banner_id=ident,action='approve',reason='Own image');self.assertEqual(self.store.record(ident)['data']['status'],'pending')
  self.member.id=10;await self.call('profile','banner_review',banner_id=ident,action='approve',reason='Approved artwork');style=dict(copy.deepcopy(DEFAULT_STYLE),background='upload:'+ident);self.assertIsNotNone(self.service.profiles.banner(1,11,style,True))
  with self.assertRaises(ValueError):self.service.profiles.banner(1,10,style,True)
  await self.call('profile','banner_review',banner_id=ident,action='reject',reason='Permission revoked');self.assertIsNone(self.service.profiles.banner(1,11,style))
 async def test_banner_submission_and_normalized_storage(self):
  await self.call('profile','banner_submit',attachment=NS(size=len(self.avatar),read=AsyncMock(return_value=self.avatar)));rows=self.store.records(1,'profile_banner');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['data']['status'],'pending')
  path=self.store.path.parent/'profile-banners'/'1'/(rows[0]['id']+'.png')
  with Image.open(path) as image:self.assertEqual(image.size,(900,360))
 async def test_showcases_require_owned_creations_and_earned_awards(self):
  ident=self.store.put_record(1,'library_entry',dict(author=99,title='Someone else’s guide'))
  await self.call('profile','showcase',slot=1,kind='creation',value=ident);self.assertNotIn('card_style',self.store.profile(1,10))
  await self.call('profile','showcase',slot=1,kind='achievement',value='Unearned');self.assertNotIn('card_style',self.store.profile(1,10))
 async def test_status_moderation_clears_loadouts_too(self):
  await self.call('profile','customize',status='Old status');await self.call('profile','loadout',action='save',name='old');await self.call('profile','moderate',member=self.member,reason='Server policy');p=self.store.profile(1,10);self.assertEqual(p['card_style']['status'],'');self.assertEqual(p['card_loadouts']['old']['status'],'')
 async def test_privacy_deletion_clears_new_personal_records_and_files(self):
  team=self.team();self.store.put_record(1,'invite_source',dict(user=10),'invite_source:1:10');self.store.put_record(1,'puzzle_progress',dict(user=10),'puzzle');self.store.put_record(1,'library_entry',dict(author=10),'entry')
  ident='b'*32;path=self.store.path.parent/'profile-banners'/'1'/(ident+'.png');path.parent.mkdir(parents=True);path.write_bytes(self.avatar);self.store.put_record(1,'profile_banner',dict(user=10,status='pending'),ident)
  with patch('vivi.community.audit',new=AsyncMock()):await DeleteView(self.service,10,1).confirm.callback(self.i)
  for ident in ['invite_source:1:10','puzzle','entry',team]:self.assertIsNone(self.store.record(ident))
  self.assertFalse(path.exists())
