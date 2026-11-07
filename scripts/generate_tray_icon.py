"""Generate Vivi's small-size neon monogram, PNG and multi-resolution Windows ICO."""
from pathlib import Path
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
def build_icon(size=256):
    scale=4;edge=size*scale;image=Image.new('RGBA',(edge,edge));draw=ImageDraw.Draw(image)
    def points(values):return [(int(x*edge),int(y*edge)) for x,y in values]
    draw.rounded_rectangle((edge*.03,edge*.03,edge*.97,edge*.97),radius=edge*.23,fill='#140c1c',outline='#ff65ad',width=max(2,int(edge*.035)))
    # Two open V strokes stay distinct even at Windows' 16px taskbar size.
    draw.line(points([(.20,.24),(.50,.80),(.80,.24)]),fill='#ff65ad',width=int(edge*.075),joint='curve')
    draw.line(points([(.37,.23),(.50,.49),(.63,.23)]),fill='#fce4f3',width=int(edge*.055),joint='curve')
    return image.resize((size,size),Image.Resampling.LANCZOS)

def main():
    folder=ROOT/'assets/vivi/tray';folder.mkdir(parents=True,exist_ok=True)
    icon=build_icon();icon.save(folder/'vivi.png');icon.save(folder/'vivi.ico',sizes=[(n,n) for n in (16,20,24,32,40,48,64,128,256)])
    build_icon(64).save(folder/'vivi-64.png')
if __name__=='__main__':main()
