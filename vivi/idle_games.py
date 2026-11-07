"""Persistent idle games with integer accounting and server-clock offline progress."""
import asyncio
import io
import time
import weakref
import discord
from discord import app_commands
from PIL import Image,ImageDraw
from .bot import reply
from .game_design import font,wrapped

CAP_MS=24*60*60*1000
GAMES={
 'farm':dict(title='Neon Rooftop Farm',resource='produce crates',building='Rooftop plots',automation='Delivery drones',variety='Crop research',capacity='Cold storage',rate=4,sale=2,worker=2,accent='#7ce3b9',items=['Glow lettuce','Neon berries','Moon melons','Prism peppers','Starfruit','Aurora orchids']),
 'market':dict(title='Night Market Empire',resource='customer orders',building='Market stalls',automation='Night staff',variety='Merchant guilds',capacity='Queue capacity',rate=3,sale=3,worker=1,accent='#ff84c6',items=['Lantern tea','Moon pastries','Spirit charms','Dream fabrics','Starlight jewelry','Enchanted antiques'])}
UPGRADES={'production':('building',50),'automation':('automation',75),'capacity':('capacity',40),'variety':('variety',120)}

def new_game(now):
    return dict(version=1,last_ms=int(now),cash=100000,stock=0,earned=0,prestige=0,levels=dict(production=1,automation=1,capacity=0,variety=0),production_remainder=0,sale_remainder=0)

def rates(kind,state):
    config=GAMES[kind];levels=state['levels'];bonus=100+25*state['prestige']
    return dict(production=(config['rate']+levels['variety'])*levels['production']*bonus,
                sales=config['worker']*levels['automation']*bonus,
                price=config['sale']+levels['variety'],capacity=400*(levels['capacity']+1))

def advance(kind,state,now):
    """Rates are in hundredths of units/minute. Balances are milli-units/credits."""
    now=int(now);elapsed=max(0,now-state['last_ms']);used=min(elapsed,CAP_MS)
    state['last_ms']=max(now,state['last_ms']);values=rates(kind,state)
    produced,state['production_remainder']=divmod(used*values['production']+state['production_remainder'],6000)
    budget,state['sale_remainder']=divmod(used*values['sales']+state['sale_remainder'],6000)
    supply=state['stock']+produced;sold=min(supply,budget);income=sold*values['price']
    # Inventory overflows are discarded. Automatic workers sell continuously at their rate.
    state['stock']=min(values['capacity']*1000,supply-sold);state['cash']+=income;state['earned']+=income
    return dict(elapsed_ms=elapsed,credited_ms=used,income=income,sold=sold,capped=elapsed>CAP_MS)

def cost(state,upgrade):
    if upgrade not in UPGRADES:raise ValueError('Unknown upgrade.')
    level=state['levels'][upgrade];return UPGRADES[upgrade][1]*135**level//100**level*1000

def prestige_goal(state):return 50000*(state['prestige']+1)*1000

def act(kind,state,action):
    if action=='collect':
        income=state['stock']*rates(kind,state)['price'];state['stock']=0;state['cash']+=income;state['earned']+=income
        return f'Sold waiting stock for {income/1000:,.2f} credits.'
    if action=='prestige':
        if state['earned']<prestige_goal(state):raise ValueError('Reach the displayed lifetime earnings milestone before expanding into a new district.')
        old=state['prestige'];earned=state['earned'];last=state['last_ms'];state.clear();state.update(new_game(last));state['prestige']=old+1;state['earned']=earned
        return 'New district opened! Buildings and wallet reset; permanent production and automation bonuses increased.'
    if action not in UPGRADES:raise ValueError('Unknown action.')
    maximum=len(GAMES[kind]['items'])-1 if action=='variety' else 100
    if state['levels'][action]>=maximum:raise ValueError('This upgrade is at its district limit. Expand into a new district to rebuild.')
    price=cost(state,action)
    if state['cash']<price:raise ValueError(f'You need {price/1000:,.2f} credits for this upgrade.')
    state['cash']-=price;state['levels'][action]+=1
    return 'Upgrade purchased. Your new rate applies from now onward.'

def display_amount(value):return f'{value/1000:,.2f}'

def render(kind,state):
    cfg=GAMES[kind];values=rates(kind,state);image=Image.new('RGB',(1000,640),'#120f20');draw=ImageDraw.Draw(image);accent=cfg['accent']
    draw.rounded_rectangle((18,18,982,622),radius=24,outline=accent,width=2)
    draw.text((42,34),'V I V I  /  IDLE WORLDS',font=font(16),fill=accent);draw.text((42,65),cfg['title'],font=font(35),fill='#faf1fa')
    # Original skyline and modular rooftop/stall illustration, independent of uploaded art.
    for n in range(10):
        x=45+n*54;height=65+(n*47)%135;y=345-height
        draw.rectangle((x,y,x+43,348),fill='#29213d')
        for row in range(3):draw.line((x+8,y+18+row*17,x+30,y+18+row*17),fill=accent,width=2)
    draw.rounded_rectangle((42,350,584,493),radius=14,fill='#29213d')
    count=min(8,state['levels']['production'])
    for n in range(count):
        x=55+(n%4)*130;y=361+(n//4)*64
        if kind=='farm':
            draw.rounded_rectangle((x,y+29,x+110,y+51),radius=5,fill='#493454')
            for plant in range(4):
                px=x+15+plant*24;draw.line((px,y+32,px,y+8),fill=accent,width=3);draw.ellipse((px-9,y+7,px+4,y+18),fill=accent)
        else:
            draw.rectangle((x,y+16,x+110,y+52),fill='#493454')
            draw.polygon([(x,y+18),(x+15,y),(x+95,y),(x+110,y+18)],fill=accent)
            draw.line((x+10,y+18,x+10,y+52),fill=accent,width=3)
    draw.text((45,515),cfg['items'][state['levels']['variety']],font=font(24),fill=accent)
    wrapped(draw,(45,558),f"District {state['prestige']+1} · +{25*state['prestige']}% permanent bonus",530,20,'#d1bbdb')
    draw.rounded_rectangle((610,135,955,590),radius=18,fill='#251e35')
    lines=[('WALLET',display_amount(state['cash'])+' credits'),('WAITING STOCK',display_amount(state['stock'])+' / '+str(values['capacity'])),('PRODUCTION',f"{values['production']/100:g} units/min"),('AUTOMATION',f"{values['sales']/100:g} units/min"),('UNIT VALUE',str(values['price'])+' credits'),('NEXT DISTRICT',display_amount(prestige_goal(state))+' earned')]
    for index,(label,value) in enumerate(lines):
        y=153+index*69;draw.text((632,y),label,font=font(12),fill=accent);wrapped(draw,(632,y+21),value,302,20,'#f9eff9',max_lines=1)
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()

class IdleService:
    def __init__(self,service):self.service=service;self.store=service.store;self.locks=weakref.WeakValueDictionary()
    def perform(self,guild,user,kind,action='view',now=None,expected_prestige=None,expected_level=None):
        if kind not in GAMES:raise ValueError('Choose farm or market.')
        now=int(time.time()*1000) if now is None else int(now)
        # No awaits between loading and saving: concurrent interactions cannot double spend.
        profile=self.store.profile(guild,user);state=profile.setdefault('idle_games',{}).setdefault(kind,new_game(now))
        report=advance(kind,state,now);notice=''
        try:
            if action in UPGRADES and expected_level is not None and state['levels'][action]!=expected_level:raise ValueError('That upgrade changed since this card was opened. Refresh to see its current price.')
            if action=='prestige' and expected_prestige is not None and state['prestige']!=expected_prestige:raise ValueError('Your district already changed. Open the game again before confirming another reset.')
            if action!='view':notice=act(kind,state,action)
        except ValueError:
            self.store.save_profile(guild,user,profile);raise
        self.store.save_profile(guild,user,profile)
        # Isolate render workers from later changes to the profile.
        import copy
        return copy.deepcopy(state),report,notice
    async def show(self,i,kind,action='view',edit=False,expected_prestige=None,expected_level=None):
        if not await self.service.need(i,'games'):return
        await i.response.defer(ephemeral=True)
        key=(i.guild_id,i.user.id,kind);lock=self.locks.get(key)
        if lock is None:lock=asyncio.Lock();self.locks[key]=lock
        async with lock:
            try:state,report,notice=self.perform(i.guild_id,i.user.id,kind,action,expected_prestige=expected_prestige,expected_level=expected_level)
            except ValueError as error:return await i.followup.send(str(error),ephemeral=True)
            body=await asyncio.to_thread(render,kind,state);values=rates(kind,state);cfg=GAMES[kind]
            card=discord.Embed(title=cfg['title'],description=(notice+'\n' if notice else '')+f"Automatic earnings since your last visit: **{display_amount(report['income'])} credits**."+(' Offline credit was capped at 24 hours.' if report['capped'] else ''),color=int(cfg['accent'][1:],16))
            card.add_field(name='Your game profile',value=f"Wallet: {display_amount(state['cash'])}\nStock: {display_amount(state['stock'])}/{values['capacity']}\nLifetime earned: {display_amount(state['earned'])}\nDistrict: {state['prestige']+1}",inline=False)
            for upgrade,(label,_) in UPGRADES.items():
                maximum=len(cfg['items'])-1 if upgrade=='variety' else 100
                card.add_field(name=cfg[label],value=f"Level {state['levels'][upgrade]} · "+('MAX' if state['levels'][upgrade]>=maximum else f"next: {display_amount(cost(state,upgrade))} credits"),inline=True)
            card.set_image(url='attachment://vivi-idle.png');card.set_footer(text='Private profile · 24h offline cap · finite storage · fictional credits · no purchases or cash value')
            file=discord.File(io.BytesIO(body),filename='vivi-idle.png',description=f"{cfg['title']} private game profile. Wallet {display_amount(state['cash'])}; stock {display_amount(state['stock'])}; district {state['prestige']+1}.")
            view=IdleView(self,i.guild_id,i.user.id,kind)
            if edit:await i.edit_original_response(embed=card,attachments=[file],view=view)
            else:await i.followup.send(embed=card,file=file,view=view,ephemeral=True)

class IdleView(discord.ui.View):
    def __init__(self,service,guild,owner,kind):
        super().__init__(timeout=900);self.service=service;self.guild=guild;self.owner=owner;self.kind=kind
        levels=service.store.profile(guild,owner).get('idle_games',{}).get(kind,{}).get('levels',{})
        for index,(label,action) in enumerate([('Refresh','view'),('Sell waiting stock','collect'),('Add plots' if kind=='farm' else 'Add stalls','production'),('Delivery drones' if kind=='farm' else 'Hire staff','automation'),('Expand storage','capacity'),('Research crops' if kind=='farm' else 'New merchants','variety'),('New district','confirm_prestige')]):
            button=discord.ui.Button(label=label,row=index//4,style=discord.ButtonStyle.primary if action=='collect' else discord.ButtonStyle.secondary)
            async def callback(i,value=action):
                if i.guild_id!=self.guild or i.user.id!=self.owner:return await reply(i,'This is another member’s private game profile.')
                if value=='confirm_prestige':
                    if not await service.service.need(i,'games'):return
                    return await i.response.send_message('Open a new district? This resets this game’s wallet, stock, buildings and research. Lifetime earnings stay; production and automation gain another permanent +25%.',view=PrestigeView(service,guild,owner,kind),ephemeral=True)
                await service.show(i,kind,value,edit=True,expected_level=levels.get(value))
            button.callback=callback;self.add_item(button)

class PrestigeView(discord.ui.View):
    def __init__(self,service,guild,owner,kind):
        super().__init__(timeout=60)
        expected=service.store.profile(guild,owner).get('idle_games',{}).get(kind,{}).get('prestige',0)
        button=discord.ui.Button(label='Confirm new district',style=discord.ButtonStyle.danger)
        async def confirm(i):
            if i.guild_id!=guild or i.user.id!=owner:return await reply(i,'This confirmation is not yours.')
            if getattr(self,'used',False):return await reply(i,'This confirmation has already been used.')
            self.used=True
            await service.show(i,kind,'prestige',edit=True,expected_prestige=expected)
        button.callback=confirm;self.add_item(button)

def register_idle(bot):
    service=IdleService(bot.community);group=app_commands.Group(name='idle',description='Persistent farm and night market with offline progress',guild_only=True)
    @group.command(name='farm',description='Open Neon Rooftop Farm: crops, drones, upgrades and offline earnings.')
    async def farm(i:discord.Interaction):await service.show(i,'farm')
    @group.command(name='market',description='Open Night Market Empire: stalls, staff, merchants and offline earnings.')
    async def market(i:discord.Interaction):await service.show(i,'market')
    bot.tree.add_command(group)
