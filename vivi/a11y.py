"""Static HTML checks to assist, rather than certify, manual screen-reader testing."""
from html.parser import HTMLParser
class Audit(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.ids=set(); self.labels=set(); self.controls=[]; self.issues=[]; self.heading=0; self.main=False; self.live=False; self.label_depth=0; self.navigation=False; self.interactive=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs); ident=a.get('id')
        if tag=='label': self.label_depth+=1
        if tag=='nav' or a.get('role')=='navigation': self.navigation=True
        if tag=='button' or tag=='a' and a.get('href'): self.interactive.append(dict(tag=tag,text='',attrs=a))
        if a.get('tabindex'):
            try:
                if int(a['tabindex'])>0: self.issues.append('Positive tabindex changes keyboard navigation order.')
            except ValueError: self.issues.append('Invalid tabindex value.')
        if ident:
            if ident in self.ids: self.issues.append('Duplicate ID: '+ident)
            self.ids.add(ident)
        if tag=='label' and a.get('for'): self.labels.add(a['for'])
        if tag in {'input','select','textarea'} and a.get('type') not in {'hidden','submit','button'}: self.controls.append((tag,a,self.label_depth>0))
        if tag=='img' and 'alt' not in a: self.issues.append('Image has no alt attribute.')
        if tag=='main' or a.get('role')=='main': self.main=True
        if a.get('aria-live') or a.get('role') in {'status','alert'}: self.live=True
        if tag in {'h1','h2','h3','h4','h5','h6'}:
            level=int(tag[1])
            if level>self.heading+1: self.issues.append(f'Heading jumps from h{self.heading} to {tag}.')
            self.heading=level
    def handle_data(self,text):
        for item in self.interactive: item['text']+=text
    def handle_endtag(self,tag):
        if self.interactive and self.interactive[-1]['tag']==tag:
            item=self.interactive.pop(); a=item['attrs']
            if not (item['text'].strip() or a.get('aria-label') or a.get('aria-labelledby')): self.issues.append('Unnamed navigation/control element: '+tag)
        if tag=='label': self.label_depth=max(0,self.label_depth-1)
    def findings(self):
        for tag,a,implicit in self.controls:
            if not (implicit or a.get('aria-label') or a.get('aria-labelledby') and all(x in self.ids for x in a['aria-labelledby'].split()) or a.get('id') in self.labels): self.issues.append('Missing accessible label: '+a.get('name',tag))
        if not self.main: self.issues.append('Missing main landmark.')
        if not self.navigation: self.issues.append('Missing navigation landmark.')
        if not self.live: self.issues.append('No live status region found.')
        return self.issues

def audit_html(source):
    parser=Audit(); parser.feed(source); return parser.findings()
