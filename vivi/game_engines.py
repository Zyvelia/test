"""Local game rules. Engines never send messages or expose opponents' hidden state."""
import random
import re
import chess

class ConnectFour:
    help='Drop a piece with a column number, 1–7.'
    def __init__(self): self.cells=[[0]*7 for _ in range(6)]; self.turn=0; self.done=False; self.result=''
    def move(self,text):
        if not re.fullmatch('[1-7]',text): raise ValueError(self.help)
        col=int(text)-1
        rows=[r for r in range(6) if self.cells[r][col]==0]
        if not rows: raise ValueError('Column is full.')
        r=max(rows); value=self.turn+1; self.cells[r][col]=value
        for dr,dc in [(1,0),(0,1),(1,1),(1,-1)]:
            count=1
            for sign in [-1,1]:
                y,x=r+dr*sign,col+dc*sign
                while 0<=y<6 and 0<=x<7 and self.cells[y][x]==value:
                    count+=1; y+=dr*sign; x+=dc*sign
            if count>=4: self.done=True; self.result=f'Player {value} wins!'
        if not self.done and all(all(row) for row in self.cells): self.done=True; self.result='Draw.'
        if not self.done: self.turn=1-self.turn
    def board(self,player=0): return '\n'.join(''.join('⚪🔴🟡'[v] for v in row) for row in self.cells)+'\n1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣'

class Chess:
    help='Use SAN (Nf3, O-O) or UCI (e2e4, e7e8q). Use draw to claim a valid draw.'
    def __init__(self): self.position=chess.Board(); self.turn=0; self.done=False; self.result=''
    def move(self,text):
        if text.lower()=='draw':
            if not self.position.can_claim_draw(): raise ValueError('A draw cannot be claimed in this position.')
            self.done=True; self.result='Draw claimed.'; return
        try: move=self.position.parse_san(text)
        except ValueError:
            try: move=chess.Move.from_uci(text)
            except ValueError: raise ValueError(self.help) from None
        if move not in self.position.legal_moves: raise ValueError('Illegal move. '+self.help)
        self.position.push(move); self.turn=0 if self.position.turn else 1
        outcome=self.position.outcome()
        if outcome: self.done=True; self.result='Draw.' if outcome.winner is None else f'Player {1 if outcome.winner else 2} wins!'
    def board(self,player=0): return '```\n'+self.position.unicode(borders=True)+'\n```'

def square(text,size=8):
    if not re.fullmatch(f'[a-{chr(96+size)}][1-{size}]',text.lower()): raise ValueError('Use board coordinates such as A1.')
    return size-int(text[1]),ord(text[0].lower())-97

class Checkers:
    help='American checkers: b6-a5, captures b6-d4-f2. Mandatory captures; men capture forward; promotion ends turn.'
    def __init__(self):
        self.cells={(r,c):(0 if r<3 else 1,False) for r in list(range(3))+list(range(5,8)) for c in range(8) if (r+c)%2}
        self.turn=0; self.done=False; self.result=''
    def steps(self,board,pos,capture=False):
        side,king=board[pos]; r,c=pos; answer=[]
        for dr in ([-1,1] if king else [1 if side==0 else -1]):
            for dc in [-1,1]:
                mid=(r+dr,c+dc); end=(r+dr*(2 if capture else 1),c+dc*(2 if capture else 1))
                if not (0<=end[0]<8 and 0<=end[1]<8) or end in board: continue
                if not capture or (mid in board and board[mid][0]!=side): answer.append(end)
        return answer
    def options(self,capture): return [(p,q) for p,v in self.cells.items() if v[0]==self.turn for q in self.steps(self.cells,p,capture)]
    def move(self,text):
        try: path=[square(x) for x in text.lower().replace('x','-').split('-')]
        except ValueError: raise ValueError(self.help) from None
        if len(path)<2 or path[0] not in self.cells or self.cells[path[0]][0]!=self.turn: raise ValueError(self.help)
        board=dict(self.cells); capture=bool(self.options(True)); pos=path[0]; promoted=False
        for n,end in enumerate(path[1:]):
            if end not in self.steps(board,pos,capture) or promoted: raise ValueError('Illegal move. '+self.help)
            side,king=board.pop(pos)
            if capture: board.pop(((pos[0]+end[0])//2,(pos[1]+end[1])//2))
            elif len(path)!=2: raise ValueError('Only jumps may be chained.')
            promoted=not king and end[0]==(7 if side==0 else 0)
            board[end]=(side,king or promoted); pos=end
        if capture and not promoted and self.steps(board,pos,True): raise ValueError('Complete the multi-jump in one move.')
        self.cells=board; self.turn=1-self.turn
        if not self.options(True) and not self.options(False): self.done=True; self.result=f'Player {2-self.turn} wins!'
    def board(self,player=0):
        return '```\n'+'\n'.join(str(8-r)+' '+''.join(('rR' if v[0]==0 else 'bB')[v[1]] if (v:=self.cells.get((r,c))) else '.' for c in range(8)) for r in range(8))+'\n  abcdefgh\n```'

WORD_BANK=['planet','silver','garden','rocket','puzzle','forest','castle','window','dragon','orange','velvet','ruins','violet','flower','kitten','galaxy','winter','summer','ocean','sunset']
class Hangman:
    help='Guess one letter or the whole word. Six mistakes allowed.'
    def __init__(self): self.word=random.choice(WORD_BANK); self.guesses=set(); self.errors=0; self.turn=0; self.done=False; self.result=''
    def move(self,text):
        text=text.lower().strip()
        if not text.isascii() or not text.isalpha() or len(text)>30: raise ValueError(self.help)
        if text in self.guesses: raise ValueError('Already guessed.')
        self.guesses.add(text)
        if text!=self.word and (len(text)>1 or text not in self.word): self.errors+=1
        won=text==self.word or set(self.word)<=self.guesses
        self.done=won or self.errors>=6
        if self.done: self.result=('Solved! ' if won else 'Out of guesses. ')+self.word
    def board(self,player=0): return ' '.join(c if c in self.guesses or self.done else '＿' for c in self.word)+f'\nMistakes: {self.errors}/6 · Guessed: '+', '.join(sorted(self.guesses))

class Memory:
    help='Reveal a card: A1–D4. Reveal two; mismatches hide after two seconds.'
    def __init__(self):
        self.cards=list('🍎🍊🍋🍇🍓🍒🥝🍉')*2; random.shuffle(self.cards); self.matched=set(); self.shown=[]; self.turn=0; self.done=False; self.result=''; self.tries=0
    def move(self,text):
        r,c=square(text,4); index=r*4+c
        if len(self.shown)==2: raise ValueError('Wait for the cards to hide.')
        if index in self.matched or index in self.shown: raise ValueError('Choose a hidden card.')
        self.shown.append(index)
        if len(self.shown)==2:
            self.tries+=1
            if self.cards[self.shown[0]]==self.cards[self.shown[1]]: self.matched.update(self.shown); self.shown=[]
        if len(self.matched)==16: self.done=True; self.result=f'All pairs found in {self.tries} tries!'
    def board(self,player=0): return '\n'.join(str(4-r)+' '+''.join(self.cards[r*4+c] if r*4+c in self.matched or r*4+c in self.shown else '❔' for c in range(4)) for r in range(4))+'\n　A B C D'

def solutions(board,limit=2):
    """Count solutions with MRV; stops as soon as uniqueness is disproved."""
    best=None; choices=None
    for n,value in enumerate(board):
        if value: continue
        r,c=divmod(n,9); seen={board[r*9+x] for x in range(9)}|{board[x*9+c] for x in range(9)}|{board[y*9+x] for y in range(r//3*3,r//3*3+3) for x in range(c//3*3,c//3*3+3)}
        possible=set(range(1,10))-seen
        if not possible: return 0
        if choices is None or len(possible)<len(choices): best,choices=n,possible
    if best is None: return 1
    count=0
    for value in choices:
        board[best]=value; count+=solutions(board,limit-count)
        if count>=limit: break
    board[best]=0; return count

class Sudoku:
    help='Enter A1=5 (columns A–I, rows 1–9); use A1=0 to clear your entry.'
    def __init__(self,difficulty='easy'):
        if difficulty not in {'easy','medium','hard'}: raise ValueError('Choose easy, medium or hard.')
        def groups(): return [g*3+x for g in random.sample(range(3),3) for x in random.sample(range(3),3)]
        rows,cols=groups(),groups(); nums=random.sample(range(1,10),9)
        self.solution=[nums[(r*3+r//3+c)%9] for r in rows for c in cols]; self.cells=self.solution[:]
        target={'easy':45,'medium':36,'hard':30}[difficulty]
        for n in random.sample(range(81),81):
            if sum(bool(x) for x in self.cells)<=target: break
            value=self.cells[n]; self.cells[n]=0
            if solutions(self.cells[:])!=1: self.cells[n]=value
        self.clues={n for n,v in enumerate(self.cells) if v}; self.turn=0; self.done=False; self.result=''; self.difficulty=difficulty
    def move(self,text):
        match=re.fullmatch(r'([a-i])([1-9])\s*=\s*([0-9])',text.lower())
        if not match: raise ValueError(self.help)
        col,row,value=match.groups(); n=(9-int(row))*9+ord(col)-97; value=int(value)
        if n in self.clues: raise ValueError('Original clues cannot be changed.')
        board=self.cells[:]; board[n]=0; r,c=divmod(n,9)
        peers={board[r*9+x] for x in range(9)}|{board[x*9+c] for x in range(9)}|{board[y*9+x] for y in range(r//3*3,r//3*3+3) for x in range(c//3*3,c//3*3+3)}
        if value and value in peers: raise ValueError('That conflicts with the row, column or box.')
        self.cells[n]=value
        if all(self.cells): self.done=True; self.result='Sudoku solved!'
    def board(self,player=0): return '```\n'+'\n'.join(str(9-r)+' '+''.join(str(x) if x else '.' for x in self.cells[r*9:r*9+9]) for r in range(9))+'\n  ABCDEFGHI\n```'+f'\n{sum(bool(x) for x in self.cells)}/81 filled · {self.difficulty}'

class Battleship:
    help='Quick Battleship: 6×6, automatic fleets of 3, 2, 2. Fire at A1–F6; /games board shows your private fleet.'
    def __init__(self):
        self.fleets=[]
        for _ in range(2):
            occupied=set()
            for size in [3,2,2]:
                while True:
                    r,c=random.randrange(6),random.randrange(6); dr,dc=random.choice([(1,0),(0,1)])
                    ship={(r+dr*n,c+dc*n) for n in range(size)}
                    if all(y<6 and x<6 for y,x in ship) and not ship&occupied: occupied|=ship; break
            self.fleets.append(occupied)
        self.shots=[set(),set()]; self.turn=0; self.done=False; self.result=''; self.last='No shots yet.'
    def move(self,text):
        pos=square(text,6)
        if pos in self.shots[self.turn]: raise ValueError('You already fired there.')
        self.shots[self.turn].add(pos); hit=pos in self.fleets[1-self.turn]
        self.last=f'Player {self.turn+1}: {text.upper()} — '+('hit!' if hit else 'miss.')
        if self.fleets[1-self.turn]<=self.shots[self.turn]: self.done=True; self.result=f'Player {self.turn+1} wins!'
        else: self.turn=1-self.turn
    def board(self,player=0):
        shots=self.shots[1-player]
        own='\n'.join(str(6-r)+' '+''.join('X' if (r,c) in shots and (r,c) in self.fleets[player] else 'o' if (r,c) in shots else 'S' if (r,c) in self.fleets[player] else '.' for c in range(6)) for r in range(6))
        target='\n'.join(str(6-r)+' '+''.join('X' if (r,c) in self.shots[player] and (r,c) in self.fleets[1-player] else 'o' if (r,c) in self.shots[player] else '.' for c in range(6)) for r in range(6))
        return 'Your fleet:\n```\n'+own+'\n  ABCDEF\n```Your shots:\n```\n'+target+'\n  ABCDEF\n```'+self.last
