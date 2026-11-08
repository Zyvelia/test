'use strict';
(()=>{
 const form=document.querySelector('#embed-writer');if(!form)return;
 const container=document.querySelector('#embed-fields'),hidden=form.elements.fields,preview=document.querySelector('#embed-preview');
 let fields=JSON.parse(hidden.value);
 function update(){
  hidden.value=JSON.stringify(fields);
  form.dispatchEvent(new Event('vivi:editor-update'));
  for(const key of ['title','description','footer'])preview.querySelector('[data-preview="'+key+'"]').textContent=form.elements[key].value;
  preview.style.borderColor=form.elements.color.value;
  const target=preview.querySelector('[data-preview="fields"]');target.replaceChildren();
  for(const field of fields){const block=document.createElement('div'),title=document.createElement('strong'),text=document.createElement('p');title.textContent=field.name;text.textContent=field.value;block.append(title,text);target.append(block);}
  const size=['title','description','footer'].reduce((n,k)=>n+form.elements[k].value.length,0)+fields.reduce((n,f)=>n+f.name.length+f.value.length,0);
  document.querySelector('#embed-count').textContent=size+' / 6,000 characters · '+fields.length+' / 25 fields';
  document.querySelector('#embed-add-field').disabled=fields.length>=25;
  form.elements.description.setCustomValidity(size>6000?'Embed text exceeds 6,000 characters.':'');
 }
 function draw(){container.replaceChildren();fields.forEach((field,index)=>{
  const row=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='Field '+(index+1);row.append(legend);
  for(const [key,max] of [['name',256],['value',1024]]){const label=document.createElement('label'),input=document.createElement(key==='value'?'textarea':'input');label.textContent=key==='name'?'Field name':'Field text';input.value=field[key];input.maxLength=max;input.required=true;input.addEventListener('input',()=>{field[key]=input.value;update();});label.append(input);row.append(label);}
  const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=field.inline;check.addEventListener('change',()=>{field.inline=check.checked;update();});label.append(check,document.createTextNode(' Inline field'));row.append(label);
  for(const [text,delta] of [['Move up',-1],['Move down',1],['Remove',0]]){const button=document.createElement('button');button.type='button';button.textContent=text;button.disabled=delta<0&&index===0||delta>0&&index===fields.length-1;button.addEventListener('click',()=>{if(!delta)fields.splice(index,1);else [fields[index],fields[index+delta]]=[fields[index+delta],fields[index]];draw();});row.append(button);}container.append(row);
 });update();}
 document.querySelector('#embed-add-field').addEventListener('click',()=>{if(fields.length<25){fields.push({name:'',value:'',inline:false});draw();}});
 form.addEventListener('vivi:draft-restored',()=>{try{const value=JSON.parse(hidden.value);if(!Array.isArray(value)||value.length>25||value.some(field=>!field||typeof field.name!=='string'||field.name.length>256||typeof field.value!=='string'||field.value.length>1024||typeof field.inline!=='boolean'))throw new Error();fields=value;draw();}catch{hidden.value=JSON.stringify(fields);draw();}});
 let dirty=false;form.addEventListener('input',()=>{dirty=true;update();});form.addEventListener('click',event=>{if(event.target.type==='button')dirty=true;});form.addEventListener('submit',()=>{update();dirty=false;});window.addEventListener('beforeunload',event=>{if(dirty&&form.dataset.draftReady!=='true'){event.preventDefault();event.returnValue='';}});draw();
})();
