"""Render reproducible, synthetic Vivi arcade previews without Discord access."""
import argparse
import io
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from vivi.games.game_design import presentation,render,font
from vivi.games.game_engines import Chess,ConnectFour,Memory,Battleship
from vivi.games.more_games import Minesweeper,WordSearch


def generate(output):
    random.seed(2026);cards=[]
    for kind,factory,theme in [('chess',Chess,'velvet'),('connect_four',ConnectFour,'velvet'),('memory',Memory,'velvet'),('battleship',Battleship,'moonlight'),('minesweeper',Minesweeper,'velvet'),('word_search',WordSearch,'garden')]:
        engine=factory();game=dict(kind=kind,engine=engine,players=[1001] if kind in {'memory','minesweeper','word_search'} else [1001,1002],accepted=True,theme=theme)
        if kind=='chess':
            for move in ['e4','e5','Nf3']:engine.move(move)
        if kind=='connect_four':
            for move in ['4','3','4','5','3']:engine.move(move)
        if kind=='memory':engine.move('A4');engine.move('B4')
        if kind=='minesweeper':engine.move('C3')
        if kind=='battleship':engine.move('C3');engine.move('B2')
        data=presentation(game,1001 if kind=='battleship' else None)
        cards.append(Image.open(io.BytesIO(render(data))).resize((480,380),Image.Resampling.LANCZOS))
    image=Image.new('RGB',(960,1204),'#171322');draw=ImageDraw.Draw(image)
    draw.text((24,17),'Vivi Arcade | sample boards',font=font(24),fill='#f7f0fa')
    draw.text((24,46),'Synthetic demo games. No live member data.',font=font(12),fill='#b9accb')
    for n,card in enumerate(cards):image.paste(card,((n%2)*480,64+(n//2)*380))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);image.save(output,optimize=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'docs/assets/arcade-preview.png'))
    generate(parser.parse_args().output)
