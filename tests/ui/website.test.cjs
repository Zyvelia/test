'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const path=require('node:path');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const child=spawn(process.env.VIVI_PYTHON||'python',['scripts/preview_website.py','--port','0','--dashboard-preview'],{cwd:root});
 let browser;
 try{
  const url=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(new Error('Preview startup timed out')),20000);child.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/PREVIEW_READY=(http:\/\/127.0.0.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});child.stderr.on('data',chunk=>process.stderr.write(chunk));child.once('exit',code=>{clearTimeout(timer);reject(new Error('Preview exited '+code));});});
  browser=await chromium.launch({executablePath:process.env.VIVI_BROWSER_PATH||undefined,args:['--no-sandbox']});
  const context=await browser.newContext({viewport:{width:1440,height:960}});
  const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text());});
  for(const route of ['/','/features','/commands','/support','/privacy','/terms','/dashboard']){const response=await page.goto(url+route);assert.equal(response.status(),200,route);assert.equal(await page.locator('h1').count(),1);}
  await page.goto(url);await page.waitForFunction(()=>getComputedStyle(document.body).backgroundColor!=='rgba(0, 0, 0, 0)');assert.equal(await page.locator('img[src="/assets/vivi-avatar.png"]').evaluate(img=>img.complete&&img.naturalWidth>0),true);
  await page.screenshot({path:path.join(root,'docs/assets/website-desktop.png')});
  const catalog=await (await page.request.get(url+'/api/commands')).json();assert.equal(catalog.commands.length,158);assert(!catalog.commands.some(c=>['/admin faq_add','/admin faq_remove','/community faq'].includes(c.name)));
  const invite=await page.request.get(url+'/invite',{maxRedirects:0});const target=new URL(invite.headers().location);assert.equal(target.hostname,'discord.com');assert.equal(target.searchParams.get('client_id'),'1568121020047429775');assert.equal(target.searchParams.get('scope'),'bot applications.commands');
  assert.equal((await page.request.get(url+'/assets/.env')).status(),404);
  assert.equal((await page.request.get(url+'/login')).status(),503);
  assert.equal((await page.request.get(url+'/',{headers:{Host:'evil.example'}})).status(),403);
  assert.equal((await page.request.post(url+'/feature',{headers:{Origin:'https://evil.example'},data:{}})).status(),403);
  await page.goto(url+'/commands');await page.waitForLoadState('networkidle');await page.locator('#command-search').fill('chess');await page.waitForFunction(()=>document.querySelector('#command-count').textContent.startsWith('1 of'));assert.match(await page.locator('#command-results').innerText(),/chess/);
  await page.locator('#command-search').fill('zzzz-no-command');await page.waitForSelector('.empty-state');
  await context.addCookies([{name:'vivi_session',value:'vivi-preview',url}]);await page.goto(url+'/dashboard');assert.equal(await page.locator('a[href="/login"]').count(),0);assert.match(await page.locator('.account-menu').innerText(),/ZyVelia/);assert.equal(await page.locator('form[action="/logout"]').count(),1);assert.match(await page.locator('main').innerText(),/Velvet Ruins/);await page.goto(url+'/dashboard?guild=1');assert.equal((await page.request.post(url+'/feature',{form:{guild:'1',csrf:'bad',feature:'games',enabled:'true'}})).status(),403);
  await page.locator('[data-module-configure="welcome"]').click();assert.equal(await page.locator('#module-settings').getAttribute('open'),'');assert.equal(await page.locator('form[data-setting="welcome_text"]').isVisible(),true);assert.equal(await page.locator('form[data-setting="spam_limit"]').isVisible(),false);
  const welcome=page.locator('form[data-setting="welcome_text"]');await welcome.locator('textarea').fill('Welcome from browser');await welcome.locator('button').click();assert.equal(await page.locator('form[data-setting="welcome_text"] textarea').inputValue(),'Welcome from browser');
  const savedRevision=(await (await page.request.get(url+'/api/dashboard-state?guild=1')).json()).revision;
  await page.locator('form[data-setting="welcome_text"]').evaluate(el=>{el.closest('details').open=true;});await page.locator('form[data-setting="welcome_text"] textarea').fill('Unsaved draft');
  await page.request.post(url+'/setting',{form:{csrf:'preview-only-csrf',guild:'1',name:'welcome_text',value:'Changed elsewhere'}});
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.waitForFunction(()=>document.querySelector('.sync-status').textContent.includes('unsaved edits'));assert.equal(await page.locator('form[data-setting="welcome_text"] textarea').inputValue(),'Unsaved draft');
  assert.notEqual((await (await page.request.get(url+'/api/dashboard-state?guild=1')).json()).revision,savedRevision);
  page.once('dialog',dialog=>dialog.accept());await page.locator('.sync-status button').click();await page.waitForLoadState('networkidle');assert.equal(await page.locator('form[data-setting="welcome_text"] textarea').inputValue(),'Changed elsewhere');
  await page.request.post(url+'/setting',{form:{csrf:'preview-only-csrf',guild:'1',name:'welcome_text',value:'Automatic refresh'}});await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.waitForFunction(()=>document.querySelector('form[data-setting="welcome_text"] textarea')?.value==='Automatic refresh');
  const form=page.locator('form[action="/feature"]').first();await form.evaluate(el=>{let parent=el.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}});const before=await form.innerText();await form.locator('button').click();assert.notEqual(await page.locator('form[action="/feature"]').first().innerText(),before);
  await page.locator('form[action="/feature"]').first().evaluate(el=>{for(let x=el.parentElement;x;x=x.parentElement)if(x.tagName==='DETAILS')x.open=true;});await page.screenshot({path:path.join(root,'docs/assets/website-dashboard.png')});
  await page.goto(url+'/');assert.equal(await page.locator('a[href="/login"]').count(),0);
  await page.setViewportSize({width:390,height:844});await page.goto(url);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.locator('#menu-toggle').click();assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'),'false');await page.screenshot({path:path.join(root,'docs/assets/website-mobile.png')});
  await page.locator('.account-menu summary').click();await page.locator('.account-menu button').click();assert.equal(await page.locator('.account-menu').count(),0);assert.equal(await page.locator('a[href="/login"]').count(),1);assert.equal((await page.request.get(url+'/api/dashboard-state?guild=1')).status(),401);
  // Expected HTTP 403/404/503 responses above are checked separately; page navigation must have no script/CSP errors.
  assert.equal(errors.filter(e=>!e.includes('Failed to load resource')).length,0,errors.join('\n'));
  console.log('Website browser checks passed: public pages, real command search, invite, assets, permission checks, settings changes and mobile navigation.');
 }finally{if(browser)await browser.close();child.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
