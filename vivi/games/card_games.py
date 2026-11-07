"""Two-player practice cards; engines keep decks and hidden hands out of public views."""
import random

RANKS=['A']+[str(n) for n in range(2,11)]+['J','Q','K']
def deck(rng):
    cards=[rank+suit for rank in RANKS for suit in 'HDSC'];rng.shuffle(cards);return cards

def total(hand):
    value=sum(11 if c[:-1]=='A' else 10 if c[:-1] in 'JQK' else int(c[:-1]) for c in hand)
    aces=sum(c[:-1]=='A' for c in hand)
    while value>21 and aces:value-=10;aces-=1
    return value

class Blackjack:
    help='Hit or stand. Closest to 21 without busting wins. Vivi stands on all 17s. No splits, doubles or bets; wins earn 10 fictional practice chips. Open Private board for your hand.'
    def __init__(self,vs_vivi=True,rng=None):
        self.deck=deck(rng or random.SystemRandom());self.hands=[[self.deck.pop(),self.deck.pop()] for _ in range(2)]
        self.vs_vivi=vs_vivi;self.stood=[False,False];self.turn=0;self.done=False;self.result='';self.winners=[]
    def finish(self):
        scores=[total(hand) for hand in self.hands];valid=[n for n,value in enumerate(scores) if value<=21]
        self.winners=[n for n in valid if scores[n]==max(scores[x] for x in valid)] if valid else []
        if len(self.winners)==2:self.winners=[];self.result='Push: both hands tie. No chips awarded.'
        elif self.winners:self.result=f'Player {self.winners[0]+1} wins! +10 fictional practice chips.'
        else:self.result='Both players bust. No chips awarded.'
        self.done=True
    def move(self,text):
        if self.done:raise ValueError('This hand has ended.')
        action=text.lower().strip()
        if action not in {'hit','stand'}:raise ValueError('Use hit or stand.')
        player=self.turn
        if action=='hit':
            if total(self.hands[player])>=21:raise ValueError('You have 21 or more. Stand to finish your turn.')
            self.hands[player].append(self.deck.pop())
        if self.vs_vivi and player==0 and total(self.hands[0])>21:
            self.stood=[True,True];self.finish();return
        if action=='stand' or total(self.hands[player])>=21:
            self.stood[player]=True;self.turn=1-player
            if all(self.stood):self.finish()
    def bot_move(self):
        self.move('hit' if total(self.hands[1])<17 else 'stand')
    def visible(self,viewer=None):
        return [list(hand) if self.done or viewer==n else [hand[0],'??'] if self.vs_vivi and n==1 else ['??']*len(hand) for n,hand in enumerate(self.hands)]
    def board(self,player=None):
        rows=[]
        for n,hand in enumerate(self.visible(player)):
            score=f' ({total(self.hands[n])})' if '??' not in hand else ''
            rows.append(f'Player {n+1}: '+', '.join(hand)+score)
        return '\n'.join(rows)+('\n'+self.result if self.done else '')

class GoFish:
    help='Ask for a rank you hold: A, 2–10, J, Q or K. Collect four of a rank to make a book. A successful ask or matching draw keeps your turn. Open Private board to see your cards.'
    def __init__(self,vs_vivi=True,rng=None):
        self.deck=deck(rng or random.SystemRandom());self.hands=[[self.deck.pop() for _ in range(7)] for _ in range(2)]
        self.books=[[],[]];self.vs_vivi=vs_vivi;self.turn=0;self.done=False;self.result='';self.last='';self.winners=[]
        for player in range(2):self.collect(player)
    def collect(self,player):
        for rank in RANKS:
            if sum(c[:-1]==rank for c in self.hands[player])==4:
                self.books[player].append(rank);self.hands[player]=[c for c in self.hands[player] if c[:-1]!=rank]
    def refill(self,player):
        while not self.hands[player] and self.deck:
            self.hands[player]=[self.deck.pop() for _ in range(min(7,len(self.deck)))];self.collect(player)
    def finish(self):
        a,b=map(len,self.books);self.done=True;self.winners=[] if a==b else [0 if a>b else 1]
        self.result=f'Draw: {a}–{b} books.' if a==b else f'Player {self.winners[0]+1} wins {max(a,b)}–{min(a,b)} books! +10 fictional practice chips.'
    def move(self,text):
        if self.done:raise ValueError('This match has ended.')
        rank=text.upper().strip().removeprefix('ASK ').replace('ACE','A').replace('JACK','J').replace('QUEEN','Q').replace('KING','K')
        player=self.turn;other=1-player
        if rank not in RANKS or not any(c[:-1]==rank for c in self.hands[player]):raise ValueError('Ask for a rank currently in your hand: A, 2–10, J, Q or K.')
        found=[c for c in self.hands[other] if c[:-1]==rank]
        if found:
            self.hands[other]=[c for c in self.hands[other] if c[:-1]!=rank];self.hands[player]+=found
            self.last=f'Player {player+1} asked for {rank}: received {len(found)} card(s).'
        else:
            drawn=self.deck.pop() if self.deck else None
            if drawn:self.hands[player].append(drawn)
            matching=bool(drawn and drawn[:-1]==rank)
            self.last=f'Player {player+1} asked for {rank}: go fish.'+(' Matching draw: another turn.' if matching else '')
            if not matching:self.turn=other
        self.collect(player)
        for n in range(2):self.refill(n)
        if sum(map(len,self.books))==13 or not self.deck and not any(self.hands):self.finish()
        elif not self.hands[self.turn]:self.turn=1-self.turn
    def bot_move(self):
        hand=self.hands[1];ranks=[c[:-1] for c in hand]
        self.move(max(set(ranks),key=lambda rank:(ranks.count(rank),RANKS.index(rank))))
    def board(self,player=None):
        text='\n'.join(f'Player {n+1}: {len(self.hands[n])} cards · {len(self.books[n])} books ({", ".join(self.books[n]) or "none"})' for n in range(2))
        if player is not None:text+='\nYour cards: '+', '.join(sorted(self.hands[player],key=lambda c:RANKS.index(c[:-1])))
        return text+f'\nDeck: {len(self.deck)} cards. '+(self.result if self.done else self.last)
