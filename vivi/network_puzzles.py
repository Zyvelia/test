"""Procedural, solvable rotation puzzles. Saved state includes seed and solution privately."""
import random
import secrets
import time
from .more_games import SavedPuzzle,coord

DIRS=[(-1,0),(0,1),(1,0),(0,-1)]
SIZES={'small':6,'medium':10,'large':14}
DIFFICULTIES=['easy','medium','hard']
def rotate(mask,steps=1):
    for _ in range(steps%4):mask=((mask<<1)&15)|((mask>>3)&1)
    return mask

def route(size,rng):
    # Random monotone path: never self-intersects and always reaches the receiver.
    steps=[1]*(size-1)+[2]*(size-1);rng.shuffle(steps);path=[(0,0)]
    for direction in steps:
        r,c=path[-1];dr,dc=DIRS[direction];path.append((r+dr,c+dc))
    return path

class NetworkPuzzle(SavedPuzzle):
    mode='pipe_connector'
    def __init__(self,difficulty='easy',size='small',seed=None):
        if difficulty not in DIFFICULTIES or size not in SIZES:raise ValueError('Choose easy/medium/hard and small/medium/large.')
        self.difficulty=difficulty;self.size=SIZES[size];self.seed=seed or secrets.token_hex(16);rng=random.Random(self.seed)
        self.turn=0;self.done=False;self.result='';self.moves=0;self.last=''
        n=self.size;self.solution=[[0]*n for _ in range(n)]
        if self.mode=='circuit_repair':
            visited={(0,0)};stack=[(0,0)]
            while stack:
                r,c=stack[-1];options=[(d,r+dr,c+dc) for d,(dr,dc) in enumerate(DIRS) if 0<=r+dr<n and 0<=c+dc<n and (r+dr,c+dc) not in visited]
                if not options:stack.pop();continue
                d,y,x=rng.choice(options);self.solution[r][c]|=1<<d;self.solution[y][x]|=1<<((d+2)%4);visited.add((y,x));stack.append((y,x))
        else:
            path=route(n,rng)
            if self.mode=='pipe_connector':
                self.solution[0][0]|=8;self.solution[n-1][n-1]|=2
                for (r,c),(y,x) in zip(path,path[1:]):
                    d=DIRS.index((y-r,x-c));self.solution[r][c]|=1<<d;self.solution[y][x]|=1<<((d+2)%4)
                for r in range(n):
                    for c in range(n):
                        if not self.solution[r][c]:self.solution[r][c]=rng.choice([3,6,12,9,5,10])
            else:
                # Laser tiles: 0 empty, 1 / mirror, 2 backslash mirror, 3 fixed wall.
                self.solution=[[rng.choices([0,1,2,3],weights=[4,2,2,{'easy':1,'medium':3,'hard':5}[difficulty]])[0] for _ in range(n)] for _ in range(n)]
                incoming=1
                for index,(r,c) in enumerate(path):
                    outgoing=DIRS.index((path[index+1][0]-r,path[index+1][1]-c)) if index+1<len(path) else 1
                    self.solution[r][c]=0 if incoming==outgoing else 1 if (incoming,outgoing) in {(0,1),(1,0),(2,3),(3,2)} else 2
                    incoming=outgoing
        self.cells=[list(row) for row in self.solution]
        for r in range(n):
            for c in range(n):
                if self.mode=='laser_locks':
                    if self.cells[r][c] in {1,2} and rng.random()<{'easy':.3,'medium':.55,'hard':.8}[difficulty]:self.cells[r][c]=3-self.cells[r][c]
                elif rng.random()<{'easy':.35,'medium':.65,'hard':.95}[difficulty]:self.cells[r][c]=rotate(self.cells[r][c],rng.randint(1,3))
        # Ensure a newly generated board is a challenge, including unusually lucky scrambles.
        for _ in range(100):
            if not self.solved():break
            r,c=rng.randrange(n),rng.randrange(n)
            if self.mode=='laser_locks':
                if self.cells[r][c] in {1,2}:self.cells[r][c]=3-self.cells[r][c]
            else:self.cells[r][c]=rotate(self.cells[r][c])
        if self.solved():
            self.cells=[list(row) for row in self.solution]
            if self.mode=='laser_locks':
                r,c=next((r,c) for r,c in path if self.solution[r][c] in {1,2})
                self.cells[r][c]=3-self.cells[r][c]  # First bend sends the beam off the top edge.
            else:self.cells[0][0]=rotate(self.cells[0][0])
        self.deadline=time.time()+{'easy':600,'medium':420,'hard':300}[difficulty]*(n/6)**2 if self.mode=='pipe_connector' else None
        self.help=('Rotate a tile with A1, or A1 2 / A1 3 for half/three-quarter turns. '
                   +('Connect the west inlet at the top-left to the east outlet at the bottom-right before the timer runs out. The timer continues while away.' if self.mode=='pipe_connector' else 'Power every tile from the top-left source; all wire ends must connect.' if self.mode=='circuit_repair' else 'Guide the eastbound beam from the top-left through mirrors to the east receiver at the bottom-right. Walls are fixed.'))
    def trace(self):
        n=self.size;seen=set();pending=[(0,0)];leaks=[]
        while pending:
            r,c=pending.pop()
            if (r,c) in seen:continue
            seen.add((r,c));mask=self.cells[r][c]
            for d,(dr,dc) in enumerate(DIRS):
                if not mask&(1<<d):continue
                y,x=r+dr,c+dc
                if 0<=y<n and 0<=x<n:
                    if self.cells[y][x]&(1<<((d+2)%4)):pending.append((y,x))
                    else:leaks.append((r,c))
                elif not (self.mode=='pipe_connector' and ((r,c,d)==(0,0,3) or (r,c,d)==(n-1,n-1,1))):leaks.append((r,c))
        return seen,leaks
    def beam(self):
        n=self.size;r=c=0;direction=1;seen=set();path=[]
        while 0<=r<n and 0<=c<n and (r,c,direction) not in seen:
            seen.add((r,c,direction));path.append((r,c));tile=self.cells[r][c]
            if tile==3:return path,False
            if tile==1:direction={0:1,1:0,2:3,3:2}[direction]
            elif tile==2:direction={0:3,3:0,2:1,1:2}[direction]
            if (r,c,direction)==(n-1,n-1,1):return path,True
            dr,dc=DIRS[direction];r+=dr;c+=dc
        return path,False
    def solved(self):
        if self.mode=='laser_locks':return self.beam()[1]
        seen,leaks=self.trace()
        if self.mode=='circuit_repair':return len(seen)==self.size**2 and not leaks
        return bool(self.cells[0][0]&8 and self.cells[-1][-1]&2 and (self.size-1,self.size-1) in seen and not leaks)
    def expire(self,now=None):
        if not self.done and self.deadline and (time.time() if now is None else now)>=self.deadline:
            self.done=True;self.result='Water arrived before the pipeline was connected. Start a new board to retry.'
        return self.done
    def move(self,text):
        if self.expire():raise ValueError(self.result or 'This puzzle has ended.')
        parts=text.strip().split()
        if len(parts) not in {1,2}:raise ValueError('Use A1 or A1 2 / A1 3.')
        r,c=coord(parts[0],self.size)
        if len(parts)==2 and parts[1] not in {'1','2','3'}:raise ValueError('Rotate by 1, 2 or 3 quarter turns.')
        turns=int(parts[1]) if len(parts)==2 else 1
        if self.mode=='laser_locks':
            if self.cells[r][c] not in {1,2}:raise ValueError('Choose a mirror tile; empty tiles and walls cannot rotate.')
            if turns%2:self.cells[r][c]=3-self.cells[r][c]
        else:self.cells[r][c]=rotate(self.cells[r][c],turns)
        self.moves+=1
        if self.solved():self.done=True;self.result=f'Puzzle solved in {self.moves} moves!'
    def board(self,player=0):
        symbols={0:'·',1:'╵',2:'╶',3:'└',4:'╷',5:'│',6:'┌',7:'├',8:'╴',9:'┘',10:'─',11:'┴',12:'┐',13:'┤',14:'┬',15:'┼'}
        if self.mode=='laser_locks':symbols={0:'.',1:'/',2:'\\',3:'#'}
        n=self.size
        rows=[''.join(symbols[tile] for tile in row) for row in self.cells]
        return '```\n'+'\n'.join(f'{n-r:2} '+row for r,row in enumerate(rows))+'\n   '+''.join(chr(65+c) for c in range(n))+'\n```'+f'\n{n}×{n} · {self.difficulty} · {self.moves} moves'+(f' · {max(0,int(self.deadline-time.time()))} seconds left' if self.deadline and not self.done else '')+('\n'+self.result if self.done else '')

class PipeConnector(NetworkPuzzle):mode='pipe_connector'
class CircuitRepair(NetworkPuzzle):mode='circuit_repair'
class LaserLocks(NetworkPuzzle):mode='laser_locks'
NETWORK_TYPES={'pipe_connector':PipeConnector,'circuit_repair':CircuitRepair,'laser_locks':LaserLocks}
