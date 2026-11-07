"""Module-specific dashboard controls, using the same validated server options."""
import html
import json
from types import SimpleNamespace
import discord
from aiohttp import web
from .features import FEATURES,OPTION_TYPES,enabled
from .settings import DEFAULTS,validate_resources
from .module_manager import title,DESCRIPTIONS,GROUPS,group_for
from . import embed_writer
from .message_templates import expand,message_embed

E=lambda value:html.escape(str(value),quote=True)
PREFIXES={
 'welcome':('welcome_',),'welcome_cards':('welcome_',),'goodbye':('goodbye_',),'autorole':('autorole',),'rules':('rules_',),
 'automod':('spam_','blocked_'),'moderation':('dm_explanations',),'mention_protection':('mention_',),'raid_protection':('raid_',),'warning_thresholds':('warning_',),
 'scam_images':('scam_',),'staff_reviews':('review',),'birthdays':('birthday_','timezone'),'daily_questions':('daily_','timezone'),
 'ai':('ai_',),'voice_rooms':('voice_',),'lfg':('lfg_',),'scheduled_backups':('backup_',),'translation':('language',)}
TOOLS={
 'welcome_cards':[('Welcome-card layout editor','/dashboard?guild={gid}&module=welcome_cards#module-settings')],
 'tickets':[('Ticket categories and staff setup','/dashboard?guild={gid}&module=tickets#module-settings')],
 'ticket_tools':[('Ticket categories and staff setup','/dashboard?guild={gid}&module=ticket_tools#module-settings')],
 'notifications':[('Subscriptions and destinations','/dashboard?guild={gid}&module=notifications#module-settings')],
 'instant_webhooks':[('Notification filters and subscriptions','/dashboard?guild={gid}&module=instant_webhooks#module-settings')],
 'custom_aliases':[('Custom command aliases','/dashboard?guild={gid}&module=custom_aliases#module-settings')],
 'xp':[('Per-channel XP settings','/dashboard?guild={gid}&module=xp#module-settings')],
 'profiles':[('Dashboard branding and themes','/dashboard?guild={gid}#dashboard-panels')],
 'scam_images':[('Reference image manager','/dashboard?guild={gid}&module=scam_images#module-settings')],
 'global_bans':[('Owner participation and consent','/modules?guild={gid}#module-global_bans')]}

class FeatureDashboard:
    def feature_routes(self):return [web.get('/configure',self.configure_module),web.post('/messages',self.save_messages)]
    def feature_page(self,gid,feature,content):
        response=self.page(content);navigation=''
        for group,features in GROUPS.items():
            links=''.join(f'<a href="/configure?guild={gid}&module={key}"'+(' aria-current="page"' if key==feature else '')+f'>{E(title(key))}</a>' for key in sorted(features) if key in FEATURES)
            navigation+='<details'+(' open' if group_for(feature)==group else '')+f'><summary>{E(group)}</summary>{links}</details>'
        response.text=response.text.replace('<nav data-dashboard-sections aria-label="Server modules"></nav>','<nav data-dashboard-sections aria-label="Server modules">'+navigation+'</nav>')
        return response
    async def configure_module(self,request):
        try:gid=int(request.query.get('guild',''))
        except ValueError:raise web.HTTPBadRequest(text='Choose a server.')
        feature=request.query.get('module','')
        if feature not in FEATURES or feature=='faq':raise web.HTTPNotFound(text='Unknown module.')
        session=await self.authorize(request,gid);guild=self.service.bot.get_guild(gid);store=self.service.store
        content=f'<a href="/modules?guild={gid}">← All modules</a><div class="modules-intro"><div><span class="eyebrow">Customize your server</span><h2>{E(title(feature))}</h2><p>{E(DESCRIPTIONS.get(feature,""))}</p></div><a class="btn btn-ghost" href="/embeds?guild={gid}">Embed writer →</a></div>'
        content+=f'<div data-dashboard-sync data-guild="{gid}" data-revision="{self.config_revision(gid)}"><p class="sync-status" role="status">Settings shared with Discord. Checking for updates automatically.</p></div>'
        if request.query.get('saved')=='yes':content+='<p role="status">Settings saved. New events use these settings immediately.</p>'
        if feature in {'welcome','goodbye'}:return self.feature_page(gid,feature,content+self.message_composer(gid,session,feature))
        on=enabled(store,gid,feature)
        if feature!='global_bans':content+='<form action="/feature" method="post">'+self.hidden(session,gid)+f'<input type="hidden" name="feature" value="{feature}"><input type="hidden" name="enabled" value="{str(not on).lower()}"><input type="hidden" name="return" value="configure"><p>Feature is <strong>{"enabled" if on else "disabled"}</strong>.</p><button>{"Disable" if on else "Enable"} {E(title(feature))}</button></form>'
        keys=[key for key in OPTION_TYPES if any(key.startswith(prefix) for prefix in PREFIXES.get(feature,())) and OPTION_TYPES[key] is not dict]
        content+='<div class="feature-settings-grid">'
        for key in keys:
            typ=OPTION_TYPES[key];value=store.option(gid,key,DEFAULTS.get(key,[] if typ is list else False if typ is bool else 0 if typ is int else ''))
            content+=f'<form action="/setting" method="post" data-setting="{key}">'+self.hidden(session,gid)+f'<input type="hidden" name="name" value="{key}"><input type="hidden" name="module" value="{feature}"><label for="setting-{key}">{E(key.replace("_"," ").title())}</label>'
            if key.endswith('_channel') or key in {'voice_lobby','voice_category','autorole','rules_role','reviewer_role'}:
                resources=guild.roles if key in {'autorole','rules_role','reviewer_role'} else guild.categories if key=='voice_category' else guild.voice_channels if key=='voice_lobby' else guild.text_channels
                options=[(0,'Not set')]+[(r.id,r.name) for r in resources]
                control=self.select('value',options,value)
            elif key=='ai_channels':control='<select name="values" multiple>'+''.join(f'<option value="{c.id}"'+(' selected' if c.id in value else '')+f'>{E(c.name)}</option>' for c in guild.text_channels)+'</select>'
            elif typ is bool:control=self.select('value',[('true','On'),('false','Off')],str(value).lower())
            elif key=='language':control=self.select('value',[('en','English'),('es','Español'),('fr','Français')],value)
            elif key=='raid_action':control=self.select('value',[('alert','Alert and pause roles'),('lockdown','Lockdown selected channel')],value)
            elif typ is int:control=f'<input name="value" type="number" value="{E(value)}">'
            else:control=f'<textarea name="value" rows="4">{E(", ".join(map(str,value)) if typ is list else value)}</textarea>'
            # Labels remain associated for every generated control.
            control=control.replace('name="value"',f'id="setting-{key}" name="value"',1).replace('name="values"',f'id="setting-{key}" name="values"',1)
            content+=control+('<small>Comma-separated entries.</small>' if typ is list and key!='ai_channels' else '')+'<button>Save setting</button></form>'
        content+='</div>'
        for label,url in TOOLS.get(feature,[]):content+=f'<p><a class="btn btn-ghost" href="{E(url.format(gid=gid))}">{E(label)} →</a></p>'
        if not keys and feature not in TOOLS:content+='<p>This module has no additional server-wide settings. Its individual items and member preferences are managed through its Discord menu.</p>'
        content+=f'<p><a href="/commands?search={E(feature)}">Related Discord commands</a> · <a href="/dashboard?guild={gid}">All server settings</a></p>'
        return self.feature_page(gid,feature,content)

    def message_composer(self,gid,session,kind):
        store=self.service.store;guild=self.service.bot.get_guild(gid);configuration=store.settings(gid)
        channel=store.option(gid,kind+'_channel',configuration['welcome'] if kind=='welcome' and configuration else 0)
        mode=store.option(gid,kind+'_mode','text');text=store.option(gid,kind+'_text',DEFAULTS[kind+'_text']);snapshot=store.option(gid,kind+'_embed',{})
        result='<div class="message-workspace"><form action="/messages" method="post" id="message-composer">'+self.hidden(session,gid)+f'<input type="hidden" name="kind" value="{kind}"><label><input type="checkbox" name="enabled" value="yes"'+(' checked' if enabled(store,gid,kind) else '')+f'> Enable {kind} messages</label><label>Destination channel '+self.select('channel',[(0,'Not set')]+[(c.id,'#'+c.name) for c in guild.text_channels],channel)+'</label><label>Message style '+self.select('mode',[('text','Text message'),('embed','Embed message')],mode)+'</label>'+f'<label>Message text<textarea name="text" rows="8" maxlength="1800">{E(text)}</textarea></label><p>Placeholders: <code>{{member}}</code>, <code>{{username}}</code>, <code>{{server}}</code>, <code>{{member_count}}</code>. Text welcomes can mention the joining member. Embeds and goodbye messages do not ping.</p>'
        options=[('','Keep current configured embed' if snapshot else 'Choose a saved embed')]+[(row['id'],row['data']['document']['name']) for row in store.records(gid,embed_writer.KIND)]
        result+='<label>Saved embed '+self.select('template',options)+'</label><p>Choosing a template copies it into these settings. Edit it in the embed writer, then select it here again to apply updates. Deleting the library template will not break messages.</p>'+f'<p><a href="/embeds?guild={gid}">Create or edit an embed →</a></p>'
        if kind=='welcome':result+='<label><input type="checkbox" name="cards" value="yes"'+(' checked' if enabled(store,gid,'welcome_cards') else '')+f'> Add a welcome card to text messages</label><p><a href="/dashboard?guild={gid}&module=welcome_cards#module-settings">Customize welcome-card layout →</a></p>'
        result+='<button name="action" value="preview">Preview without saving</button><button name="action" value="save">Save message settings</button></form><aside class="message-help"><h3>How it works</h3><p>Choose a channel, write your text or choose an embed, and save. Changes apply to future joins or departures. Existing messages stay unchanged.</p><p>Vivi needs View Channel and Send Messages, plus Embed Links for embeds or Attach Files for cards. You can save drafts while disabled.</p></aside></div>'
        return result

    async def save_messages(self,request):
        data,session,gid,guild=await self.form(request);kind=data.get('kind');store=self.service.store
        if kind not in {'welcome','goodbye'}:raise web.HTTPBadRequest(text='Invalid message type.')
        try:
            mode=data.get('mode');text=str(data.get('text',''));channel_id=int(data.get('channel',0));on=data.get('enabled')=='yes';cards=kind=='welcome' and data.get('cards')=='yes'
            validate_resources(store,guild,kind+'_channel',channel_id);validate_resources(store,guild,kind+'_mode',mode);validate_resources(store,guild,kind+'_text',text)
            snapshot=embed_writer.load(store,gid,str(data['template']))['data']['document'] if data.get('template') else store.option(gid,kind+'_embed',{})
            if mode=='embed' and not snapshot:raise ValueError('Choose a saved embed first.')
            if snapshot:embed_writer.validate(snapshot)
            if mode=='text' and not text.strip():raise ValueError('Write a message first.')
            if data.get('action')=='preview':
                sample=SimpleNamespace(display_name='Sample member',mention='@Sample member',guild=SimpleNamespace(name=guild.name,member_count=getattr(guild,'member_count',0)))
                if mode=='embed':
                    embed=message_embed(snapshot,sample);body=f'<article class="embed-preview" style="border-color:{E(snapshot["color"])}"><h3>{E(embed.title or "")}</h3><p>{E(embed.description or "")}</p>'+''.join(f'<h4>{E(f.name)}</h4><p>{E(f.value)}</p>' for f in embed.fields)+f'<small>{E(embed.footer.text or "")}</small></article><p>Text preview; Discord renders markdown and images when sent.</p>'
                else:body=f'<article class="embed-preview"><p>{E(expand(text,sample))}</p></article>'
                return self.page('<h2>Message preview</h2><p>Nothing was saved or sent.</p>'+body+f'<p><a href="/configure?guild={gid}&module={kind}">Back to saved settings</a> · Use your browser’s Back button to keep this draft.</p>')
            if data.get('action')!='save':raise ValueError('Unknown action.')
            channel=guild.get_channel(channel_id)
            if on:
                if not channel:raise ValueError('Choose a destination channel before enabling.')
                permissions=channel.permissions_for(guild.me)
                if not permissions.view_channel or not permissions.send_messages:raise ValueError('Vivi needs View Channel and Send Messages in this channel.')
                if mode=='embed' and not permissions.embed_links:raise ValueError('Vivi needs Embed Links in this channel.')
                if mode=='text' and cards and not permissions.attach_files:raise ValueError('Vivi needs Attach Files for welcome cards.')
            values={kind+'_channel':channel_id,kind+'_mode':mode,kind+'_text':text,kind+'_embed':snapshot,'feature:'+kind:on}
            if kind=='welcome':values['feature:welcome_cards']=cards
            # Validate everything before one transaction and one history entry.
            before=store.export_config(gid)
            with store.db:
                store.db.executemany('INSERT OR REPLACE INTO options VALUES (?,?,?)',[(gid,k,json.dumps(v)) for k,v in values.items()])
                if kind=='welcome' and channel_id:store.db.execute('UPDATE settings SET welcome=? WHERE guild=?',(channel_id,gid))
                store.log_config(gid,kind+' message composer',before)
        except (ValueError,TypeError) as error:raise web.HTTPBadRequest(text=str(error))
        raise web.HTTPSeeOther(f'/configure?guild={gid}&module={kind}&saved=yes')
