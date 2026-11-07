"""Render synthetic examples of new Vivi games without Discord or personal data."""
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vivi.games.card_games import Blackjack,GoFish
from vivi.games.network_puzzles import NETWORK_TYPES
from vivi.games.game_design import presentation,render

def main():
    output=Path(__file__).resolve().parents[1]/'docs/assets'
    output.mkdir(parents=True,exist_ok=True)
    factories={**{'blackjack':lambda:Blackjack(rng=random.Random(42)),'go_fish':lambda:GoFish(rng=random.Random(42))},**{kind:lambda factory=factory:factory('medium','large','vivi-preview') for kind,factory in NETWORK_TYPES.items()}}
    for kind,factory in factories.items():
        engine=factory()
        game=dict(kind=kind,engine=engine,players=[1,2] if kind in {'blackjack','go_fish'} else [1],vs_vivi=kind in {'blackjack','go_fish'},accepted=True,theme='velvet')
        body=render(presentation(game,1 if kind in {'blackjack','go_fish'} else None))
        path=output/f'arcade-{kind}.png';path.write_bytes(body);print(path)
if __name__=='__main__':main()
