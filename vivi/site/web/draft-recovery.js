'use strict';
(()=>{
 const form=document.querySelector('#message-composer,#embed-writer');if(!form)return;
 const embed=form.getAttribute('id')==='embed-writer',prefix='vivi:draft:v1:',owner=form.dataset.draftOwner,guild=form.elements.guild.value;
 if(!owner)return;
 const names=embed?['name','title','description','footer','url','image','thumbnail','color','fields']:['mode','channel','text','template','cards','enabled','custom_color','accent_color','appearance_thumbnail','appearance_image'];
 const key=prefix+owner+':'+guild+':'+(embed?'embed:'+form.elements.id.value+':'+(new URLSearchParams(location.search).get('preset')||''):form.elements.kind.value),ttl=7*86400000;
 const get=()=>Object.fromEntries(names.filter(name=>form.elements[name]).map(name=>{const input=form.elements[name];return [name,input.type==='checkbox'?input.checked:input.value];}));
 const initial=get(),baseline=JSON.stringify(initial);let available=true,pending=null,discarded=null;
 const panel=document.createElement('section');panel.className='draft-recovery';panel.setAttribute('aria-label','Browser draft recovery');
 const status=document.createElement('p');status.setAttribute('role','status');
 const restore=document.createElement('button'),discard=document.createElement('button');restore.type=discard.type='button';restore.textContent='Restore draft';discard.textContent='Discard draft';panel.append(status,restore,discard);form.prepend(panel);
 function clear(){try{localStorage.removeItem(key);}catch{}pending=null;restore.hidden=true;discard.hidden=true;}
 function save(){
  if(pending||JSON.stringify(get())===discarded)return; // Preserve the recoverable draft until the user chooses restore or discard.
  try{
   const value=get();
   if(JSON.stringify(value)===baseline){clear();status.textContent='Draft recovery ready · stored only in this browser for up to 7 days.';return;}
   localStorage.setItem(key,JSON.stringify({at:Date.now(),values:value}));discard.hidden=false;restore.hidden=true;status.textContent='Draft saved in this browser · not published or saved to Vivi’s settings.';
  }catch{available=false;form.dataset.draftReady='false';status.textContent='Browser storage is unavailable. Keep this page open or save your changes to Vivi.';}
 }
 try{
  const now=Date.now();
  for(const item of Object.keys(localStorage))if(item.startsWith(prefix)){
   try{const data=JSON.parse(localStorage.getItem(item));if(!Number.isFinite(data.at)||data.at<now-ttl||data.at>now+60000)localStorage.removeItem(item);}catch{localStorage.removeItem(item);}
  }
  const submitted=JSON.parse(sessionStorage.getItem(prefix+'submitted')||'null');
  if(submitted&&submitted.key.startsWith(prefix+owner+':'+guild+':')&&submitted.path===location.pathname){
   if(new URLSearchParams(location.search).get('draft_saved')===submitted.nonce&&now-submitted.at<120000)localStorage.removeItem(submitted.key);
   sessionStorage.removeItem(prefix+'submitted');
  }
  const stored=JSON.parse(localStorage.getItem(key)||'null');
  if(stored&&stored.values&&typeof stored.values==='object'&&!Array.isArray(stored.values)&&JSON.stringify(stored.values)!==baseline){pending=stored;status.textContent='An unfinished draft from '+new Date(stored.at).toLocaleString()+' is available. Restore it or discard it; your saved settings have not changed.';}
  else{clear();status.textContent='Draft recovery ready · stored only in this browser for up to 7 days.';}
 }catch{available=false;status.textContent='Browser draft recovery is unavailable. Save changes before closing this page.';}
 form.dataset.draftReady=String(available);restore.hidden=!pending;discard.hidden=!pending;
 restore.addEventListener('click',()=>{
  if(!pending)return;
  const values=pending.values;
  for(const name of names){const input=form.elements[name],value=values[name];if(!input||value===undefined)continue;
   if(input.type==='checkbox'){if(typeof value==='boolean')input.checked=value;}
   else if(typeof value==='string'&&value.length<=(name==='fields'?128000:24000)){
    if(input instanceof HTMLSelectElement&&!Array.from(input.options).some(option=>option.value===value))continue;
    input.value=value;
   }
  }
  pending=null;restore.hidden=true;form.dispatchEvent(new CustomEvent('vivi:draft-restored'));form.dispatchEvent(new Event('change',{bubbles:true}));status.textContent='Draft restored. Review it before saving or sending.';
 });
 discard.addEventListener('click',()=>{discarded=JSON.stringify(get());clear();status.textContent='Browser draft discarded. Current editor contents are unchanged.';});
 form.addEventListener('input',save);form.addEventListener('change',save);form.addEventListener('vivi:editor-update',save);
 form.addEventListener('submit',event=>{if(['save','duplicate'].includes(event.submitter?.value))try{const nonce=Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');let input=form.elements.draft_nonce;if(!input){input=document.createElement('input');input.type='hidden';input.name='draft_nonce';form.append(input);}input.value=nonce;sessionStorage.setItem(prefix+'submitted',JSON.stringify({key,nonce,at:Date.now(),path:location.pathname}));}catch{}});
 window.addEventListener('pagehide',()=>{if(available&&!pending)save();});
})();
