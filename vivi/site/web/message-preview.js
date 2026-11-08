'use strict';
(()=>{
 const form=document.querySelector('#message-composer'),preview=document.querySelector('#message-live-preview');if(!form||!preview)return;
 const data=document.querySelector('#message-preview-data').dataset,documents=JSON.parse(data.documents),server=data.server,count=data.count;
 const status=document.querySelector('#message-send-status'),send=document.querySelector('#message-send'),dialog=document.querySelector('#confirm-message-send'),confirm=document.querySelector('#confirm-message-submit');let sending=false;
 const original=JSON.stringify([...new FormData(form)]);
 const expand=value=>String(value||'').replaceAll('{member}','@Sample member').replaceAll('{username}','Sample member').replaceAll('{server}',server).replaceAll('{member_count}',count);
 // A small, safe subset of Discord formatting. Unmatched text stays literal.
 function formatted(parent,value){
  const source=expand(value),pattern=/(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*)/g;let start=0;
  for(const match of source.matchAll(pattern)){parent.append(document.createTextNode(source.slice(start,match.index)));const token=match[0],element=document.createElement(token.startsWith('**')?'strong':token.startsWith('`')?'code':'em');element.textContent=token.startsWith('**')?token.slice(2,-2):token.slice(1,-1);parent.append(element);start=match.index+token.length;}
  parent.append(document.createTextNode(source.slice(start)));
 }
 function selectedEmbed(){return documents[form.elements.template.value];}
 function draw(){
  const mode=form.elements.mode.value;const dirty=JSON.stringify([...new FormData(form)])!==original;document.querySelector('#message-draft-state').textContent=dirty?'Unsaved changes':'No unsaved changes';
  form.elements.text.required=mode==='text';form.elements.channel.setCustomValidity(form.elements.enabled.checked&&form.elements.channel.value==='0'?'Choose a channel before enabling automatic messages.':'');document.querySelectorAll('[data-message-mode]').forEach(panel=>{panel.hidden=panel.dataset.messageMode!==mode;});
  document.querySelector('#message-character-count').textContent=form.elements.text.value.length+' / 1,800';
  const channel=form.elements.channel.selectedOptions[0]?.textContent||'Choose a channel';document.querySelector('#message-preview-channel').textContent=form.elements.channel.value==='0'?'Choose a destination to send this message':channel;
  const doc=selectedEmbed(),validEmbed=!!doc?.name;form.querySelector('button[value="save"]').disabled=sending||(mode==='embed'&&!validEmbed);send.disabled=sending||form.elements.channel.value==='0'||(mode==='embed'&&!validEmbed);const sample=document.querySelector('#message-test-welcome');if(sample)sample.disabled=send.disabled;
  document.querySelector('#embed-choice-status').textContent=mode==='embed'?(validEmbed?'Using “'+doc.name+'”':'Choose an embed to finish this message.') : '';
  preview.replaceChildren();preview.classList.toggle('is-text-message',mode==='text');
  const text=document.createElement('p');
  if(mode==='text'){preview.style.borderColor='#ff65ad';formatted(text,form.elements.text.value||'Your message will appear here…');preview.append(text);}
  else{
   if(!validEmbed){preview.classList.add('is-empty');text.textContent='Pick an embed from your library to see it here.';preview.append(text);return;}
   preview.style.borderColor=form.elements.custom_color.checked?form.elements.accent_color.value:doc.color||'#ff65ad';const title=document.createElement('strong');formatted(title,doc.title);formatted(text,doc.description);preview.append(title,text);
   const fields=document.createElement('div');fields.className='preview-embed-fields';
   for(const field of doc.fields||[]){const item=document.createElement('div'),title=document.createElement('strong'),value=document.createElement('p');item.className=field.inline?'is-inline':'';formatted(title,field.name);formatted(value,field.value);item.append(title,value);fields.append(item);}preview.append(fields);
   for(const key of ['thumbnail','image']){
    const source=form.elements['appearance_'+key].value,url=source==='member'?data.memberAvatar:source==='server'?data.serverIcon:source==='template'?doc[key]:'';
    if(!url)continue;
    if(url.startsWith('/assets/')||/^https:\/\/cdn\.discordapp\.com\//.test(url)){
     const image=document.createElement('img');image.src=url;image.alt=source==='member'?'Sample member profile picture':source==='server'?'Server icon':key;image.className='welcome-preview-'+key;image.addEventListener('error',()=>image.remove(),{once:true});if(key==='thumbnail')preview.prepend(image);else preview.append(image);
    }else{const note=document.createElement('p');note.className='preview-media-note';note.textContent=key+' included in this embed';preview.append(note);}
   }
   const footer=document.createElement('small');formatted(footer,doc.footer);preview.append(footer);
  }
  preview.classList.remove('is-empty');
 }
 form.querySelectorAll('[data-insert-token]').forEach(button=>button.addEventListener('click',()=>{const input=form.elements.text,token='{'+button.dataset.insertToken+'}';if(input.value.length-(input.selectionEnd-input.selectionStart)+token.length>1800){status.textContent='Not enough room for this placeholder.';return;}input.setRangeText(token,input.selectionStart,input.selectionEnd,'end');input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();}));
 document.querySelector('#message-refresh-embeds').addEventListener('click',async event=>{
  const button=event.currentTarget;button.disabled=true;
  try{
   const response=await fetch('/api/embed-templates?guild='+encodeURIComponent(form.elements.guild.value),{credentials:'same-origin',cache:'no-store'});
   if(!response.ok)throw new Error(response.status===429?'Discord is busy. Try refreshing the library in a moment.':'Could not refresh the embed library. Check your connection and permissions.');
   const result=await response.json(),selected=form.elements.template.value;
   for(const key of Object.keys(documents))if(key)delete documents[key];
   form.elements.template.replaceChildren(new Option(documents['']?.name?'Current: '+documents[''].name:'Choose a saved embed',''));
   for(const template of result.templates){documents[template.id]=template.document;form.elements.template.append(new Option(template.document.name,template.id));}
   form.elements.template.value=documents[selected]?selected:'';status.textContent='Library refreshed. Your draft is kept.';draw();
  }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
 });
 send.addEventListener('click',()=>{
  if(sending||!form.reportValidity())return;
  document.querySelector('#confirm-message-destination').textContent='Post this '+form.elements.kind.value+' message in '+form.elements.channel.selectedOptions[0].textContent+'?';dialog.showModal();
 });
 document.querySelector('#message-test-welcome')?.addEventListener('click',()=>send.click());
 document.querySelector('#confirm-message-cancel').addEventListener('click',()=>dialog.close());
 confirm.addEventListener('click',async()=>{
  if(sending)return;sending=true;confirm.disabled=true;dialog.close();status.textContent='Sending your message…';draw();
  try{
   const body=new FormData(form);body.set('action','send');body.set('confirm_send','yes');
   const response=await fetch('/messages',{method:'POST',body,headers:{Accept:'application/json'},credentials:'same-origin'});
   if(!response.ok){const message=await response.text();throw new Error(response.status===401?'Your session ended. Sign in again.':response.status===429?'Discord is busy. Wait before trying again.':message.startsWith('<')?'Could not send this message. Check the channel before trying again.':message.slice(0,350));}
   const result=await response.json();status.replaceChildren(document.createTextNode('Sent to Discord. Your settings have not changed. '));
   if(result.url&&/^https:\/\/discord\.com\/channels\/\d+\/\d+\/\d+$/.test(result.url)){const link=document.createElement('a');link.href=result.url;link.target='_blank';link.rel='noopener';link.textContent='View message →';status.append(link);}
  }catch(error){status.textContent=error.message;}
  finally{sending=false;confirm.disabled=false;draw();}
 });
 form.querySelectorAll('button[type="submit"],button[name="action"]').forEach(button=>button.addEventListener('click',draw));
 const edited=()=>{if(!sending)status.textContent='';draw();};form.addEventListener('input',edited);form.addEventListener('change',edited);window.addEventListener('pageshow',()=>setTimeout(draw,0));draw();
})();
