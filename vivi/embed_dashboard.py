"""Authenticated named embed library and visual editor."""
import html
import json
from pathlib import Path
from urllib.parse import urlencode
import discord
from aiohttp import web
from . import embed_writer as writer

E=lambda value:html.escape(str(value),quote=True)
class EmbedDashboard:
    def embed_routes(self):
        return [web.get('/embeds',self.embed_editor),web.post('/embeds',self.embed_action),web.get('/assets/embed-writer.js',self.embed_script)]
    async def embed_script(self,request):return web.Response(text=(Path(__file__).parent/'web'/'embed-writer.js').read_text(),content_type='application/javascript')
    async def embed_editor(self,request):
        if not request.query.get('guild'):
            response=await self.index(request)
            response.text=response.text.replace('/modules?guild=','/embeds?guild=')
            return response
        try:gid=int(request.query['guild'])
        except ValueError:raise web.HTTPBadRequest(text='Invalid server ID.')
        session=await self.authorize(request,gid);guild=self.service.bot.get_guild(gid);store=self.service.store
        ident=request.query.get('id','');document=dict(name='',title='',description='',color='#ff65ad',fields=[])
        if ident:
            try:document=writer.load(store,gid,ident)['data']['document']
            except ValueError as error:raise web.HTTPNotFound(text=str(error))
        elif request.query.get('preset')=='rules':document.update(name='Server rules',title='Welcome to our community',description='Please read and follow these rules.\n\n**1. Be respectful**\nTreat everyone with kindness.\n\n**2. Keep it safe**\nNo scams, spam or harmful content.\n\n**3. Follow channel topics**\nUse the right channel and listen to staff.',footer='Thank you for keeping our community welcoming.')
        library=''.join(f'<li><a href="/embeds?{urlencode(dict(guild=gid,id=row["id"]))}">{E(row["data"]["document"]["name"])}</a></li>' for row in store.records(gid,writer.KIND))
        status=''
        if request.query.get('saved')=='yes':status='<p role="status">Template saved. It is available in /embed too.</p>'
        if request.query.get('posted')=='yes':status='<p role="status">Embed posted to Discord.</p>'
        content=f'<div class="embed-intro"><span class="eyebrow">Write once. Share when ready.</span><h2>Embed writer</h2><p>Save rules, announcements and useful messages for this server. Use Discord markdown in your text. Saving never posts a message.</p><a href="/dashboard?guild={gid}">← Server settings</a></div>{status}<div class="embed-workspace"><aside class="embed-library"><h3>Saved embeds</h3><a href="/embeds?guild={gid}">+ New embed</a> · <a href="/embeds?guild={gid}&preset=rules">Rules starter</a><ul>{library or "<li>No saved embeds yet.</li>"}</ul></aside><div><form method="post" action="/embeds" id="embed-writer">'+self.hidden(session,gid)+f'<input type="hidden" name="id" value="{E(ident)}">'
        for key,label,limit in [('name','Template name',80),('title','Embed title',256),('description','Message text (Discord markdown)',4096),('footer','Footer',2048),('url','Title link (HTTPS)',2048),('image','Image URL (HTTPS)',2048),('thumbnail','Thumbnail URL (HTTPS)',2048)]:
            value=E(document.get(key,''));content+=f'<label>{label}'+(f'<textarea name="{key}" maxlength="{limit}" rows="10">{value}</textarea>' if key=='description' else f'<input name="{key}" maxlength="{limit}" value="{value}"'+(' required' if key=='name' else '')+(' type="url"' if key in {'url','image','thumbnail'} else '')+'>')+'</label>'
        content+=f'<label>Accent color <input type="color" name="color" value="{E(document["color"])}"></label><input type="hidden" name="fields" value="{E(json.dumps(document.get("fields",[])))}"><h3>Fields</h3><div id="embed-fields"></div><button type="button" id="embed-add-field">Add field</button><p id="embed-count" role="status"></p><button name="action" value="save">Save template</button><button name="action" value="duplicate">Save as new copy</button><details><summary>Post to Discord</summary><p>This posts the current editor contents. Save separately to keep changes in your library.</p><label>Destination channel '+self.select('channel',[(c.id,'#'+c.name) for c in guild.text_channels])+'</label><label><input type="checkbox" name="confirm" value="yes"> I confirm posting this message to the selected channel</label><button name="action" value="publish">Post embed</button></details>'
        if ident:content+='<details><summary>Delete saved template</summary><p>Already posted Discord messages will stay.</p><label><input type="checkbox" name="delete_confirm" value="yes"> Delete this template from the library</label><button name="action" value="delete" formnovalidate>Delete template</button></details>'
        content+='</form></div><section class="embed-preview-panel"><h3>Live preview</h3><p>Text layout preview. Discord renders markdown and remote images when posted.</p><article id="embed-preview" class="embed-preview"><strong data-preview="title"></strong><p data-preview="description"></p><div data-preview="fields"></div><small data-preview="footer"></small></article></section></div><script src="/assets/embed-writer.js" defer></script>'
        return self.page(content)
    async def embed_action(self,request):
        data,session,gid,guild=await self.form(request);store=self.service.store;ident=str(data.get('id',''));action=data.get('action')
        try:
            if ident:writer.load(store,gid,ident)
            if action=='delete':
                if data.get('delete_confirm')!='yes':raise ValueError('Confirm deletion first.')
                if not ident:raise ValueError('Choose a saved template.')
                store.delete_record(ident);raise web.HTTPSeeOther(f'/embeds?guild={gid}')
            document={k:str(data.get(k,'')) for k in ('name','title','description','footer','color','url','image','thumbnail')}
            document['fields']=json.loads(str(data.get('fields','[]')));document=writer.validate(document)
            if action in {'save','duplicate'}:
                ident=writer.save(store,gid,document,session['user_id'],ident if action=='save' else '')
                raise web.HTTPSeeOther('/embeds?'+urlencode(dict(guild=gid,id=ident,saved='yes')))
            if action=='publish':
                if data.get('confirm')!='yes':raise ValueError('Confirm publication before posting.')
                await writer.publish(guild,int(data.get('channel',0)),document,session['user_id'])
                # Return to the editor with the exact posted content, without replacing a saved template.
                return self.page('<h2>Embed posted</h2><p>Your message was posted. Posting does not save changes to the library.</p>'+f'<a href="/embeds?{urlencode(dict(guild=gid,id=ident))}">Back to embed writer</a>')
            raise ValueError('Unknown embed action.')
        except PermissionError as error:raise web.HTTPForbidden(text=str(error))
        except (ValueError,TypeError) as error:raise web.HTTPBadRequest(text=str(error))
        except discord.HTTPException:raise web.HTTPBadGateway(text='Discord could not post this embed. Check channel permissions and try again.')
