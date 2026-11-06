"""Consent-based Discord game sessions. Hidden boards are returned ephemerally."""
import asyncio
import contextlib
import random
import time
import discord
from discord import app_commands
from .bot import reply
from .features import enabled
from .game_engines import ConnectFour, Checkers, Chess, Hangman, Sudoku, Memory, Battleship, WORD_BANK

from .more_games import Reversi,SAVED_TYPES

class MoveModal(discord.ui.Modal,title='Your move'):
    value=discord.ui.TextInput(label='Move or guess',max_length=80)
    def __init__(self,hub,key): super().__init__(); self.hub=hub; self.key=key; self.game=hub.sessions.get(key)
    async def on_submit(self,i):
        if self.hub.sessions.get(self.key) is not self.game or i.guild_id!=self.key[0]: return await reply(i,'This game has ended. Use your current game’s controls.')
        await self.hub.move(i,str(self.value))

class GameView(discord.ui.View):
    def __init__(self,hub,key,invite=False):
        super().__init__(timeout=None); self.hub=hub; self.key=key; self.game=hub.sessions.get(key)
        for label in (['Accept','Decline'] if invite else ['Enter move','Private board','Resign']):
            button=discord.ui.Button(label=label)
            async def callback(i,action=label):
                game=hub.sessions.get(key)
                if not game or game is not self.game or i.user.id not in game['players']: return await reply(i,'This is not your active game.')
                if not enabled(hub.store,i.guild_id,'games'): return await reply(i,'Games are disabled here.')
                if action in {'Accept','Decline'}:
                    if i.user.id!=game['players'][1]: return await reply(i,'Only the challenged member can respond.')
                    if action=='Decline': hub.sessions.pop(key,None); return await i.response.edit_message(content='Challenge declined.',view=None)
                    game['accepted']=True; game['expires']=time.time()+1800
                    return await i.response.edit_message(content=hub.public(game),view=GameView(hub,key))
                if action=='Enter move': return await i.response.send_modal(MoveModal(hub,key))
                if action=='Private board': return await reply(i,hub.private(game,i.user.id))
                await hub.resign(i)
            button.callback=callback; self.add_item(button)
        game=hub.sessions.get(key)
        if game and not invite and game['kind'] in {'memory','connect_four'}:
            moves=[str(n) for n in range(1,8)] if game['kind']=='connect_four' else [f'{chr(65+c)}{4-r}' for r in range(4) for c in range(4)]
            for n,move in enumerate(moves):
                engine=game['engine']; label=move
                if game['kind']=='memory':
                    if n in engine.matched or n in engine.shown: label=move+' '+engine.cards[n]
                button=discord.ui.Button(label=label,row=1+n//4,disabled=game['kind']=='memory' and (n in engine.matched or n in engine.shown))
                async def choose(i,value=move):
                    found=hub.find(i.guild_id,i.user.id)
                    if not found or found[0]!=key or found[1] is not self.game: return await reply(i,'This is not your active game.')
                    await hub.move(i,value)
                button.callback=choose; self.add_item(button)

class TournamentView(discord.ui.View):
    def __init__(self,hub,key):
        super().__init__(timeout=None); self.game=hub.sessions.get(key)
        for label in ['Join','Start','Guess']:
            button=discord.ui.Button(label=label)
            async def callback(i,action=label):
                game=hub.sessions.get(key)
                if not game or game is not self.game or i.guild_id!=key[0] or not enabled(hub.store,i.guild_id,'games'): return await reply(i,'Tournament unavailable.')
                if action=='Join':
                    if game['round']: return await reply(i,'The tournament has started.')
                    if i.user.id not in game['players']:
                        if hub.find(i.guild_id,i.user.id): return await reply(i,'Finish your current game first.')
                        if len(game['players'])>=10: return await reply(i,'This tournament is full.')
                        game['players'].append(i.user.id); game['scores'][i.user.id]=0
                    return await i.response.edit_message(content=hub.public(game),view=self)
                if action=='Start':
                    if i.user.id!=game['players'][0] or game['round']: return await reply(i,'Only the host can start this lobby.')
                    if len(game['players'])<2: return await reply(i,'At least two players must join.')
                    hub.next_round(game); return await i.response.edit_message(content=hub.public(game),view=self)
                if i.user.id not in game['players']: return await reply(i,'Join before the tournament starts.')
                await i.response.send_modal(MoveModal(hub,key))
            button.callback=callback; self.add_item(button)

class GameHub:
    def __init__(self,service): self.service=service; self.bot=service.bot; self.store=service.store; self.sessions={}; self.task=None
    def find(self,guild,user): return next(((key,g) for key,g in self.sessions.items() if key[0]==guild and user in g['players']),None)
    def private(self,g,user):
        if g['kind']=='anagram': return self.public(g)
        engine=g['engine']; player=g['players'].index(user)
        return engine.board(player)+'\n'+engine.help
    def public(self,g):
        if g['kind']=='anagram':
            scores=' · '.join(f'<@{u}>: {g["scores"][u]}' for u in g['players'])
            if not g['round']: return 'Anagram tournament lobby. Join, then the host presses Start.\n'+scores
            return f'Anagram round {g["round"]}/{g["rounds"]}: **{g["scramble"]}** · <t:{int(g["deadline"])}:R>\n'+scores+('\n'+g.get('last',''))
        engine=g['engine']; board=engine.last if g['kind']=='battleship' else engine.board()
        return f'**{g["kind"].title()}** · '+(' vs '.join(f'<@{u}>' for u in g['players']))+'\n'+board+'\n'+(engine.result if engine.done else f'Turn: <@{g["players"][engine.turn]}>')+'\n'+engine.help
    async def start(self,i,kind,opponent=None,difficulty='easy',rounds=5):
        if not await self.service.need(i,'games'): return
        if self.find(i.guild_id,i.user.id): return await reply(i,'Finish your active game with /games resign first.')
        if sum(key[0]==i.guild_id for key in self.sessions)>=50: return await reply(i,'Server game limit reached. Try later.')
        if opponent and (opponent.bot or opponent.id==i.user.id or self.find(i.guild_id,opponent.id)): return await reply(i,'Choose another available human member.')
        await i.response.defer()
        key=(i.guild_id,i.user.id)
        game=dict(kind=kind,players=[i.user.id]+([opponent.id] if opponent else []),accepted=not opponent,expires=time.time()+(120 if opponent else 1800))
        if kind=='anagram': game.update(round=0,rounds=rounds,scores={i.user.id:0},words=random.sample(WORD_BANK,rounds),last='')
        else:
            factories={'connect_four':ConnectFour,'checkers':Checkers,'chess':Chess,'hangman':Hangman,'sudoku':lambda:Sudoku(difficulty),'memory':Memory,'battleship':Battleship,'reversi':Reversi,**SAVED_TYPES}
            if kind=='minesweeper':factories[kind]=lambda:SAVED_TYPES[kind](difficulty)
            saved=self.store.record(f'puzzle:{i.guild_id}:{i.user.id}:{kind}') if kind in SAVED_TYPES else None
            game['engine']=SAVED_TYPES[kind].load(saved['data']['state']) if saved else await asyncio.to_thread(factories[kind])
        game['key']=key
        # Recheck after off-thread Sudoku generation.
        if self.find(i.guild_id,i.user.id) or opponent and self.find(i.guild_id,opponent.id): return await reply(i,'A player started another game. Retry after it ends.')
        if sum(k[0]==i.guild_id for k in self.sessions)>=50:return await reply(i,'Server game limit reached. Try later.')
        self.sessions[key]=game
        self.save_puzzle(game)
        view=TournamentView(self,key) if kind=='anagram' else GameView(self,key,bool(opponent))
        try: game['message']=await i.followup.send(f'<@{opponent.id}>, accept this {kind} challenge within two minutes.' if opponent else self.public(game),view=view,wait=True,allowed_mentions=discord.AllowedMentions.none())
        except Exception: self.sessions.pop(key,None); raise
    def save_puzzle(self,g):
        if g['kind'] not in SAVED_TYPES:return
        ident=f'puzzle:{g["key"][0]}:{g["players"][0]}:{g["kind"]}'
        if g['engine'].done:self.store.delete_record(ident)
        else:self.store.put_record(g['key'][0],'puzzle_progress',dict(user=g['players'][0],kind=g['kind'],state=g['engine'].dump(),saved=time.time()),ident)

    def next_round(self,g):
        g['round']+=1; g['word']=g['words'][g['round']-1]; chars=list(g['word'])
        for _ in range(10):
            random.shuffle(chars)
            if ''.join(chars)!=g['word']: break
        g['scramble']=''.join(chars); g['deadline']=time.time()+30; g['answered']=set()
    async def move(self,i,text):
        if not await self.service.need(i,'games'): return
        found=self.find(i.guild_id,i.user.id)
        if not found: return await reply(i,'You have no active game.')
        key,g=found
        if not g['accepted']: return await reply(i,'Wait for the opponent to accept.')
        if g['kind']=='anagram':
            if not g['round'] or time.time()>=g['deadline']: return await reply(i,'Wait for the next round.')
            if i.user.id in g['answered']: return await reply(i,'Your answer is already counted.')
            alternatives=[w for w in WORD_BANK if sorted(w)==sorted(g['word'])]
            if text.lower().strip() not in alternatives: return await reply(i,'That is not a matching word in this tournament’s word bank.')
            g['answered'].add(i.user.id); g['scores'][i.user.id]+=max(1,int(g['deadline']-time.time()))
            return await reply(i,'Correct! Your points will appear at the end of the round.')
        engine=g['engine']
        if engine.done:return await reply(i,'This game has finished. Start another game.')
        if g['players'][engine.turn]!=i.user.id: return await reply(i,'It is the other player’s turn.')
        try: engine.move(text.strip())
        except ValueError as error: return await reply(i,str(error))
        g['expires']=time.time()+1800
        self.save_puzzle(g)
        await i.response.defer(ephemeral=True)
        await self.update(g)
        await reply(i,self.private(g,i.user.id) if g['kind']=='battleship' else 'Move recorded.')
        if engine.done:
            if self.sessions.get(key) is g:self.sessions.pop(key,None)
        elif isinstance(engine,Memory) and len(engine.shown)==2: g['hide_at']=time.time()+2
    async def resign(self,i):
        found=self.find(i.guild_id,i.user.id)
        if not found: return await reply(i,'You have no active game.')
        key,g=found; self.sessions.pop(key,None)
        await i.response.defer(ephemeral=True)
        with contextlib.suppress(discord.HTTPException): await g['message'].edit(content=f'Game ended: <@{i.user.id}> resigned.',view=None,allowed_mentions=discord.AllowedMentions.none())
        await reply(i,'Game ended.')
    async def update(self,g):
        if self.sessions.get(g['key']) is not g:return
        with contextlib.suppress(discord.HTTPException):
            done=g.get('engine') and g['engine'].done
            await g['message'].edit(content=self.public(g),view=None if done else (TournamentView(self,g['key']) if g['kind']=='anagram' else GameView(self,g['key'])),allowed_mentions=discord.AllowedMentions.none())
    async def tick(self):
        now=time.time()
        for key,g in list(self.sessions.items()):
            if self.sessions.get(key) is not g:continue
            if g['expires']<now or not enabled(self.store,key[0],'games'):
                self.sessions.pop(key,None)
                with contextlib.suppress(discord.HTTPException): await g['message'].edit(content='Game ended (timeout or games disabled).',view=None)
                continue
            if g.get('hide_at',now+1)<=now:
                g.pop('hide_at'); g['engine'].shown=[]; await self.update(g)
            if g['kind']=='anagram' and g['round'] and g['deadline']<=now:
                g['last']='Previous answer: '+g['word']
                if g['round']>=g['rounds']:
                    self.sessions.pop(key,None)
                    with contextlib.suppress(discord.HTTPException): await g['message'].edit(content='Tournament finished!\n'+g['last']+'\n'+'\n'.join(f'<@{u}>: {score}' for u,score in sorted(g['scores'].items(),key=lambda x:x[1],reverse=True)),view=None,allowed_mentions=discord.AllowedMentions.none())
                else: self.next_round(g); await self.update(g)
    async def run(self):
        await self.bot.wait_until_ready()
        while True:
            try: await self.tick()
            except Exception as error: self.service.productivity.error('game timer',error)
            await asyncio.sleep(1)
    def start_task(self): self.task=asyncio.create_task(self.run(),name='vivi-games')
    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError): await self.task


def register_games(bot):
    group=bot.tree.get_command('games'); hub=bot.community.games
    @group.command(name='connect_four',description='Challenge a member to Connect Four.')
    async def connect_four(i:discord.Interaction,opponent:discord.Member): await hub.start(i,'connect_four',opponent)
    @group.command(name='checkers',description='Challenge a member to American checkers.')
    async def checkers(i:discord.Interaction,opponent:discord.Member): await hub.start(i,'checkers',opponent)
    @group.command(name='chess',description='Challenge a member to chess with legal move validation.')
    async def chess_game(i:discord.Interaction,opponent:discord.Member): await hub.start(i,'chess',opponent)
    @group.command(name='battleship',description='Challenge a member to quick Battleship with private fleets.')
    async def battleship(i:discord.Interaction,opponent:discord.Member): await hub.start(i,'battleship',opponent)
    @group.command(name='hangman',description='Guess the hidden word before six mistakes.')
    async def hangman(i:discord.Interaction): await hub.start(i,'hangman')
    @group.command(name='sudoku',description='Start a unique-solution Sudoku puzzle.')
    @app_commands.choices(difficulty=[app_commands.Choice(name=x,value=x) for x in ['easy','medium','hard']])
    async def sudoku(i:discord.Interaction,difficulty:str='easy'): await hub.start(i,'sudoku',difficulty=difficulty)
    @group.command(name='memory',description='Find matching pairs in a 4×4 board.')
    async def memory(i:discord.Interaction): await hub.start(i,'memory')
    @group.command(name='anagram',description='Host a timed multiplayer anagram tournament.')
    async def anagram(i:discord.Interaction,rounds:app_commands.Range[int,2,10]=5): await hub.start(i,'anagram',rounds=rounds)
    @group.command(name='move',description='Make a move or submit a private tournament guess.')
    async def move(i:discord.Interaction,notation:str): await hub.move(i,notation)
    @group.command(name='board',description='Show your current board privately, including your Battleship fleet.')
    async def board(i:discord.Interaction):
        found=hub.find(i.guild_id,i.user.id)
        await reply(i,hub.private(found[1],i.user.id) if found else 'No active game.')
    @group.command(name='resign',description='End your active game or tournament.')
    async def resign(i:discord.Interaction): await hub.resign(i)

    @group.command(name='reversi',description='Challenge a member to Reversi with legal flips and automatic passes.')
    async def reversi(i:discord.Interaction,opponent:discord.Member):await hub.start(i,'reversi',opponent)
    @group.command(name='minesweeper',description='Reveal safe squares in a saved 6×6 Minesweeper puzzle.')
    @app_commands.choices(difficulty=[app_commands.Choice(name=x,value=x) for x in ['easy','medium','hard']])
    async def minesweeper(i:discord.Interaction,difficulty:str='easy'):await hub.start(i,'minesweeper',difficulty=difficulty)
    @group.command(name='word_search',description='Find hidden words in a saved 10×10 letter grid.')
    async def word_search(i:discord.Interaction):await hub.start(i,'word_search')
    @group.command(name='crossword',description='Solve a mini crossword with saved answers and crossing letters.')
    async def crossword(i:discord.Interaction):await hub.start(i,'crossword')
    @group.command(name='spelling',description='Spell words from clues across increasingly difficult levels.')
    async def spelling(i:discord.Interaction):await hub.start(i,'spelling')
    @group.command(name='resume',description='Resume one of your saved puzzles after a restart.')
    @app_commands.choices(kind=[app_commands.Choice(name=x,value=x) for x in SAVED_TYPES])
    async def resume(i:discord.Interaction,kind:str):
        if not hub.store.record(f'puzzle:{i.guild_id}:{i.user.id}:{kind}'):return await reply(i,'No saved puzzle of this type.')
        await hub.start(i,kind)
    @group.command(name='puzzle_reset',description='Discard your saved puzzle so the next start generates a new one.')
    @app_commands.choices(kind=[app_commands.Choice(name=x,value=x) for x in SAVED_TYPES])
    async def puzzle_reset(i:discord.Interaction,kind:str):
        if hub.find(i.guild_id,i.user.id):return await reply(i,'Resign from your active game first.')
        hub.store.delete_record(f'puzzle:{i.guild_id}:{i.user.id}:{kind}');await reply(i,'Saved puzzle reset.')
