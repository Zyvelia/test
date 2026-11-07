'use strict';
(() => {
  const status=document.getElementById('studio-status');
  const say=text=>{if(status)status.textContent=text;};
  const panels=document.getElementById('dashboard-panels');
  if(panels){
    const items=[...panels.querySelectorAll(':scope > details[data-panel]')];
    const order=JSON.parse(panels.dataset.order||'[]');
    items.sort((a,b)=>{const rank=x=>order.includes(x.dataset.panel)?order.indexOf(x.dataset.panel):100; return rank(a)-rank(b);}).forEach(x=>panels.append(x));
    let dragged=null;
    items.forEach(panel=>{
      const summary=panel.querySelector('summary'); summary.draggable=true;
      summary.addEventListener('dragstart',event=>{dragged=panel; event.dataTransfer.setData('text/plain',panel.dataset.panel);});
      panel.addEventListener('dragover',event=>event.preventDefault());
      panel.addEventListener('drop',event=>{event.preventDefault(); if(dragged&&dragged!==panel){panels.insertBefore(dragged,panel);say('Panel moved. Save your panel order.');}dragged=null;});
      ['Move up','Move down'].forEach((text,index)=>{
        const button=document.createElement('button');button.type='button';button.textContent=text;button.setAttribute('aria-label',`${text}: ${summary.childNodes[0].textContent}`);
        button.addEventListener('click',event=>{event.preventDefault();const siblings=[...panels.querySelectorAll(':scope > details[data-panel]')];const n=siblings.indexOf(panel);const target=siblings[n+(index?1:-1)];if(target){panels.insertBefore(panel,index?target.nextSibling:target);say('Panel moved. Save your panel order.');}});summary.append(' ',button);
      });
    });
    const form=document.getElementById('panel-layout-form');
    if(form)form.addEventListener('submit',()=>{form.elements.layout.value=JSON.stringify([...panels.querySelectorAll(':scope > details[data-panel]')].map(x=>x.dataset.panel));});
  }
  document.querySelectorAll('form[data-editor]').forEach(form=>{
    const welcome=form.dataset.editor==='welcome';const documentInput=form.elements.document;let doc=JSON.parse(documentInput.value);let elements=welcome?doc.elements:doc;
    const list=form.querySelector('.editor-elements');const canvas=form.querySelector('canvas');const background=form.elements.background;
    if(background){background.value=doc.background;background.addEventListener('input',()=>{doc.background=background.value;sync();});}
    const sync=()=>{documentInput.value=JSON.stringify(doc);preview();};
    function preview(){
      if(welcome){
        const ctx=canvas.getContext('2d');ctx.fillStyle=doc.background;ctx.fillRect(0,0,900,260);
        const values={header:'Welcome, Sample member!',server:'Your server',message:'Welcome to our community!',brand:'Vivi'};
        elements.forEach(e=>{ctx.fillStyle=e.color;if(e.type==='avatar'){ctx.beginPath();ctx.arc(e.x+e.size/2,e.y+e.size/2,e.size/2,0,2*Math.PI);ctx.fill();}else{ctx.font=`${e.size}px sans-serif`;ctx.textBaseline='top';ctx.fillText(e.type==='text'?e.value:values[e.type],e.x,e.y);}});
      }else{
        const view=form.querySelector('.announcement-preview');view.replaceChildren();elements.forEach(e=>{const p=document.createElement(e.type==='title'?'h3':'p');p.textContent=e.type==='divider'?'──────────':(e.name?e.name+': ':'')+(e.value||'');view.append(p);});
      }
    }
    function render(){
      list.replaceChildren();elements.forEach((element,index)=>{
        const box=document.createElement('fieldset');const legend=document.createElement('legend');legend.textContent=`${index+1}. ${element.type}`;box.append(legend);box.draggable=true;
        box.addEventListener('dragstart',event=>event.dataTransfer.setData('text/plain',String(index)));
        box.addEventListener('dragover',event=>event.preventDefault());box.addEventListener('drop',event=>{event.preventDefault();event.stopPropagation();const from=Number(event.dataTransfer.getData('text/plain'));if(Number.isInteger(from)&&from>=0&&from<elements.length){elements.splice(index,0,elements.splice(from,1)[0]);render();}});
        const keys=welcome?['x','y','size','color',...(element.type==='text'?['value']:[])]:element.type==='divider'?[]:element.type==='field'?['name','value']:['value'];
        keys.forEach(key=>{const label=document.createElement('label');label.textContent=key+' ';const input=document.createElement(key==='value'?'textarea':'input');if(key!=='value')input.type=key==='color'?'color':['x','y','size'].includes(key)?'number':'text';input.value=element[key]??'';input.addEventListener('input',()=>{element[key]=['x','y','size'].includes(key)?Number(input.value):input.value;sync();});label.append(input);box.append(label);});
        ['Up','Down','Remove'].forEach((text,n)=>{const button=document.createElement('button');button.type='button';button.textContent=text;button.addEventListener('click',()=>{if(n===2)elements.splice(index,1);else{const target=index+(n===1?1:-1);if(target>=0&&target<elements.length)[elements[target],elements[index]]=[elements[index],elements[target]];}render();});box.append(button);});list.append(box);
      });sync();
    }
    form.querySelector('.add-element').addEventListener('click',()=>{if(elements.length>=12){say('Maximum twelve elements.');return;}const type=form.querySelector('.new-type').value;elements.push(welcome?{type,x:30,y:30,size:type==='avatar'?80:20,color:'#ffffff',value:type==='text'?'Your text':''}:{type,name:type==='field'?'Field':'',value:type==='divider'?'':'Your text'});render();});
    if(canvas){let selected=null;canvas.style.maxWidth='100%';canvas.style.touchAction='none';
      const point=event=>{const rect=canvas.getBoundingClientRect();return {x:(event.clientX-rect.left)*900/rect.width,y:(event.clientY-rect.top)*260/rect.height};};
      canvas.addEventListener('pointerdown',event=>{const p=point(event);selected=[...elements].reverse().find(e=>p.x>=e.x&&p.x<=e.x+(e.type==='avatar'?e.size:300)&&p.y>=e.y&&p.y<=e.y+e.size);if(selected)canvas.setPointerCapture(event.pointerId);});
      canvas.addEventListener('pointermove',event=>{if(!selected)return;const p=point(event);selected.x=Math.round(Math.max(0,Math.min(900-(selected.type==='avatar'?selected.size:1),p.x)));selected.y=Math.round(Math.max(0,Math.min(260-(selected.type==='avatar'?selected.size:1),p.y)));sync();});
      canvas.addEventListener('pointerup',()=>{selected=null;render();});
    }
    form.addEventListener('submit',sync);render();
  });
  // Index existing authorized controls; selecting a result only opens/focuses it.
  const palette=document.getElementById('command-palette');
  if(panels&&palette){
    const search=document.getElementById('palette-search'),results=document.getElementById('palette-results');
    const entries=[];const navigation=document.getElementById('section-links');
    [...panels.querySelectorAll(':scope > details[data-panel]')].forEach(section=>{
      const title=section.querySelector('summary').childNodes[0].textContent.trim();if(!section.id)section.id='panel-'+section.dataset.panel;
      const link=document.createElement('a');link.href='#'+section.id;link.textContent=title;
      link.addEventListener('click',()=>{section.open=true;const menu=document.getElementById('mobile-navigation');if(menu)menu.open=false;});navigation.append(link);
      entries.push({label:title,target:section,section});
      section.querySelectorAll('form').forEach(form=>{
        const key=form.querySelector('input[name="name"],input[name="feature"]')?.value||'';
        const label=(key||form.querySelector('label')?.textContent||form.querySelector('button')?.textContent||'Settings').trim().replace(/\s+/g,' ').slice(0,110);
        const previous=form.previousElementSibling;const heading=previous&&previous.matches('h2,h3,h4')?previous.textContent.trim():'';
        const labels=[...form.querySelectorAll('label')].map(label=>label.textContent).join(' ');
        const fields=[...form.querySelectorAll('input,textarea,select')].map(control=>control.name).join(' ');
        entries.push({label:title+' · '+(heading?heading+' · ':'')+label,target:form,section,keywords:(form.getAttribute('action')||'')+' '+fields+' '+labels+' '+[...form.querySelectorAll('button')].map(button=>button.textContent).join(' ')});
      });
    });
    const close=()=>{if(typeof palette.close==='function')palette.close();else palette.removeAttribute('open');document.getElementById('palette-open').focus();};
    const inline=document.getElementById('settings-search'),inlineResults=document.getElementById('settings-search-results'),inlineStatus=document.getElementById('settings-search-status');
    const aliases={safety:['moderation','automod','raid','spam'],birthday:['birthday','birthdays'],welcome:['welcome','newcomer'],security:['raid','automod','spam'],scam:['scam','blocked','suspicious'],xp:['xp','level']};
    function find(query){
      const terms=query.toLowerCase().replaceAll('_',' ').trim().split(/\s+/).filter(Boolean);
      return entries.filter(entry=>{const text=(entry.label+' '+(entry.keywords||'')).replaceAll('_',' ').toLowerCase();return terms.every(term=>text.includes(term)||(aliases[term]||[]).some(alias=>text.includes(alias)));});
    }
    function go(entry){
      entry.target.hidden=false;entry.section.hidden=false;
      let parent=entry.target;while(parent&&parent!==panels){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}
      entry.section.open=true;entry.target.scrollIntoView?.({block:'center',behavior:'auto'});
      const control=entry.target.querySelector('input:not([type=hidden]),select,textarea,button');if(control)control.focus();else{entry.target.tabIndex=-1;entry.target.focus();}
    }
    function renderMatches(query,container,onChoose){
      container.replaceChildren();const matches=find(query);
      matches.slice(0,30).forEach(entry=>{const button=document.createElement('button');button.type='button';button.textContent=entry.label;button.addEventListener('click',()=>{onChoose();go(entry);if(inlineStatus)inlineStatus.textContent='Opened '+entry.label;});container.append(button);});
      if(!matches.length){const text=document.createElement('p');text.textContent='No matching settings.';container.append(text);}
      return matches.length;
    }
    function display(){renderMatches(search.value,results,close);}
    if(inline&&inlineResults){
      const refresh=()=>{const query=inline.value.trim();inlineResults.hidden=!query;if(!query){inlineResults.replaceChildren();if(inlineStatus)inlineStatus.textContent='';return;}const count=renderMatches(query,inlineResults,()=>{inlineResults.hidden=true;});if(inlineStatus)inlineStatus.textContent=count+' matching settings'+(count>30?' · showing first 30; refine your search':'');};
      inline.addEventListener('input',refresh);inline.addEventListener('focus',()=>{if(inline.value.trim())refresh();});
      inline.addEventListener('keydown',event=>{if(event.key==='ArrowDown'){event.preventDefault();inlineResults.querySelector('button')?.focus();}if(event.key==='Enter'){event.preventDefault();inlineResults.querySelector('button')?.click();}if(event.key==='Escape'){inline.value='';refresh();}});
    }
    const open=()=>{if(typeof palette.showModal==='function')palette.showModal();else palette.setAttribute('open','');search.value='';display();search.focus();};
    document.getElementById('palette-open').addEventListener('click',open);document.getElementById('palette-close').addEventListener('click',close);search.addEventListener('input',display);
    search.addEventListener('keydown',event=>{if(event.key==='ArrowDown'){event.preventDefault();results.querySelector('button')?.focus();}});
    palette.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}});
    document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();open();}});
  }
  const panelForm=document.getElementById('panel-layout-form');
  const syncOrder=()=>{if(panelForm&&panels)panelForm.elements.layout.value=JSON.stringify([...panels.querySelectorAll(':scope > details[data-panel]')].map(x=>x.dataset.panel));};
  syncOrder();if(panels)panels.addEventListener('click',syncOrder);if(panels)panels.addEventListener('drop',syncOrder);
  // Compare actual form values, including the editors' hidden JSON documents.
  const snapshot=form=>JSON.stringify([...new FormData(form)].map(([key,value])=>[key,typeof value==='string'?value:{name:value.name,size:value.size,lastModified:value.name?value.lastModified:0}]));
  const initialForms=new Map([...document.querySelectorAll('form:not([data-module-toggle]):not(#module-filters)')].map(form=>[form,snapshot(form)]));let submitting=null;
  initialForms.forEach((value,form)=>form.addEventListener('submit',()=>{submitting=form;setTimeout(()=>{submitting=null;},1000);}));
  window.addEventListener('beforeunload',event=>{if([...initialForms].some(([form,original])=>form!==submitting&&snapshot(form)!==original)){event.preventDefault();event.returnValue='';}});
})();
