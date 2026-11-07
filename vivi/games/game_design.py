"""Portable arcade cards. Renderers receive redacted presentation data, never engine secrets."""
import asyncio
import io
import math
from pathlib import Path
from functools import lru_cache
import discord
from PIL import Image,ImageDraw,ImageFont

THEMES={
 'velvet':dict(background='#171322',panel='#252035',tile='#342b47',accent='#e4a3bc',second='#b9aff0',text='#f7f0fa',muted='#b9accb'),
 'moonlight':dict(background='#111d2c',panel='#1b2d40',tile='#2c4157',accent='#8bd5df',second='#c6b8f0',text='#f1f7fc',muted='#a5b9cc'),
 'garden':dict(background='#142323',panel='#203637',tile='#30494a',accent='#a5d5b0',second='#f0c7bc',text='#f1faf4',muted='#afc6be')}
TITLES={'connect_four':'Connect Four','word_search':'Word Search','tictactoe':'Tic-Tac-Toe','anagram':'Anagram Tournament'}
FRUITS=dict(zip('🍎🍊🍋🍇🍓🍒🥝🍉',['apple','orange','lemon','grape','berry','cherry','kiwi','melon']))
ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=32)
def font(size,mono=False):
    return ImageFont.truetype(str(ROOT/'assets/fonts/mono.ttf'),size) if mono else ImageFont.load_default(size=size)


def presentation(game,viewer=None):
    """All hidden answers/ships/cards are removed synchronously before any worker starts."""
    kind=game['kind'];engine=game.get('engine');done=bool(engine and engine.done)
    data=dict(kind=kind,title=TITLES.get(kind,kind.replace('_',' ').title()),done=done,turn=getattr(engine,'turn',0),status=getattr(engine,'result','') if done else 'Your next move',help=getattr(engine,'help','Join the lobby, then the host starts.'),theme=game.get('theme','velvet'),players_count=len(game['players']))
    if game.get('end_status'):data.update(done=True,status=game['end_status'])
    if kind=='anagram':
        data.update(round=game['round'],rounds=game['rounds'],letters=game.get('scramble',''),scores=[(f'Player {n+1}',(game['scores'] if game.get('finished') else game.get('shown_scores',game['scores']))[u]) for n,u in enumerate(game['players'])],previous=game.get('last',''),deadline=int(game.get('deadline',0)))
        if game.get('finished'):data.update(done=True,status='Tournament complete')
        return data
    if not game.get('accepted',True) and not data['done']:data['status']='Waiting for your opponent'
    if kind in {'blackjack','go_fish'}:
        if viewer is not None and viewer not in game['players']:raise ValueError('This hand belongs to another player.')
        player=game['players'].index(viewer) if viewer is not None else None
        data.update(private=player is not None,vs_vivi=game.get('vs_vivi',False))
        if kind=='blackjack':
            from vivi.games.card_games import total
            data.update(hands=engine.visible(player),stats=['Practice chips only','10 chips per win','Vivi stands on soft 17' if game.get('vs_vivi') else 'Head-to-head: closest to 21'])
            data['scores']=[total(hand) if engine.done or player==n else None for n,hand in enumerate(engine.hands)]
        else:
            from vivi.games.card_games import RANKS
            data['hand_counts']=[f'{rank}: {sum(card[:-1]==rank for card in engine.hands[player])}' for rank in RANKS if player is not None and any(card[:-1]==rank for card in engine.hands[player])]
            data.update(hand=list(engine.hands[player]) if player is not None else None,counts=[len(hand) for hand in engine.hands],books=[list(books) for books in engine.books],last=engine.last,stats=[f'Player {n+1}: {len(books)} books' for n,books in enumerate(engine.books)]+[f'{len(engine.deck)} cards in deck'])
        return data
    if kind in {'pipe_connector','circuit_repair','laser_locks'}:
        data.update(grid=[list(row) for row in engine.cells],stats=[f'{engine.size} x {engine.size} map',engine.difficulty.title(),f'{engine.moves} rotations'],highlight=[])
        if kind=='laser_locks':data['beam']=[list(cell) for cell in engine.beam()[0]]
        else:
            powered,leaks=engine.trace();data['highlight']=[list(cell) for cell in powered]
            data['stats'].append(f'{len(powered)} / {engine.size**2} tiles powered' if kind=='circuit_repair' else f'{len(powered)} connected tiles')
        if engine.deadline:data['deadline']=int(engine.deadline);data['stats'].append('Water arrives at the shown time')
        return data
    if kind=='tictactoe':data['grid']=[engine.cells[r*3:r*3+3] for r in range(3)]
    elif kind=='connect_four':data['stats']=[f'Player 1: {sum(row.count(1) for row in engine.cells)} discs',f'Player 2: {sum(row.count(2) for row in engine.cells)} discs'];data['grid']=[list(row) for row in engine.cells]
    elif kind=='chess':
        data['grid']=[[None]*8 for _ in range(8)]
        for square,piece in engine.position.piece_map().items():data['grid'][7-square//8][square%8]=dict(piece=piece.symbol().lower(),side=0 if piece.color else 1)
        data['highlight']=[]
        if engine.position.move_stack:
            last=engine.position.peek();data['highlight']=[[7-square//8,square%8] for square in [last.from_square,last.to_square]]
    elif kind=='checkers':
        data['grid']=[[None]*8 for _ in range(8)]
        for (r,c),(side,king) in engine.cells.items():data['grid'][r][c]=dict(side=side,king=king)
    elif kind=='reversi':data.update(grid=[list(row) for row in engine.cells],legal=[list(x) for x in engine.legal(engine.turn)] if not done else [],stats=[f'Player 1: {sum(row.count(1) for row in engine.cells)} pieces',f'Player 2: {sum(row.count(2) for row in engine.cells)} pieces'])
    elif kind=='sudoku':data.update(grid=[engine.cells[r*9:r*9+9] for r in range(9)],clues=sorted(engine.clues),stats=[engine.difficulty.title(),f'{sum(bool(x) for x in engine.cells)} / 81 cells filled'])
    elif kind=='memory':
        data['grid']=[[dict(face=FRUITS.get(engine.cards[r*4+c],engine.cards[r*4+c]) if r*4+c in engine.matched or r*4+c in engine.shown else None,matched=r*4+c in engine.matched) for c in range(4)] for r in range(4)]
        data['stats']=[f'{len(engine.matched)//2} / 8 pairs',f'{engine.tries} attempts']
    elif kind=='hangman':data.update(letters=[c.upper() if c in engine.guesses or done else '' for c in engine.word],errors=engine.errors,guesses=sorted(engine.guesses),stats=[f'{6-engine.errors} mistakes remaining'])
    elif kind=='minesweeper':
        data['grid']=[['mine' if done and n in engine.mines else 'flag' if n in engine.flags else sum(x in engine.mines for x in engine.neighbors(n)) if n in engine.revealed else None for n in range(r*6,r*6+6)] for r in range(6)]
        data['stats']=[f'{engine.count} mines',f'{len(engine.flags)} flags placed',f'{len(engine.revealed)} / {36-engine.count} safe cells']
    elif kind=='word_search':
        data.update(grid=[list(row) for row in engine.cells],words=list(engine.words),found=list(engine.found),highlight=[list(cell) for word in engine.found for cell in engine.words[word]],stats=[f'{len(engine.found)} / {len(engine.words)} words found'])
    elif kind=='crossword':
        from vivi.games.more_games import CROSSWORDS
        rows=[['#' if c=='#' else '' for c in row] for row in CROSSWORDS[engine.pack][0]]
        for clue,answer in engine.answers.items():
            for (r,c),letter in zip(engine.paths[clue],answer):rows[r][c]=letter
        data.update(grid=rows,clues_text=[key+' '+value[1]+(' [solved]' if key in engine.answers else '') for key,value in CROSSWORDS[engine.pack][1].items()],stats=[f'{len(engine.answers)} / 4 clues solved'])
    elif kind=='spelling':
        from vivi.games.more_games import SPELLING
        data.update(clue=SPELLING[engine.index][1] if not done else engine.result,word_length=len(SPELLING[engine.index][0]) if not done else 0,stats=[f'Level {min(engine.index+1,len(SPELLING))} / {len(SPELLING)}',f'{engine.errors} / 3 mistakes'])
    elif kind=='battleship':
        data['last']=engine.last
        if viewer is None:data.update(private=False,stats=['6 x 6 ocean','Fleet: 3, 2, 2','Open Private board to aim'])
        else:
            if viewer not in game['players']:raise ValueError('This fleet belongs to another player.')
            player=game['players'].index(viewer);data['private']=True
            data['own']=[['hit' if (r,c) in engine.shots[1-player] and (r,c) in engine.fleets[player] else 'miss' if (r,c) in engine.shots[1-player] else 'ship' if (r,c) in engine.fleets[player] else None for c in range(6)] for r in range(6)]
            data['target']=[['hit' if (r,c) in engine.shots[player] and (r,c) in engine.fleets[1-player] else 'miss' if (r,c) in engine.shots[player] else None for c in range(6)] for r in range(6)]
    return data


def legacy_presentation(view,status=''):
    data=dict(kind='trivia' if view.trivia else 'tictactoe',title='Trivia' if view.trivia else 'Tic-Tac-Toe',done=view.done,turn=view.turn,status=status or 'Choose your next move',help='Use the answer buttons below.' if view.trivia else 'Choose a square below. Connect three Xs or Os.',theme=getattr(view,'theme','velvet'),players_count=len(view.players))
    if view.trivia:data.update(question=view.trivia[0],choices=list(view.trivia[1]),correct=view.trivia[2] if view.done else None,selected=getattr(view,'selected',None))
    else:data['grid']=[view.board[r*3:r*3+3] for r in range(3)]
    return data


def centered(draw,xy,text,size,fill,mono=False):draw.text(xy,str(text),font=font(size,mono),fill=fill,anchor='mm')
def wrapped(draw,xy,text,width,size,fill,line_height=None,max_lines=8):
    x,y=xy;line='';lines=[]
    for word in str(text).split():
        candidate=(line+' '+word).strip()
        if draw.textlength(candidate,font=font(size))>width and line:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    for n,line in enumerate(lines[:max_lines]):draw.text((x,y+n*(line_height or size+7)),line,font=font(size),fill=fill)
    return y+min(len(lines),max_lines)*(line_height or size+7)


def chess_piece(draw,x,y,size,piece,side,palette):
    fill='#f6edf7' if side==0 else '#655374';outline='#7f638f' if side==0 else '#e4d5ed'
    def point(a,b):return (x+a*size,y+b*size)
    def polygon(points):draw.polygon([point(a,b) for a,b in points],fill=fill,outline=outline,width=2)
    def ellipse(box):draw.ellipse((*point(*box[:2]),*point(*box[2:])),fill=fill,outline=outline,width=2)
    polygon([(0.2,0.84),(0.8,0.84),(0.75,0.94),(0.25,0.94)])
    if piece=='p':ellipse((.33,.14,.67,.48));polygon([(.43,.48),(.57,.48),(.66,.8),(.34,.8)])
    elif piece=='r':polygon([(.24,.15),(.38,.15),(.38,.3),(.46,.3),(.46,.15),(.56,.15),(.56,.3),(.64,.3),(.64,.15),(.78,.15),(.75,.4),(.65,.45),(.65,.8),(.35,.8),(.35,.45),(.25,.4)])
    elif piece=='n':polygon([(.3,.8),(.7,.8),(.68,.5),(.8,.35),(.57,.18),(.48,.08),(.4,.22),(.23,.49),(.42,.53),(.53,.4),(.42,.65)]);draw.ellipse((*point(.54,.25),*point(.6,.31)),fill=outline)
    elif piece=='b':ellipse((.32,.16,.68,.58));draw.line((*point(.6,.17),*point(.44,.42)),fill=outline,width=3);polygon([(.45,.55),(.55,.55),(.68,.8),(.32,.8)])
    elif piece=='q':polygon([(.28,.45),(.16,.2),(.38,.36),(.5,.12),(.62,.36),(.84,.2),(.72,.45),(.62,.8),(.38,.8)]);ellipse((.44,.06,.56,.18))
    else:
        polygon([(.4,.4),(.6,.4),(.7,.8),(.3,.8)]);draw.line((*point(.5,.09),*point(.5,.42)),fill=fill,width=max(3,int(size*.1)));draw.line((*point(.35,.22),*point(.65,.22)),fill=fill,width=max(3,int(size*.1)))


def fruit(draw,x,y,size,kind,palette):
    colors={'apple':'#e895ad','orange':'#efb97e','lemon':'#e8dc96','grape':'#b4a0df','berry':'#ed9aaa','cherry':'#dc91b1','kiwi':'#b5d591','melon':'#8ec7ac'};color=colors.get(kind,palette['accent']);cx=x+size/2;cy=y+size/2;radius=size*.23
    if kind=='grape':
        for dx,dy in [(-.12,-.12),(.12,-.12),(0,.04),(-.1,.12),(.1,.12),(0,.25)]:draw.ellipse((cx+dx*size-radius*.6,cy+dy*size-radius*.6,cx+dx*size+radius*.6,cy+dy*size+radius*.6),fill=color)
    elif kind=='berry':draw.polygon([(cx-radius,cy-radius),(cx+radius,cy-radius),(cx,cy+radius*1.5)],fill=color)
    elif kind=='cherry':
        for dx in [-.13,.13]:draw.ellipse((cx+dx*size-radius*.7,cy-radius*.25,cx+dx*size+radius*.7,cy+radius*1.2),fill=color);draw.line((cx+dx*size,cy,cx,cy-radius*1.5),fill='#a8cfa7',width=3)
    else:
        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=color)
        if kind=='kiwi':draw.ellipse((cx-radius*.65,cy-radius*.65,cx+radius*.65,cy+radius*.65),fill='#e2e7b5')
        if kind=='melon':
            for dx in [-.12,0,.12]:draw.line((cx+dx*size,cy-radius*.7,cx+dx*size,cy+radius*.7),fill='#4e9376',width=2)
    draw.ellipse((cx-2,cy-radius-8,cx+12,cy-radius+1),fill='#a2c79d')


def board(draw,data,palette,xy=(70,165),box=520,key='grid',caption=None):
    rows=data[key];height=len(rows);width=len(rows[0]);cell=min(box/width,box/height);x0,y0=xy;kind=data['kind']
    if caption:draw.text((x0,y0-45),caption,font=font(22),fill=palette['text'])
    for c in range(width):centered(draw,(x0+(c+.5)*cell,y0-18),str(c+1) if kind=='connect_four' else chr(65+c),17,palette['muted'],True)
    for r,row in enumerate(rows):
        centered(draw,(x0-23,y0+(r+.5)*cell),height-r,17,palette['muted'],True)
        for c,value in enumerate(row):
            x,y=x0+c*cell,y0+r*cell;inset=3 if kind not in {'chess','checkers','sudoku','word_search'} else 1
            fill=palette['tile']
            if kind in {'chess','checkers'}:fill='#cbb6cf' if (r+c)%2==0 else '#62516f'
            if [r,c] in data.get('highlight',[]):fill='#9a758b' if kind=='chess' else '#66587b'
            if kind=='crossword' and value=='#':fill=palette['background']
            if kind=='memory' and value['matched']:fill='#3c655c'
            draw.rounded_rectangle((x+inset,y+inset,x+cell-inset,y+cell-inset),radius=8 if inset>1 else 1,fill=fill)
            center=(x+cell/2,y+cell/2)
            if kind in {'pipe_connector','circuit_repair','laser_locks'}:
                ink=palette['accent'] if [r,c] in data.get('highlight',[]) else palette['second']
                if kind=='laser_locks':
                    if [r,c] in data.get('beam',[]):draw.ellipse((center[0]-3,center[1]-3,center[0]+3,center[1]+3),fill=palette['accent'])
                    if value in {1,2}:
                        endpoints=(x+cell*.22,y+cell*.78,x+cell*.78,y+cell*.22) if value==1 else (x+cell*.22,y+cell*.22,x+cell*.78,y+cell*.78)
                        draw.line(endpoints,fill=palette['second'],width=max(3,int(cell*.07)))
                    elif value==3:draw.rectangle((x+cell*.2,y+cell*.2,x+cell*.8,y+cell*.8),fill=palette['muted'])
                else:
                    for direction,(dr,dc) in enumerate([(-1,0),(0,1),(1,0),(0,-1)]):
                        if value&(1<<direction):draw.line((center[0],center[1],center[0]+dc*(cell/2-4),center[1]+dr*(cell/2-4)),fill=ink,width=max(3,int(cell*.12)))
                    draw.ellipse((center[0]-3,center[1]-3,center[0]+3,center[1]+3),fill=ink)
                if (r,c)==(0,0):draw.text((x+4,y+3),'S',font=font(max(10,int(cell*.25))),fill=palette['text'])
                if kind!='circuit_repair' and (r,c)==(height-1,width-1):draw.text((x+4,y+3),'R',font=font(max(10,int(cell*.25))),fill=palette['text'])
            elif kind=='chess' and value:chess_piece(draw,x+cell*.1,y+cell*.05,cell*.8,value['piece'],value['side'],palette)
            elif kind=='checkers' and value:
                color=palette['accent'] if value['side']==0 else palette['second'];draw.ellipse((x+cell*.17,y+cell*.17,x+cell*.83,y+cell*.83),fill=color,outline='#f2e7f1',width=2)
                if value['king']:centered(draw,center,'K',int(cell*.35),palette['background'],True)
            elif kind in {'connect_four','reversi'}:
                radius=cell*.34;color=palette['background'] if not value else palette['accent'] if value==1 else palette['second']
                draw.ellipse((center[0]-radius,center[1]-radius,center[0]+radius,center[1]+radius),fill=color)
                if value:centered(draw,center,'1' if value==1 else '2',int(cell*.25),palette['background'],True)
                elif [r,c] in data.get('legal',[]):draw.ellipse((center[0]-5,center[1]-5,center[0]+5,center[1]+5),fill=palette['accent'])
            elif kind=='memory':
                if value['face']:fruit(draw,x,y,cell,value['face'],palette)
                else:
                    draw.ellipse((center[0]-16,center[1]-16,center[0]+16,center[1]+16),outline=palette['second'],width=2);centered(draw,center,'?',24,palette['second'])
            elif kind=='minesweeper':
                if value=='flag':draw.line((x+cell*.4,y+cell*.25,x+cell*.4,y+cell*.8),fill=palette['text'],width=3);draw.polygon([(x+cell*.4,y+cell*.25),(x+cell*.75,y+cell*.4),(x+cell*.4,y+cell*.52)],fill=palette['accent'])
                elif value=='mine':draw.ellipse((x+cell*.3,y+cell*.3,x+cell*.7,y+cell*.7),fill=palette['accent']);draw.line((x+cell*.2,y+cell*.2,x+cell*.8,y+cell*.8),fill=palette['accent'],width=3)
                elif value is not None:centered(draw,center,str(value) if value else '·',int(cell*.4),palette['text'] if value else palette['muted'],True)
            elif kind=='battleship':
                if value=='ship':draw.rounded_rectangle((x+cell*.15,y+cell*.35,x+cell*.85,y+cell*.65),radius=6,fill=palette['second'])
                elif value=='hit':
                    draw.line((x+cell*.3,y+cell*.3,x+cell*.7,y+cell*.7),fill=palette['accent'],width=5);draw.line((x+cell*.7,y+cell*.3,x+cell*.3,y+cell*.7),fill=palette['accent'],width=5)
                elif value=='miss':draw.ellipse((center[0]-5,center[1]-5,center[0]+5,center[1]+5),outline=palette['muted'],width=2)
            elif kind=='tictactoe':
                if value=='X':
                    for a,b in [((.28,.28),(.72,.72)),((.72,.28),(.28,.72))]:draw.line((x+cell*a[0],y+cell*a[1],x+cell*b[0],y+cell*b[1]),fill=palette['accent'],width=8)
                elif value=='O':draw.ellipse((x+cell*.27,y+cell*.27,x+cell*.73,y+cell*.73),outline=palette['second'],width=8)
            elif kind in {'sudoku','word_search','crossword'} and value and value!='#':
                color=palette['text'] if kind!='sudoku' or r*9+c in data['clues'] else palette['accent'];centered(draw,center,value,int(cell*.47),color,True)
            if kind=='crossword' and (r,c) in {(0,0),(0,2),(2,0)}:draw.text((x+6,y+5),{(0,0):'1',(0,2):'2',(2,0):'3'}[(r,c)],font=font(15),fill=palette['muted'])
    if kind=='laser_locks':
        path=data.get('beam',[])
        for a,b in zip(path,path[1:]):
            draw.line((x0+(a[1]+.5)*cell,y0+(a[0]+.5)*cell,x0+(b[1]+.5)*cell,y0+(b[0]+.5)*cell),fill=palette['accent'],width=max(2,int(cell*.045)))
    if kind=='sudoku':
        for n in [0,3,6,9]:draw.line((x0+n*cell,y0,x0+n*cell,y0+9*cell),fill=palette['second'],width=3);draw.line((x0,y0+n*cell,x0+9*cell,y0+n*cell),fill=palette['second'],width=3)


def draw_cards(draw,cards,palette,x,y):
    # Wrap compact cards instead of clipping large Go Fish hands.
    width=52 if len(cards)>12 else 68;step=width+7;columns=int(510/step)
    for index,card in enumerate(cards):
        px=x+(index%columns)*step;py=y+(index//columns)*88
        if py+78>700:break
        hidden=card=='??';fill=palette['tile'] if hidden else '#f8f0f6'
        draw.rounded_rectangle((px,py,px+width,py+78),radius=7,fill=fill,outline=palette['accent'],width=2)
        if hidden:centered(draw,(px+width/2,py+39),'V',25,palette['accent'])
        else:
            ink='#aa285c' if card[-1] in 'HD' else '#251d34'
            draw.text((px+6,py+6),card[:-1],font=font(19),fill=ink)
            centered(draw,(px+width/2,py+51),card[-1],20,ink)


def render(data):
    palette=THEMES.get(data.get('theme'),THEMES['velvet']);image=Image.new('RGB',(960,760),palette['background']);draw=ImageDraw.Draw(image)
    # Restrained original line art keeps the design portable and legible at Discord sizes.
    for n in range(5):draw.arc((650+n*25,-200+n*20,1200+n*30,400+n*30),0,360,fill=palette['tile'],width=2)
    draw.rounded_rectangle((20,20,940,740),radius=25,outline=palette['tile'],width=2)
    draw.text((45,37),'V I V I  /  A R C A D E',font=font(15),fill=palette['accent']);draw.text((45,64),data['title'],font=font(34),fill=palette['text'])
    status=data.get('status') if data.get('done') or 'Waiting' in data.get('status','') else ('LOBBY OPEN' if not data.get('round') else f'ROUND {data["round"]} / {data["rounds"]}') if data['kind']=='anagram' else 'CHOOSE AN ANSWER' if data['kind']=='trivia' else 'YOUR TURN' if data.get('players_count')==1 else f'PLAYER {data.get("turn",0)+1} TO MOVE'
    draw.rounded_rectangle((655,54,913,100),radius=15,fill=palette['tile']);wrapped(draw,(672,65),status or 'GAME COMPLETE',225,16,palette['accent'],max_lines=1)
    kind=data['kind'];draw.rounded_rectangle((42,130,625,711),radius=20,fill=palette['panel'])
    if kind=='battleship' and data.get('private'):
        draw.rounded_rectangle((640,130,920,711),radius=20,fill=palette['panel'])
        # Both private boards have the same readable scale; no public ship coordinates exist.
        draw.rounded_rectangle((42,130,920,711),radius=20,fill=palette['panel'])
        board(draw,data,palette,(78,220),350,'own','YOUR FLEET');board(draw,data,palette,(535,220),350,'target','YOUR SHOTS')
        wrapped(draw,(78,615),data.get('last',''),790,20,palette['text']);wrapped(draw,(78,655),'Ships = lavender  |  X = hit  |  circle = miss',790,16,palette['muted'])
    else:
        if 'grid' in data:board(draw,data,palette)
        elif kind in {'blackjack','go_fish'}:
            if kind=='blackjack':
                for player,hand in enumerate(data['hands']):
                    y=180+player*220;name='Vivi' if data.get('vs_vivi') and player==1 else f'Player {player+1}'
                    draw.text((75,y),name+(f" / {data['scores'][player]}" if data['scores'][player] is not None else ''),font=font(22),fill=palette['accent'])
                    draw_cards(draw,hand,palette,75,y+40)
            else:
                draw.text((75,170),'BOOKS OF FOUR',font=font(22),fill=palette['accent'])
                for player,books in enumerate(data['books']):wrapped(draw,(75,215+player*65),f'Player {player+1}: '+(', '.join(books) or 'No books yet'),500,21,palette['text'])
                if data['hand'] is not None:
                    draw.text((75,370),'YOUR PRIVATE HAND',font=font(18),fill=palette['accent']);wrapped(draw,(75,410),'  '.join(data['hand_counts']),480,24,palette['text'],line_height=35,max_lines=5) if len(data['hand'])>18 else draw_cards(draw,data['hand'],palette,75,410)
                else:wrapped(draw,(75,390),'Hands stay private. Open Private hand to see yours, then ask for a rank using Enter move.',490,27,palette['text'],max_lines=5)
                wrapped(draw,(75,615),data.get('last',''),490,17,palette['muted'],max_lines=3)
        elif kind=='hangman':
            draw.line((150,440,370,440),fill=palette['muted'],width=5);draw.line((195,440,195,200,325,200,325,240),fill=palette['muted'],width=5)
            errors=data['errors']
            if errors>=1:draw.ellipse((303,240,347,284),outline=palette['accent'],width=4)
            for step,points in [(2,(325,284,325,350)),(3,(325,301,287,325)),(4,(325,301,363,325)),(5,(325,350,293,390)),(6,(325,350,357,390))]:
                if errors>=step:draw.line(points,fill=palette['accent'],width=4)
            letters=data['letters'];size=min(58,480/max(1,len(letters)));start=75+(500-len(letters)*size)/2
            for n,letter in enumerate(letters):
                x=start+n*size;draw.line((x+3,540,x+size-5,540),fill=palette['second'],width=3)
                if letter:centered(draw,(x+size/2,510),letter,int(size*.65),palette['text'],True)
            wrapped(draw,(78,585),'Guessed: '+', '.join(data['guesses']),490,17,palette['muted'],max_lines=3)
        elif kind in {'anagram','spelling'}:
            if kind=='anagram':
                draw.text((80,175),f'ROUND {data["round"]} / {data["rounds"]}' if data['round'] else 'YOUR NEXT WORD NIGHT',font=font(20),fill=palette['accent'])
                letters=data['letters'].upper();size=min(66,490/max(1,len(letters)))
                for n,letter in enumerate(letters):
                    x=78+n*size;draw.rounded_rectangle((x,285,x+size-6,360),radius=10,fill=palette['tile']);centered(draw,(x+(size-6)/2,322),letter,32,palette['text'],True)
                wrapped(draw,(80,440),data.get('previous') or ('Join the lobby. The host starts when everyone is ready.' if not data['round'] else 'Submit guesses privately. Scores are revealed when the round ends.'),475,22,palette['muted'])
            else:
                draw.text((80,180),'SPELLING CHALLENGE',font=font(19),fill=palette['accent']);wrapped(draw,(80,245),data['clue'],465,31,palette['text'],line_height=43,max_lines=5)
                if data['word_length']:draw.text((80,540),str(data['word_length'])+' letters',font=font(24),fill=palette['second'])
        elif kind=='battleship':
            draw.text((80,180),'HIDDEN FLEETS',font=font(22),fill=palette['accent'])
            for n in range(5):draw.arc((80,280+n*45,580,360+n*45),0,180,fill=palette['second'],width=3)
            wrapped(draw,(80,570),data['last'],480,23,palette['text'],max_lines=3)
        elif kind=='trivia':
            wrapped(draw,(75,162),data['question'],510,26,palette['text'],line_height=33,max_lines=3)
            for n,choice in enumerate(data['choices']):
                y=300+n*87;fill=palette['tile'] if n!=data.get('correct') else '#3b6659'
                draw.rounded_rectangle((70,y,598,y+72),radius=12,fill=fill);centered(draw,(96,y+35),chr(65+n),22,palette['accent'],True);wrapped(draw,(125,y+18),choice,445,19,palette['text'],max_lines=2)
        sidebar(draw,data,palette)
    draw.text((48,724),'VIVI ARCADE  /  '+data.get('theme','velvet').upper()+' EDITION',font=font(11),fill=palette['muted'])
    out=io.BytesIO();image.save(out,format='PNG',optimize=True);return out.getvalue()


def sidebar(draw,data,palette):
    draw.rounded_rectangle((648,130,917,711),radius=20,fill=palette['panel']);x=670;y=155
    draw.text((x,y),'GAME STATUS',font=font(15),fill=palette['accent']);y+=35
    lines=data.get('stats',[])
    if data['kind']=='anagram':lines=[f'{name}   {score} pts' for name,score in sorted(data['scores'],key=lambda x:x[1],reverse=True)]
    for line in lines:y=wrapped(draw,(x,y),line,220,20,palette['text'],max_lines=2)+12
    if data['kind']=='word_search':
        for word in data['words']:draw.text((x,y),('✓ ' if word in data['found'] else '  ')+word,font=font(18),fill=palette['accent'] if word in data['found'] else palette['text']);y+=29
    if data['kind']=='crossword':
        for clue in data['clues_text']:y=wrapped(draw,(x,y),clue,220,17,palette['text'],max_lines=3)+12
    y=max(340,min(y+20,560));draw.text((x,y),'HOW TO PLAY',font=font(15),fill=palette['accent']);wrapped(draw,(x,y+30),data.get('help',''),220,16,palette['muted'],max_lines=max(2,(680-y)//23))


def embed(data,players=None):
    palette=THEMES.get(data.get('theme'),THEMES['velvet']);result=discord.Embed(title='Vivi Arcade · '+data['title'],color=int(palette['accent'][1:],16))
    result.description=data.get('status','') if data.get('done') or 'Waiting' in data.get('status','') else 'Your game is ready.'
    if players:result.add_field(name='Players',value=' · '.join(f'{n+1}: <@{u}>' for n,u in enumerate(players)),inline=False)
    if not data.get('done') and data['kind']!='anagram':result.add_field(name='Turn',value=f'Player {data.get("turn",0)+1}',inline=True)
    if data['kind']=='anagram' and data.get('deadline') and not data.get('done'):result.add_field(name='Round ends',value=f'<t:{data["deadline"]}:R>',inline=True)
    if data['kind']=='pipe_connector' and data.get('deadline') and not data.get('done'):result.add_field(name='Water arrives',value=f'<t:{data["deadline"]}:R>',inline=True)
    if data.get('private'):result.add_field(name='Private board',value='Only you can see this response.',inline=False)
    result.add_field(name='Controls',value=data.get('help','')[:900] or 'Use the buttons below.',inline=False)
    if data['kind']=='trivia':
        result.description=data['question']
        result.add_field(name='Answers',value='\n'.join(f'{chr(65+n)}. {answer}' for n,answer in enumerate(data['choices'])),inline=False)
        if data.get('done') and data.get('correct') is not None:result.add_field(name='Correct answer',value=data['choices'][data['correct']],inline=False)
    result.set_image(url='attachment://vivi-game.png');result.set_footer(text='Use /games board format:text for a text board. · '+data.get('theme','velvet').title())
    if data['kind']=='trivia':result.set_footer(text='Choose an answer button below. · '+data.get('theme','velvet').title())
    return result

async def payload(data,players=None):
    body=await asyncio.to_thread(render,data)
    description=f'{data["title"]}. '+(data.get('status') if data.get('done') else f'Player {data.get("turn",0)+1} to move.')+' Text board: /games board format:text.'
    if data['kind']=='trivia':description='Trivia: '+data['question']+'. Answers: '+'; '.join(f'{chr(65+n)}: {answer}' for n,answer in enumerate(data['choices']))+'. Use the answer buttons.'
    return dict(embed=embed(data,players),file=discord.File(io.BytesIO(body),filename='vivi-game.png',description=description[:1000]))
