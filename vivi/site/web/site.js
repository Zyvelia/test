'use strict';
(() => {
  const toggle=document.getElementById('menu-toggle'),navigation=document.getElementById('site-navigation');
  const closeMenu=()=>{navigation?.classList.remove('is-open');toggle?.setAttribute('aria-expanded','false');};
  toggle?.addEventListener('click',()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));navigation.classList.toggle('is-open',open);});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu();});
  navigation?.addEventListener('click',event=>{if(event.target.closest('a'))closeMenu();});
  fetch('/api/status',{credentials:'omit'}).then(response=>{if(!response.ok)throw new Error('Status unavailable');return response.json();}).then(data=>{
    document.querySelectorAll('[data-site-status]').forEach(el=>{el.textContent=data.online?'Vivi bot online':'Vivi bot offline';});
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
  const sync=document.querySelector('[data-dashboard-sync]');
  if(sync){
    let dirty=false,checking=false;const status=sync.querySelector('[role=status]');
    document.addEventListener('input',event=>{if(event.target.closest('form'))dirty=true;});
    document.addEventListener('change',event=>{if(event.target.closest('form'))dirty=true;});
    async function check(){
      if(checking||document.hidden)return;checking=true;
      try{
        const response=await fetch('/api/dashboard-state?guild='+encodeURIComponent(sync.dataset.guild),{cache:'no-store'});
        if(!response.ok){status.textContent=requestError(response,'Cannot check for updates right now. Your settings are unchanged.');return;}
        const data=await response.json();
        if(data.revision!==sync.dataset.revision){
          if(!dirty){location.reload();return;}
          status.replaceChildren(document.createTextNode('Settings changed in Discord or another dashboard. Your unsaved edits are kept here. '));
          const reload=document.createElement('button');reload.textContent='Reload saved settings';reload.type='button';reload.onclick=()=>{if(confirm('Discard unsaved edits and load the latest saved settings?'))location.reload();};status.append(reload);
        }else status.textContent='Settings synced with Discord · checked just now.';
      }catch{status.textContent='Cannot check for updates. Your saved settings remain in the bot; retrying shortly.';}
      finally{checking=false;}
    }
    setInterval(check,30000);window.addEventListener('focus',check);document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
    const settingPanel=document.getElementById('module-settings');
    const prefixes={scam_images:['scam_image_'],welcome:['welcome','autorole'],autorole:['autorole'],rules:['rules_'],staff_reviews:['review_','reviewer_'],lfg:['lfg_'],goodbye:['goodbye'],roles:['rules','autorole'],automod:['blocked','spam','dm_'],moderation:['warning','dm_','review'],birthdays:['birthday','timezone','daily_hour'],daily_questions:['daily','timezone'],ai:['ai_'],raid_protection:['raid_'],mention_protection:['mention_'],warning_thresholds:['warning_'],voice_rooms:['voice_'],scheduled_backups:['backup_'],ticket_tools:['review'],tickets:['review'],xp:['language'],translation:['language']};
    document.querySelectorAll('[data-module-configure]').forEach(link=>link.addEventListener('click',event=>{
      event.preventDefault();const feature=link.dataset.moduleConfigure;
      const specialized={welcome_cards:'Dashboard studio',custom_aliases:'Custom command aliases',xp:'Per-channel XP',notifications:'Twitch',instant_webhooks:'Twitch',tickets:'Ticket categories',ticket_tools:'Ticket categories'};
      const target=specialized[feature]&&Array.from(document.querySelectorAll('.dashboard-content details')).find(panel=>panel.querySelector('summary')?.textContent.includes(specialized[feature]));
      const panel=target||settingPanel;if(!panel)return;panel.open=true;
      if(panel===settingPanel){
        let note=panel.querySelector('.settings-filter-note');if(!note){note=document.createElement('div');note.className='settings-filter-note';panel.querySelector('summary').after(note);}
        note.replaceChildren(document.createTextNode('Customizing '+feature.replaceAll('_',' ')+'. '));
        const showAll=document.createElement('button');showAll.type='button';showAll.textContent='Show all settings';showAll.onclick=()=>{panel.querySelectorAll('[data-setting]').forEach(form=>form.hidden=false);note.textContent='All feature settings';};note.append(showAll);
        const matches=prefixes[feature];panel.querySelectorAll('[data-setting]').forEach(form=>{form.hidden=!!matches&&!matches.some(prefix=>form.dataset.setting.startsWith(prefix));});
      }
      panel.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
    }));
    const desiredModule=new URLSearchParams(location.search).get('module');
    if(desiredModule)document.addEventListener('DOMContentLoaded',()=>{const link=[...document.querySelectorAll('[data-module-configure]')].find(link=>link.dataset.moduleConfigure===desiredModule);link?.click();});
  }
  function requestError(response,fallback){
    if(response.status===401){const account=document.querySelector('.account-menu');if(account){const link=document.createElement('a');link.className='nav-login';link.href='/login';link.textContent='Sign in with Discord';account.replaceWith(link);}return 'Your Discord session ended. Sign in again to reconnect.';}
    if(response.status===403)return 'You do not have permission for this action. Your account is still signed in.';
    if(response.status===429)return 'Discord is limiting requests. You are still signed in; wait a moment before retrying.';
    if(response.status===503)return 'Discord is temporarily unavailable. You are still signed in; try again shortly.';
    return fallback;
  }
  const manager=document.querySelector('[data-module-manager]');
  if(manager){
    const filter=document.getElementById('module-filters'),search=filter.elements.search,category=filter.elements.category,state=filter.elements.state,cards=[...manager.querySelectorAll('[data-feature-module]')],status=document.getElementById('module-manager-status');let epoch=0,polling=false;
    function render(){
      const terms=search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);let count=0;
      cards.forEach(card=>{const family=card.closest('[data-module-family]');const show=(category.value==='all'||card.dataset.group===category.value)&&(state.value==='all'||(state.value==='enabled')===(card.dataset.enabled==='true'))&&terms.every(term=>(card.dataset.featureModule.replaceAll('_',' ')+' '+card.textContent+' '+(family?.querySelector('summary strong')?.textContent||'')).toLowerCase().includes(term));card.hidden=!show;if(show)count++;});
      let sections=0;manager.querySelectorAll('[data-module-family]').forEach(family=>{
        const children=[...family.querySelectorAll('[data-feature-module]')],visible=children.some(card=>!card.hidden);family.hidden=!visible;if(visible)sections++;
        family.querySelector('.family-count').textContent=children.filter(card=>card.dataset.enabled==='true').length+' of '+children.length+' enabled';
        if(visible&&(search.value.trim()||category.value!=='all'||state.value!=='all'))family.open=true;
      });
      document.getElementById('module-count').textContent=sections+' sections · '+count+' of '+cards.length+' controls';document.getElementById('module-empty').hidden=count!==0;
      const query=new URLSearchParams({guild:manager.dataset.guild});if(search.value)query.set('search',search.value);if(category.value!=='all')query.set('category',category.value);if(state.value!=='all')query.set('state',state.value);history.replaceState(null,'','/modules?'+query);
    }
    function apply(card,on){
      card.querySelector('.module-save').textContent='';card.dataset.enabled=String(on);card.querySelector('[data-module-state]').textContent=on?'Enabled':'Disabled';const form=card.querySelector('form'),button=form.querySelector('button');form.elements.enabled.value=String(!on);button.setAttribute('aria-checked',String(on));button.textContent=on?'Disable':'Enable';const consent=form.querySelector('[data-global-consent]');if(consent){consent.hidden=on;const box=consent.querySelector('input');box.checked=false;box.required=!on;box.disabled=card.dataset.ownerCanEnable!=='true';button.disabled=!on&&card.dataset.ownerCanEnable!=='true';}
    }
    filter.addEventListener('submit',event=>{event.preventDefault();render();});search.addEventListener('input',render);category.addEventListener('change',render);state.addEventListener('change',render);
    manager.querySelectorAll('[data-module-toggle]').forEach(form=>form.addEventListener('submit',async event=>{
      event.preventDefault();const button=form.querySelector('button');if(button.disabled)return;epoch++;button.disabled=true;button.setAttribute('aria-busy','true');const card=form.closest('[data-feature-module]'),feedback=card.querySelector('.module-save');feedback.textContent='Saving…';
      try{
        const response=await fetch('/feature',{method:'POST',headers:{Accept:'application/json'},body:new URLSearchParams(new FormData(form)),credentials:'same-origin'});
        if(!response.ok)throw new Error(requestError(response,'Could not save this module. Try again.'));
        const data=await response.json();apply(card,data.enabled);feedback.textContent='Saved';status.textContent=card.querySelector('h3').textContent+' '+(data.enabled?'enabled':'disabled')+' · saved to your server.';render();
      }catch(error){feedback.textContent=error.message;status.textContent=error.message;}
      finally{epoch++;button.disabled=card.dataset.featureModule==='global_bans'&&card.dataset.ownerCanEnable!=='true'&&card.dataset.enabled!=='true';button.removeAttribute('aria-busy');}
    }));
    async function refresh(){
      if(polling||document.hidden||manager.querySelector('[aria-busy=true]'))return;polling=true;const started=epoch;
      try{
        const response=await fetch('/api/modules?guild='+encodeURIComponent(manager.dataset.guild),{cache:'no-store'});
        if(!response.ok)throw new Error(requestError(response,'Module sync is temporarily unavailable.'));
        const data=await response.json();if(started!==epoch)return;let changed=false;
        cards.forEach(card=>{const on=data.features[card.dataset.featureModule];if(typeof on==='boolean'&&card.dataset.enabled!==String(on)){apply(card,on);changed=true;}});if(changed){status.textContent='Module switches updated from Discord or another dashboard.';render();}
      }catch(error){status.textContent=error.message;}finally{polling=false;}
    }
    setInterval(refresh,30000);window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
    const rail=document.querySelector('[data-dashboard-sections]');if(rail&&!rail.children.length){
      [...category.options].forEach(option=>{const link=document.createElement('a'),query=new URLSearchParams({guild:manager.dataset.guild});if(option.value!=='all')query.set('category',option.value);link.href='/modules?'+query;link.textContent=option.textContent;link.addEventListener('click',event=>{event.preventDefault();category.value=option.value;render();});rail.append(link);});
    }
    render();
    if(location.hash.startsWith('#module-')){const target=document.getElementById(location.hash.slice(1));const family=target?.closest('[data-module-family]');if(family){family.open=true;target.scrollIntoView({block:'nearest'});}}
  }
})();
