"""Additional local game rules and JSON-safe puzzle progress."""
import random
import re
from collections import deque

DIRECTIONS=[(r,c) for r in [-1,0,1] for c in [-1,0,1] if r or c]
def coord(text,size):
    m=re.fullmatch(r'([a-z])(\d{1,2})',text.strip().lower())
    if not m or not 0<=ord(m[1])-97<size or not 1<=int(m[2])<=size: raise ValueError(f'Use A1–{chr(64+size)}{size}.')
    return size-int(m[2]),ord(m[1])-97

def grid(rows):
    size=len(rows)
    return '```\n'+'\n'.join(f'{size-r:2} '+''.join(row) for r,row in enumerate(rows))+'\n   '+''.join(chr(65+c) for c in range(size))+'\n```'

class Reversi:
    help='Play A1–H8. A legal move must surround opposing pieces; unavailable turns pass automatically.'
    def __init__(self):
        self.cells=[[0]*8 for _ in range(8)]; self.cells[3][3]=self.cells[4][4]=2;self.cells[3][4]=self.cells[4][3]=1
        self.turn=0;self.done=False;self.result='';self.last=''
    def flips(self,r,c,player):
        if self.cells[r][c]:return []
        found=[];own=player+1
        for dr,dc in DIRECTIONS:
            y,x=r+dr,c+dc;line=[]
            while 0<=y<8 and 0<=x<8 and self.cells[y][x]==3-own:line.append((y,x));y+=dr;x+=dc
            if line and 0<=y<8 and 0<=x<8 and self.cells[y][x]==own:found+=line
        return found
    def legal(self,player):return [(r,c) for r in range(8) for c in range(8) if self.flips(r,c,player)]
    def move(self,text):
        r,c=coord(text,8);flipped=self.flips(r,c,self.turn)
        if not flipped:raise ValueError('That move does not surround an opposing piece.')
        for y,x in [(r,c)]+flipped:self.cells[y][x]=self.turn+1
        self.turn=1-self.turn;self.last=''
        if not self.legal(self.turn):
            self.turn=1-self.turn;self.last='Opponent has no legal move; their turn was passed.'
            if not self.legal(self.turn):
                self.done=True;a=sum(row.count(1) for row in self.cells);b=sum(row.count(2) for row in self.cells)
                self.result=f'Draw ({a}–{b}).' if a==b else f'Player {1 if a>b else 2} wins ({a}–{b})!'
    def board(self,player=0):
        legal=set(self.legal(self.turn)) if not self.done else set()
        return grid([[('+' if (r,c) in legal else '.') if not v else 'X' if v==1 else 'O' for c,v in enumerate(row)] for r,row in enumerate(self.cells)])+'\nX = player 1; O = player 2; + = legal move. '+self.last

class SavedPuzzle:
    def dump(self):return dict(self.__dict__)
    @classmethod
    def load(cls,data):
        result=cls.__new__(cls);result.__dict__.update(data);return result

class Minesweeper(SavedPuzzle):
    help='6×6 Minesweeper: reveal A1, or flag A1 / unflag A1. First reveal is safe.'
    def __init__(self,difficulty='easy'):
        if difficulty not in {'easy','medium','hard'}:raise ValueError('Choose easy, medium or hard.')
        self.count={'easy':6,'medium':8,'hard':12}[difficulty];self.mines=[];self.revealed=[];self.flags=[];self.turn=0;self.done=False;self.result=''
    def neighbors(self,n):
        r,c=divmod(n,6);return [(r+dr)*6+c+dc for dr,dc in DIRECTIONS if 0<=r+dr<6 and 0<=c+dc<6]
    def move(self,text):
        parts=text.lower().split();action=parts[0] if len(parts)==2 else 'reveal'
        if action not in {'flag','unflag','reveal'} or len(parts) not in {1,2}:raise ValueError(self.help)
        r,c=coord(parts[-1],6);n=r*6+c
        if action=='flag':
            if n in self.revealed:raise ValueError('A revealed cell cannot be flagged.')
            if n not in self.flags:
                if len(self.flags)>=self.count:raise ValueError('All available flags are placed.')
                self.flags.append(n)
            return
        if action=='unflag':
            if n in self.flags:self.flags.remove(n)
            return
        if n in self.flags or n in self.revealed:raise ValueError('Choose a hidden, unflagged cell.')
        if not self.mines:self.mines=random.sample([x for x in range(36) if x not in [n]+self.neighbors(n)],self.count)
        if n in self.mines:self.done=True;self.result='Mine hit. Start another game to try again.';return
        queue=deque([n]);seen=set(self.revealed)
        while queue:
            item=queue.popleft()
            if item in seen or item in self.flags or item in self.mines:continue
            seen.add(item)
            if not any(x in self.mines for x in self.neighbors(item)):queue.extend(self.neighbors(item))
        self.revealed=sorted(seen)
        if len(self.revealed)==36-self.count:self.done=True;self.result='All safe cells revealed!'
    def board(self,player=0):
        cells=[]
        for r in range(6):
            row=[]
            for c in range(6):
                n=r*6+c
                row.append('*' if self.done and n in self.mines else 'F' if n in self.flags else str(sum(x in self.mines for x in self.neighbors(n))) if n in self.revealed else '#')
            cells.append(row)
        return grid(cells)+f'\nMines: {self.count}; flags: {len(self.flags)}; safe cells: {len(self.revealed)}/{36-self.count}'

SEARCH_WORDS=['VELVET','RUINS','GARDEN','MOON','VIOLET','STAR','CLOUD','ROSE','DREAM','RIVER','FOREST','CASTLE']
class WordSearch(SavedPuzzle):
    help='Select a word’s endpoints, for example A1-E1. Words may run in any of eight directions.'
    def __init__(self):
        self.cells=[['']*10 for _ in range(10)];self.words={};self.found=[];self.turn=0;self.done=False;self.result=''
        for word in random.sample(SEARCH_WORDS,8):
            options=[]
            for r in range(10):
                for c in range(10):
                    for dr,dc in DIRECTIONS:
                        path=[(r+dr*n,c+dc*n) for n in range(len(word))]
                        if all(0<=y<10 and 0<=x<10 and self.cells[y][x] in {'',ch} for (y,x),ch in zip(path,word)):options.append(path)
            if not options:continue
            path=random.choice(options);self.words[word]=[list(p) for p in path]
            for (r,c),ch in zip(path,word):self.cells[r][c]=ch
        for row in self.cells:
            for c,v in enumerate(row):
                if not v:row[c]=random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    def move(self,text):
        parts=text.strip().split('-')
        if len(parts)!=2:raise ValueError(self.help)
        start,end=coord(parts[0],10),coord(parts[1],10)
        for word,path in self.words.items():
            if (list(start),list(end)) in [(path[0],path[-1]),(path[-1],path[0])]:
                if word in self.found:raise ValueError('You already found that word.')
                self.found.append(word)
                if len(self.found)==len(self.words):self.done=True;self.result='Every word found!'
                return
        raise ValueError('Those endpoints do not match a hidden target word.')
    def board(self,player=0):return grid(self.cells)+'\n'+', '.join(('✓ ' if w in self.found else '')+w for w in self.words)+f'\n{len(self.found)}/{len(self.words)} found.'

CROSSWORDS=[(['DOG','A#E','YET'],{'1A':('DOG','A common pet that barks'),'3A':('YET','Up to now; so far'),'1D':('DAY','A period of twenty-four hours'),'2D':('GET','Obtain or receive')}),(['CAT','A#O','RIP'],{'1A':('CAT','A common pet that meows'), '3A':('RIP','Tear apart'), '1D':('CAR','A vehicle with four wheels'),'2D':('TOP','The highest part')}),(['BAR','A#A','TIN'],{'1A':('BAR','A counter where drinks are served'),'3A':('TIN','A silvery metal used in cans'),'1D':('BAT','A flying mammal'),'2D':('RAN','Past tense of run')})]
class Crossword(SavedPuzzle):
    help='Mini crossword: answer a clue with 1A=CAT or 2D=TOP. Answers and progress are saved.'
    paths={'1A':[(0,0),(0,1),(0,2)],'3A':[(2,0),(2,1),(2,2)],'1D':[(0,0),(1,0),(2,0)],'2D':[(0,2),(1,2),(2,2)]}
    def __init__(self):
        self.pack=random.randrange(len(CROSSWORDS));self.answers={};self.turn=0;self.done=False;self.result=''
    def move(self,text):
        m=re.fullmatch(r'([1-3][ad])\s*=\s*([a-z]{3})',text.lower())
        if not m or m[1].upper() not in self.paths:raise ValueError(self.help)
        clue,answer=m[1].upper(),m[2].upper();expected=CROSSWORDS[self.pack][1][clue][0]
        if answer!=expected:raise ValueError('That answer does not match this clue.')
        if clue in self.answers:raise ValueError('That clue is already solved.')
        self.answers[clue]=answer
        if len(self.answers)==4:self.done=True;self.result='Crossword solved!'
    def board(self,player=0):
        rows=[['#' if c=='#' else '.' for c in row] for row in CROSSWORDS[self.pack][0]]
        for clue,answer in self.answers.items():
            for (r,c),ch in zip(self.paths[clue],answer):rows[r][c]=ch
        return grid(rows)+'\nTop-left starts 1A/1D; top-right starts 2D; bottom-left starts 3A.\n'+'\n'.join(f'{key}: {clue}'+(' ✓' if key in self.answers else '') for key,(answer,clue) in CROSSWORDS[self.pack][1].items())+f'\n{len(self.answers)}/4 clues solved.'

SPELLING=[('garden','A place where flowers and vegetables grow.'),('velvet','A fabric with a soft, dense pile.'),('violet','A purple flower, also a color.'),('necessary','Required; needed.'),('separate','Not joined together.'),('rhythm','A repeated pattern of beats.'),('accommodate','To provide room or adjust to someone’s needs.'),('conscientious','Careful and guided by a sense of duty.')]
class Spelling(SavedPuzzle):
    help='Spell the word described by the clue.'
    def __init__(self):self.index=0;self.errors=0;self.turn=0;self.done=False;self.result=''
    def move(self,text):
        if not re.fullmatch('[A-Za-z]{1,30}',text):raise ValueError('Enter one word using letters.')
        if text.casefold()!=SPELLING[self.index][0]:
            self.errors+=1
            if self.errors>=3:self.done=True;self.result='Challenge ended. The word was '+SPELLING[self.index][0]+'.'
            return
        self.index+=1;self.errors=0
        if self.index==len(SPELLING):self.done=True;self.result='Every spelling level completed!'
    def board(self,player=0):return self.result if self.done else f'Level {self.index+1}/{len(SPELLING)} · {self.errors}/3 mistakes\n{SPELLING[self.index][1]}\nWord length: {len(SPELLING[self.index][0])} letters.'

SAVED_TYPES={'minesweeper':Minesweeper,'word_search':WordSearch,'crossword':Crossword,'spelling':Spelling}
