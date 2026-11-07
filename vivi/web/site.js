'use strict';
(() => {
  const toggle=document.getElementById('menu-toggle'),navigation=document.getElementById('site-navigation');
  const closeMenu=()=>{navigation?.classList.remove('is-open');toggle?.setAttribute('aria-expanded','false');};
  toggle?.addEventListener('click',()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));navigation.classList.toggle('is-open',open);});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
  navigation?.addEventListener('click',event=>{if(event.target.closest('a'))closeMenu();});
  fetch('/api/status',{credentials:'omit'}).then(response=>{if(!response.ok)throw new Error('Status unavailable');return response.json();}).then(data=>{
    document.querySelectorAll('[data-site-status]').forEach(el=>{el.textContent=data.online?'Bot connected':'Bot not connected';});
    document.querySelectorAll('[data-site-dot]').forEach(el=>{el.dataset.state=data.online?'online':'offline';});
  }).catch(()=>document.querySelectorAll('[data-site-status]').forEach(el=>{el.textContent='Connection status unavailable';}));
  const form=document.getElementById('command-search-form');
  async function copy(button){
    try{await navigator.clipboard.writeText(button.dataset.copy);button.textContent='Copied';setTimeout(()=>{button.textContent='Copy';},1800);}
    catch{button.textContent='Select to copy';}
  }
  document.addEventListener('click',event=>{const button=event.target.closest('[data-copy]');if(button)copy(button);});
  if(form){
    const search=document.getElementById('command-search'),category=document.getElementById('command-category'),results=document.getElementById('command-results'),count=document.getElementById('command-count');let commands=null;
    function render(){
      if(!commands)return;
      const terms=search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      const selected=commands.filter(row=>(category.value==='all'||row.category===category.value)&&terms.every(term=>(row.name+' '+row.description).toLowerCase().includes(term)));
      results.replaceChildren();
      selected.forEach(row=>{const card=document.createElement('article');card.className='command-card';const header=document.createElement('header'),name=document.createElement('code'),button=document.createElement('button'),description=document.createElement('p');name.textContent=row.name;button.type='button';button.className='copy-button';button.dataset.copy=row.name;button.setAttribute('aria-label','Copy '+row.name);button.textContent='Copy';description.textContent=row.description;header.append(name,button);card.append(header,description);results.append(card);});
      if(!selected.length){const empty=document.createElement('p');empty.className='empty-state';empty.textContent='No matching commands. Try another search or category.';results.append(empty);}
      count.textContent=selected.length+' of '+commands.length+' commands';
      const query=new URLSearchParams();if(search.value)query.set('search',search.value);if(category.value!=='all')query.set('category',category.value);history.replaceState(null,'','/commands'+(query.size?'?'+query.toString():''));
    }
    fetch('/api/commands',{credentials:'omit'}).then(response=>{if(!response.ok)throw new Error('Directory unavailable');return response.json();}).then(data=>{commands=data.commands;render();form.addEventListener('submit',event=>{event.preventDefault();render();});search.addEventListener('input',render);category.addEventListener('change',render);}).catch(()=>{/* The server-rendered search form remains fully usable. */});
  }
  document.addEventListener('DOMContentLoaded',()=>{const rail=document.querySelector('[data-dashboard-sections]');if(rail)document.querySelectorAll('#section-links a').forEach(link=>rail.append(link.cloneNode(true)));});
})();
