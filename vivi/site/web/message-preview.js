'use strict';
(()=>{
 const form=document.querySelector('#message-composer'),preview=document.querySelector('#message-live-preview');if(!form||!preview)return;
 const data=document.querySelector('#message-preview-data').dataset,documents=JSON.parse(data.documents),server=data.server,count=data.count;
 const expand=value=>String(value||'').replaceAll('{member}','@Sample member').replaceAll('{username}','Sample member').replaceAll('{server}',server).replaceAll('{member_count}',count);
 function draw(){
  preview.replaceChildren();const mode=form.elements.mode.value;
  const text=document.createElement('p');
  if(mode==='text'){preview.style.borderColor='#ff65ad';text.textContent=expand(form.elements.text.value);preview.append(text);}
  else{
   const doc=documents[form.elements.template.value];
   if(!doc||!doc.name){text.textContent='Choose a saved embed to preview it here.';preview.append(text);return;}
   preview.style.borderColor=doc.color||'#ff65ad';const title=document.createElement('strong');title.textContent=expand(doc.title);text.textContent=expand(doc.description);preview.append(title,text);
   for(const field of doc.fields||[]){const title=document.createElement('strong'),value=document.createElement('p');title.textContent=expand(field.name);value.textContent=expand(field.value);preview.append(title,value);}
   const footer=document.createElement('small');footer.textContent=expand(doc.footer);preview.append(footer);
  }
 }
 form.addEventListener('input',draw);form.addEventListener('change',draw);draw();
})();
