"""Consent-based Discord game sessions. Hidden boards are returned ephemerally."""
import asyncio
import contextlib
import random
import time
import discord
from discord import app_commands
from vivi.bot import reply
from vivi.core.features import enabled
from vivi.games.game_engines import ConnectFour, Checkers, Chess, Hangman, Sudoku, Memory, Battleship, TicTacToe, WORD_BANK

from vivi.games.more_games import Reversi,SAVED_TYPES
from vivi.games.card_games import Blackjack,GoFish
from vivi.games.network_puzzles import NETWORK_TYPES,DIFFICULTIES,SIZES
SAVED_TYPES={**SAVED_TYPES,**NETWORK_TYPES}
CARD_TYPES={"blackjack":Blackjack,"go_fish":GoFish}
from vivi.games.game_design import THEMES,presentation,payload

class MoveModal(discord.ui.Modal,title='Your move'):
    value=discord.ui.TextInput(label='Move or guess',max_length=80)
    def __init__(self,hub,key):
        super().__init__(); self.hub=hub; self.key=key; self.game=hub.sessions.get(key)
        examples={'chess':'e2e4 or Nf3','checkers':'b6-d4-f2','sudoku':'A1=5','crossword':'1A=CAT','minesweeper':'A1 or flag A1','word_search':'A1-E1','battleship':'A1','anagram':'Your unscrambled word','hangman':'A letter or the whole word','blackjack':'hit or stand','go_fish':'A, 2–10, J, Q or K','pipe_connector':'A1 or A1 2','circuit_repair':'A1 or A1 3','laser_locks':'A1'}
        if self.game:self.value.placeholder=examples.get(self.game['kind'],'A coordinate or your answer')
    async def on_submit(self,i):
        if self.hub.sessions.get(self.key) is not self.game or i.guild_id!=self.key[0]: return await reply(i,'This game has ended. Use your current game’s controls.')
        await self.hub.move(i,str(self.value))

class CoordinateView(discord.ui.View):
    """Private row controls keep 6×6 boards usable within Discord's component limits."""
    def __init__(self,hub,key,owner,row):
        super().__init__(timeout=120);self.hub=hub;self.key=key;self.game=hub.sessions.get(key);self.owner=owner;self.mode='reveal'
        if self.game['kind']=='minesweeper':
            for label in ['Reveal','Flag','Unflag']:
                button=discord.ui.Button(label=label,row=0,style=discord.ButtonStyle.primary if label=='Reveal' else discord.ButtonStyle.secondary)
                async def choose_mode(i,value=label.lower()):
                    if not await self.allowed(i):return
                    self.mode=value
                    for item in self.children:
                        if item.row==0:item.style=discord.ButtonStyle.primary if item.label.lower()==value else discord.ButtonStyle.secondary
                    await i.response.edit_message(content='Mode: '+value+'. Choose a square in this row.',view=self)
                button.callback=choose_mode;self.add_item(button)
        width=getattr(self.game['engine'],'size',6) if self.game['kind'] in NETWORK_TYPES else 6
        for col in range(width):
            coordinate=f'{chr(65+col)}{row}';button=discord.ui.Button(label=coordinate,row=1+col//5)
            async def choose_square(i,value=coordinate):
                if not await self.allowed(i):return
                move=(self.mode+' ' if self.game['kind']=='minesweeper' else '')+value
                await self.hub.move(i,move)
            button.callback=choose_square;self.add_item(button)
    async def allowed(self,i):
        if i.guild_id!=self.key[0] or i.user.id!=self.owner or self.hub.sessions.get(self.key) is not self.game:
            await reply(i,'These controls belong to another player or an ended game.');return False
        return True

class GameView(discord.ui.View):
    def __init__(self,hub,key,invite=False):
        super().__init__(timeout=None); self.hub=hub; self.key=key; self.game=hub.sessions.get(key)
        for label in (['Accept','Decline'] if invite else ['Enter move','Private board','Resign']):
            button=discord.ui.Button(label=label,style=discord.ButtonStyle.success if label=='Accept' else discord.ButtonStyle.danger if label in {'Decline','Resign'} else discord.ButtonStyle.primary if label=='Enter move' else discord.ButtonStyle.secondary)
            if label=='Private board' and self.game and self.game['kind'] in CARD_TYPES:button.label='Private hand'
            async def callback(i,action=label):
                game=hub.sessions.get(key)
                if not game or game is not self.game or i.guild_id!=key[0] or i.user.id not in game['players']: return await reply(i,'This is not your active game.')
                if not enabled(hub.store,i.guild_id,'games'): return await reply(i,'Games are disabled here.')
                if action in {'Accept','Decline'}:
                    if i.user.id!=game['players'][1]: return await reply(i,'Only the challenged member can respond.')
                    if action=='Decline':
                        hub.sessions.pop(key,None);game['end_status']='Challenge declined.';await i.response.defer();return await hub.finish(game)
                    game['accepted']=True; game['expires']=time.time()+1800
                    await i.response.defer()
                    return await hub.update(game)
                if action=='Enter move': return await i.response.send_modal(MoveModal(hub,key))
                if action=='Private board': return await hub.send_board(i,game)
                await hub.resign(i)
            button.callback=callback; self.add_item(button)
        game=hub.sessions.get(key)
        if game and not invite and game['kind']=='blackjack':
            for action in ['Hit','Stand']:
                button=discord.ui.Button(label=action,row=1,style=discord.ButtonStyle.primary)
                async def play_card(i,value=action.lower()):
                    if hub.sessions.get(key) is not self.game or i.guild_id!=key[0] or i.user.id not in self.game['players']:return await reply(i,'This hand has ended.')
                    await hub.move(i,value)
                button.callback=play_card;self.add_item(button)
        if game and not invite and game['kind'] in {'memory','connect_four','tictactoe'}:
            moves=[str(n) for n in range(1,8)] if game['kind']=='connect_four' else [f'{chr(65+c)}{3-r}' for r in range(3) for c in range(3)] if game['kind']=='tictactoe' else [f'{chr(65+c)}{4-r}' for r in range(4) for c in range(4)]
            for n,move in enumerate(moves):
                engine=game['engine']; label=move
                if game['kind']=='memory':
                    if n in engine.matched or n in engine.shown: label=move+' '+engine.cards[n]
                if game['kind']=='tictactoe' and engine.cells[n]:label=move+' '+engine.cells[n]
                disabled=(game['kind']=='memory' and (n in engine.matched or n in engine.shown)) or (game['kind']=='tictactoe' and bool(engine.cells[n])) or (game['kind']=='connect_four' and bool(engine.cells[0][n]))
                button=discord.ui.Button(label=label,row=1+n//(3 if game['kind']=='tictactoe' else 4),disabled=disabled,style=discord.ButtonStyle.success if game['kind']=='memory' and n in engine.matched else discord.ButtonStyle.primary if game['kind']=='connect_four' else discord.ButtonStyle.secondary)
                async def choose(i,value=move):
                    found=hub.find(i.guild_id,i.user.id)
                    if not found or found[0]!=key or found[1] is not self.game: return await reply(i,'This is not your active game.')
                    await hub.move(i,value)
                button.callback=choose; self.add_item(button)
        if game and not invite and game['kind'] in {'minesweeper','battleship',*NETWORK_TYPES}:
            width=game['engine'].size if game['kind'] in NETWORK_TYPES else 6
            menu=discord.ui.Select(placeholder='Quick move: choose a row',row=1,options=[discord.SelectOption(label=f'Row {n}',value=str(n)) for n in range(width,0,-1)])
            async def choose_row(i):
                current=hub.sessions.get(key)
                if current is not self.game or i.guild_id!=key[0] or i.user.id not in current['players']:return await reply(i,'This is not your active game.')
                row=int(i.data['values'][0]);view=CoordinateView(hub,key,i.user.id,row)
                await i.response.send_message('Choose a column. These private controls last two minutes.',view=view,ephemeral=True)
            menu.callback=choose_row;self.add_item(menu)
        if game and not invite and game['kind']=='reversi':
            moves=[f'{chr(65+c)}{8-r}' for r,c in game['engine'].legal(game['engine'].turn)]
            for start in range(0,len(moves),25):
                menu=discord.ui.Select(placeholder='Choose a legal Reversi move',row=1+start//25,options=[discord.SelectOption(label=value,value=value) for value in moves[start:start+25]])
                async def choose_legal(i):
                    if hub.sessions.get(key) is not self.game or i.user.id not in self.game['players'] or i.guild_id!=key[0]:return await reply(i,'This is not your active game.')
                    await hub.move(i,i.data['values'][0])
                menu.callback=choose_legal;self.add_item(menu)

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
                    await i.response.defer()
                    return await hub.update(game)
                if action=='Start':
                    if i.user.id!=game['players'][0] or game['round']: return await reply(i,'Only the host can start this lobby.')
                    if len(game['players'])<2: return await reply(i,'At least two players must join.')
                    hub.next_round(game); await i.response.defer()
                    return await hub.update(game)
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
            visible=g['scores'] if g.get('finished') else g.get('shown_scores',g['scores'])
            scores=' · '.join(f'<@{u}>: {visible[u]}' for u in g['players'])
            if not g['round']: return 'Anagram tournament lobby. Join, then the host presses Start.\n'+scores
            return f'Anagram round {g["round"]}/{g["rounds"]}: **{g["scramble"]}** · <t:{int(g["deadline"])}:R>\n'+scores+('\n'+g.get('last',''))
        engine=g['engine']; board=engine.last if g['kind']=='battleship' else engine.board()
        if not g.get('accepted',True):return f'<@{g["players"][1]}>, accept or decline this {g["kind"]} challenge within two minutes.\n'+engine.help
        return f'**{g["kind"].title()}** · '+(' vs '.join(f'<@{u}>' for u in g['players']))+'\n'+board+'\n'+(engine.result if engine.done else f'Turn: <@{g["players"][engine.turn]}>')+'\n'+engine.help
    async def start(self,i,kind,opponent=None,difficulty='easy',rounds=5,size='small'):
        if not await self.service.need(i,'games'): return
        if self.find(i.guild_id,i.user.id): return await reply(i,'Finish your active game with /games resign first.')
        if sum(key[0]==i.guild_id for key in self.sessions)>=50: return await reply(i,'Server game limit reached. Try later.')
        if kind in CARD_TYPES and opponent and opponent.id==getattr(getattr(self.bot,'user',None),'id',None):opponent=None
        if opponent and (opponent.bot or opponent.id==i.user.id or self.find(i.guild_id,opponent.id)): return await reply(i,'Choose another available human member.')
        await i.response.defer()
        key=(i.guild_id,i.user.id)
        theme=self.store.profile(i.guild_id,i.user.id).get('game_theme','velvet')
        game=dict(theme=theme if theme in THEMES else 'velvet',ready=False,kind=kind,players=[i.user.id]+([opponent.id] if opponent else []),accepted=not opponent,expires=time.time()+(120 if opponent else 1800))
        if kind in CARD_TYPES and not opponent:
            game['vs_vivi']=True;game['players'].append(getattr(getattr(self.bot,'user',None),'id',None) or 1568121020047429775)
        if kind=='anagram': game.update(round=0,rounds=rounds,scores={i.user.id:0},words=random.sample(WORD_BANK,rounds),last='')
        else:
            factories={'tictactoe':TicTacToe,'connect_four':ConnectFour,'checkers':Checkers,'chess':Chess,'hangman':Hangman,'sudoku':lambda:Sudoku(difficulty),'memory':Memory,'battleship':Battleship,'reversi':Reversi,**SAVED_TYPES,**{name:(lambda factory=factory:factory(vs_vivi=not opponent)) for name,factory in CARD_TYPES.items()}}
            if kind=='minesweeper':factories[kind]=lambda:SAVED_TYPES[kind](difficulty)
            if kind in NETWORK_TYPES:factories[kind]=lambda:NETWORK_TYPES[kind](difficulty,size)
            saved=self.store.record(f'puzzle:{i.guild_id}:{i.user.id}:{kind}') if kind in SAVED_TYPES else None
            game['engine']=SAVED_TYPES[kind].load(saved['data']['state']) if saved else await asyncio.to_thread(factories[kind])
            if kind in NETWORK_TYPES:game['engine'].expire()
        game['key']=key
        # Recheck after off-thread Sudoku generation.
        if self.find(i.guild_id,i.user.id) or opponent and self.find(i.guild_id,opponent.id): return await reply(i,'A player started another game. Retry after it ends.')
        if sum(k[0]==i.guild_id for k in self.sessions)>=50:return await reply(i,'Server game limit reached. Try later.')
        self.sessions[key]=game
        self.save_puzzle(game)
        view=TournamentView(self,key) if kind=='anagram' else GameView(self,key,bool(opponent))
        try:
            options=await self.card(game)
            if self.sessions.get(key) is not game:
                if options.get('file'):options['file'].close()
                return await reply(i,'Game opening cancelled.')
            try:game['message']=await i.followup.send(view=view,wait=True,allowed_mentions=discord.AllowedMentions.none(),**options)
            except discord.HTTPException:
                game['text_only']=True
                game['message']=await i.followup.send(self.public(game),view=view,wait=True,allowed_mentions=discord.AllowedMentions.none())
            game['ready']=True
            if game.get('engine') and game['engine'].done:
                await self.update(game);self.sessions.pop(key,None);return
            if self.sessions.get(key) is not game:
                game.setdefault('end_status','Game opening cancelled.');await self.finish(game)
        except Exception:
            if self.sessions.get(key) is game:self.sessions.pop(key,None)
            raise

    async def card(self,g,viewer=None):
        if g.get('text_only'):return dict(content=self.private(g,viewer) if viewer is not None else self.public(g))
        try:return await payload(presentation(g,viewer),g['players'])
        except OSError as error:
            self.service.productivity.error('arcade rendering',error);g['text_only']=True
            return dict(content=self.private(g,viewer) if viewer is not None else self.public(g))

    async def send_board(self,i,g,format='image'):
        if i.user.id not in g['players']:return await reply(i,'This is not your game.')
        if format=='text':return await reply(i,self.private(g,i.user.id))
        await i.response.defer(ephemeral=True)
        data=presentation(g,i.user.id)
        theme=self.store.profile(i.guild_id,i.user.id).get('game_theme',g.get('theme','velvet'))
        data['theme']=theme if theme in THEMES else 'velvet'
        try:await i.followup.send(ephemeral=True,allowed_mentions=discord.AllowedMentions.none(),**await payload(data,g['players']))
        except (discord.HTTPException,OSError):await reply(i,self.private(g,i.user.id))

    def save_puzzle(self,g):
        if g['kind'] not in SAVED_TYPES:return
        ident=f'puzzle:{g["key"][0]}:{g["players"][0]}:{g["kind"]}'
        if g['engine'].done:self.store.delete_record(ident)
        else:self.store.put_record(g['key'][0],'puzzle_progress',dict(user=g['players'][0],kind=g['kind'],state=g['engine'].dump(),saved=time.time()),ident)

    def next_round(self,g):
        g['shown_scores']=dict(g['scores'])
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
        if not g.get('ready',True):return await reply(i,'Your game is opening. Try again in a moment.')
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
        if g.get('vs_vivi'):
            for _ in range(104):
                if engine.done or engine.turn!=1:break
                engine.bot_move()
            else:raise RuntimeError('Card AI exceeded its finite deck bound.')
        if g['kind'] in CARD_TYPES and engine.done:self.settle_cards(g)
        g['expires']=time.time()+1800
        self.save_puzzle(g)
        if g['kind']=='tictactoe' and engine.done and engine.result!='Draw!':self.service.reward(i.guild_id,i.user.id,0,'Tic-tac-toe winner')
        await i.response.defer(ephemeral=True)
        await self.update(g)
        if g['kind'] in {'battleship',*CARD_TYPES} and not g.get('text_only'):
            try:await i.followup.send(ephemeral=True,allowed_mentions=discord.AllowedMentions.none(),**await self.card(g,i.user.id))
            except discord.HTTPException:await reply(i,self.private(g,i.user.id))
        else:await reply(i,self.private(g,i.user.id) if g['kind'] in {'battleship',*CARD_TYPES} else 'Move recorded.',delete_after=None if g['kind'] in {'battleship',*CARD_TYPES} else 3)
        if engine.done:
            if self.sessions.get(key) is g:self.sessions.pop(key,None)
        elif isinstance(engine,Memory) and len(engine.shown)==2: g['hide_at']=time.time()+2
    def settle_cards(self,g):
        if g.get('settled'):return
        g['settled']=True
        for index,user in enumerate(g['players']):
            if g.get('vs_vivi') and index==1:continue
            profile=self.store.profile(g['key'][0],user)
            stats=profile.setdefault('arcade_cards',{}).setdefault(g['kind'],{'played':0,'wins':0,'chips':0})
            stats['played']+=1
            if index in g['engine'].winners:stats['wins']+=1;stats['chips']+=10
            self.store.save_profile(g['key'][0],user,profile)

    async def resign(self,i):
        found=self.find(i.guild_id,i.user.id)
        if not found: return await reply(i,'You have no active game.')
        key,g=found; self.sessions.pop(key,None)
        await i.response.defer(ephemeral=True)
        g['end_status']=f'Player {g["players"].index(i.user.id)+1} resigned.'
        await self.finish(g)
        await reply(i,'Game ended.')
    async def finish(self,g):
        await self.update(g,final=True)

    async def update(self,g,final=False):
        if not g.get('ready',True):return
        if not final and self.sessions.get(g['key']) is not g:return
        async with g.setdefault('_render_lock',asyncio.Lock()):
            if not final and self.sessions.get(g['key']) is not g:return
            options=await self.card(g)
            if not final and self.sessions.get(g['key']) is not g:
                if options.get('file'):options['file'].close()
                return
            done=final or g.get('finished') or (g.get('engine') and g['engine'].done)
            view=None if done else TournamentView(self,g['key']) if g['kind']=='anagram' else GameView(self,g['key'])
            try:
                if 'file' in options:
                    file=options.pop('file');await g['message'].edit(content=None,attachments=[file],view=view,allowed_mentions=discord.AllowedMentions.none(),**options)
                else:await g['message'].edit(embed=None,attachments=[],view=view,allowed_mentions=discord.AllowedMentions.none(),**options)
            except discord.HTTPException:
                g['text_only']=True
                with contextlib.suppress(discord.HTTPException):await g['message'].edit(content=g.get('end_status') or self.public(g),embed=None,attachments=[],view=view,allowed_mentions=discord.AllowedMentions.none())

    async def tick(self):
        now=time.time()
        for key,g in list(self.sessions.items()):
            if self.sessions.get(key) is not g:continue
            if g['kind'] in NETWORK_TYPES and g['engine'].expire(now):
                self.save_puzzle(g);self.sessions.pop(key,None);await self.finish(g);continue
            if g['expires']<now or not enabled(self.store,key[0],'games'):
                self.sessions.pop(key,None)
                g['end_status']='Game ended: timeout or games disabled.'
                await self.finish(g)
                continue
            if g.get('hide_at',now+1)<=now:
                g.pop('hide_at'); g['engine'].shown=[]; await self.update(g)
            if g['kind']=='anagram' and g['round'] and g['deadline']<=now:
                g['last']='Previous answer: '+g['word']
                if g['round']>=g['rounds']:
                    self.sessions.pop(key,None)
                    g['finished']=True;await self.finish(g)
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
    cards=app_commands.Group(name='cards',description='Private card games against Vivi or a member',guild_only=True)
    puzzles=app_commands.Group(name='puzzles',description='Procedural rotation puzzles with saved progress',guild_only=True)
    bot.tree.add_command(cards);bot.tree.add_command(puzzles)
    @cards.command(name='blackjack',description='Practice blackjack against Vivi, or challenge a member. No real-money bets.')
    async def blackjack(i:discord.Interaction,opponent:discord.Member=None):await hub.start(i,'blackjack',opponent)
    @cards.command(name='go_fish',description='Collect books of four against Vivi, or challenge a member.')
    async def go_fish(i:discord.Interaction,opponent:discord.Member=None):await hub.start(i,'go_fish',opponent)
    @cards.command(name='profile',description='View your saved card-game wins and fictional practice chips privately.')
    async def card_profile(i:discord.Interaction):
        if not await hub.service.need(i,'games'):return
        stats=hub.store.profile(i.guild_id,i.user.id).get('arcade_cards',{})
        card=discord.Embed(title='Vivi · Your card profile',description='Fictional practice chips only. No bets, purchases, transfers or cash value.',color=0xe4a3bc)
        for kind in CARD_TYPES:
            values=stats.get(kind,{})
            card.add_field(name=kind.replace('_',' ').title(),value=f"Played: {values.get('played',0)} · Wins: {values.get('wins',0)} · Chips: {values.get('chips',0)}",inline=False)
        await i.response.send_message(embed=card,ephemeral=True)
    def register_network(kind):
        async def play(i:discord.Interaction,difficulty:str='easy',size:str='small'):
            await hub.start(i,kind,difficulty=difficulty,size=size)
        play=app_commands.choices(difficulty=[app_commands.Choice(name=x.title(),value=x) for x in DIFFICULTIES],size=[app_commands.Choice(name=f'{x.title()} ({n}×{n})',value=x) for x,n in SIZES.items()])(play)
        puzzles.command(name=kind,description={'pipe_connector':'Connect the pipeline before water arrives; generated, saved maps.','circuit_repair':'Rotate wires to power every tile of a generated circuit.','laser_locks':'Redirect a beam through mirrors to unlock the receiver.'}[kind])(play)
    for kind in NETWORK_TYPES:register_network(kind)
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
    @app_commands.choices(format=[app_commands.Choice(name='Image card',value='image'),app_commands.Choice(name='Text / screen reader',value='text')])
    async def board(i:discord.Interaction,format:str='image'):
        found=hub.find(i.guild_id,i.user.id)
        if not found:return await reply(i,'No active game.')
        await hub.send_board(i,found[1],format)
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

    @group.command(name='theme',description='Choose your arcade colors; hosts also update their active public game.')
    @app_commands.choices(theme=[app_commands.Choice(name=x.title(),value=x) for x in THEMES])
    async def theme(i:discord.Interaction,theme:str):
        profile=hub.store.profile(i.guild_id,i.user.id);profile['game_theme']=theme;hub.store.save_profile(i.guild_id,i.user.id,profile)
        found=hub.find(i.guild_id,i.user.id)
        if found and found[1]['players'][0]==i.user.id:
            found[1]['theme']=theme;await i.response.defer(ephemeral=True);await hub.update(found[1])
        await reply(i,'Arcade theme saved: '+theme.title()+'.')
