"""Module-specific dashboard controls, using the same validated server options."""
import html
import json
import re
from types import SimpleNamespace
import discord
from aiohttp import web,ClientError
from vivi.core.features import FEATURES,OPTION_TYPES,enabled
from vivi.core.settings import DEFAULTS,validate_resources
from vivi.site.module_manager import title,DESCRIPTIONS,GROUPS,group_for,FAMILIES,family_for,family_navigation
from vivi.site import embed_writer
from vivi.site.website import asset_stamp
from vivi.site.message_templates import expand,message_embed,validate_appearance

E=lambda value:html.escape(str(value),quote=True)
PREFIXES={
 'welcome':('welcome_',),'welcome_cards':('welcome_',),'goodbye':('goodbye_',),'autorole':('autorole',),'rules':('rules_',),
 'automod':('spam_','blocked_'),'moderation':('dm_explanations',),'mention_protection':('mention_',),'raid_protection':('raid_',),'warning_thresholds':('warning_',),
 'scam_images':('scam_',),'staff_reviews':('review',),'birthdays':('birthday_','timezone'),'daily_questions':('daily_','timezone'),
 'ai':('ai_',),'voice_rooms':('voice_',),'lfg':('lfg_',),'scheduled_backups':('backup_',),'translation':('language',)}
TOOLS={
 'welcome_cards':[('Welcome-card layout editor','/configure?guild={gid}&module=welcome_cards')],
 'tickets':[('Ticket categories and staff setup','/dashboard?guild={gid}&module=tickets#module-settings')],
 'ticket_tools':[('Ticket categories and staff setup','/dashboard?guild={gid}&module=ticket_tools#module-settings')],
 'notifications':[('Subscriptions and destinations','/dashboard?guild={gid}&module=notifications#module-settings')],
 'instant_webhooks':[('Notification filters and subscriptions','/dashboard?guild={gid}&module=instant_webhooks#module-settings')],
 'custom_aliases':[('Custom command aliases','/dashboard?guild={gid}&module=custom_aliases#module-settings')],
 'xp':[('Per-channel XP settings','/dashboard?guild={gid}&module=xp#module-settings')],
 'scam_images':[('Reference image manager','/dashboard?guild={gid}&module=scam_images#module-settings')],
 'global_bans':[('Owner participation and consent','/modules?guild={gid}#module-global_bans')]}

class FeatureDashboard:
    def feature_routes(self):return [web.get('/configure',self.configure_module),web.post('/messages',self.save_messages)]
    def feature_page(self,gid,feature,content):
        content=f'<p><a href="/staff?guild={gid}">Staff home · cases · reports · tickets →</a></p>'+content
        response=self.page(content)
        response.text=response.text.replace('<nav data-dashboard-sections aria-label="Server modules"></nav>','<nav data-dashboard-sections aria-label="Server modules">'+family_navigation(gid,family_for(feature))+'</nav>')
        return response
    def related_editors(self,gid,session,feature):
        def panel(markup,heading):
            marker='<details><summary>'+heading+'</summary>'
            if marker not in markup:return ''
            return '<details open><summary>'+heading+'</summary>'+markup.split(marker,1)[1].split('</details>',1)[0]+'</details>'
        result=''
        if feature=='welcome':
            markup=self.studio_forms(gid,session)
            result=markup.split('<h2>Welcome-card layout editor</h2>',1)[1].split('<h2>Announcement builder</h2>',1)[0]
        if feature=='xp':result+=panel(self.advanced_forms(gid,session),'Per-channel XP')
        if feature in {'tickets','ticket_tools'}:
            markup=self.settings_forms(gid,session)
            result+=panel(markup,'Server channels and support staff')+panel(markup,'Ticket categories and open tickets')
        if feature in {'notifications','instant_webhooks'}:
            result+=panel(self.settings_forms(gid,session),'Twitch, YouTube and GitHub notifications')+panel(self.advanced_forms(gid,session),'Notification filters')
        if feature=='custom_aliases':result+=panel(self.tools_forms(gid,session),'Custom command aliases')
        if feature=='scheduled_backups':result+=panel(self.tools_forms(gid,session),'Scheduled backups')
        return re.sub(r'<form\b[^>]*>',lambda m:m[0]+f'<input type="hidden" name="return_module" value="{feature}">',result)
    async def configure_module(self,request):
        try:gid=int(request.query.get('guild',''))
        except ValueError:raise web.HTTPBadRequest(text='Choose a server.')
        feature=request.query.get('module','')
        if feature=='welcome_cards':
            await self.authorize(request,gid)
            raise web.HTTPSeeOther(f'/configure?guild={gid}&module=welcome#welcome-card-design')
        if feature not in FEATURES or feature=='faq':raise web.HTTPNotFound(text='Unknown module.')
        session=await self.authorize(request,gid);guild=self.service.bot.get_guild(gid);store=self.service.store
        content=f'<a href="/modules?guild={gid}">← All modules</a><div class="modules-intro"><div><span class="eyebrow">Customize your server</span><h2>{E(title(feature))}</h2><p>{E(DESCRIPTIONS.get(feature,""))}</p></div><a class="btn btn-ghost" href="/embeds?guild={gid}">Embed writer →</a></div>'
        family=FAMILIES[family_for(feature)]
        content+='<nav class="related-modules" aria-label="Related settings"><strong>'+E(family[0])+'</strong>'+''.join(f'<a href="/configure?guild={gid}&module={key}"'+(' aria-current="page"' if key==feature else '')+f'>{E(title(key))}</a>' for key in family[1])+'</nav>'
        content+=f'<div data-dashboard-sync data-guild="{gid}" data-revision="{self.config_revision(gid)}"><p class="sync-status" role="status">Settings shared with Discord. Checking for updates automatically.</p></div>'
        if request.query.get('saved')=='yes':content+='<p role="status">Settings saved. New events use these settings immediately.</p>'
        if feature in {'welcome','goodbye'}:
            content+=self.message_composer(gid,session,feature)
            if feature=='welcome':content+='<section id="welcome-card-design"><h3>Welcome card design</h3><p>Cards are part of Welcome. Enable them with Add a welcome card above; turning Welcome off pauses both messages and cards.</p>'+self.related_editors(gid,session,feature)+'</section>'
            return self.feature_page(gid,feature,content)
        on=enabled(store,gid,feature)
        if feature!='global_bans':content+='<form action="/feature" method="post">'+self.hidden(session,gid)+f'<input type="hidden" name="feature" value="{feature}"><input type="hidden" name="enabled" value="{str(not on).lower()}"><input type="hidden" name="return" value="configure"><p>Feature is <strong>{"enabled" if on else "disabled"}</strong>.</p><button>{"Disable" if on else "Enable"} {E(title(feature))}</button></form>'
        keys=[] if feature=='welcome_cards' else [key for key in OPTION_TYPES if any(key.startswith(prefix) for prefix in PREFIXES.get(feature,())) and OPTION_TYPES[key] is not dict]
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
        editors=self.related_editors(gid,session,feature);content+=editors
        for label,url in ([] if editors else TOOLS.get(feature,[])):content+=f'<p><a class="btn btn-ghost" href="{E(url.format(gid=gid))}">{E(label)} →</a></p>'
        if not keys and feature not in TOOLS:content+='<p>This module has no additional server-wide settings. Its individual items and member preferences are managed through its Discord menu.</p>'
        content+=f'<p><a href="/commands?search={E(feature)}">Related Discord commands</a> · <a href="/dashboard?guild={gid}">All server settings</a></p>'
        return self.feature_page(gid,feature,content)

    def message_composer(self,gid,session,kind):
        store=self.service.store;guild=self.service.bot.get_guild(gid);configuration=store.settings(gid)
        channel=store.option(gid,kind+'_channel',configuration['welcome'] if kind=='welcome' and configuration else 0)
        mode=store.option(gid,kind+'_mode','text');text=store.option(gid,kind+'_text',DEFAULTS[kind+'_text']);snapshot=store.option(gid,kind+'_embed',{})
        avatar=session.get('profile',{}).get('avatar','');uid=str(session.get('user_id',''))
        member_avatar=f'https://cdn.discordapp.com/avatars/{uid}/{avatar}.png?size=256' if re.fullmatch(r'[0-9]{1,20}',uid) and re.fullmatch(r'(?:a_)?[a-f0-9]{32}',avatar) else 'https://cdn.discordapp.com/embed/avatars/0.png'
        documents={row['id']:row['data']['document'] for row in store.records(gid,embed_writer.KIND)};documents['']=snapshot
        result='<div class="message-workspace message-designer"><form action="/messages" method="post" id="message-composer">'+self.hidden(session,gid)+f'<input type="hidden" name="kind" value="{kind}">'
        result+=f'<header class="composer-header"><div><span class="eyebrow">Make an entrance</span><h3>{kind.title()} message</h3><span id="message-draft-state">No unsaved changes</span><p>Write it once. Make every {"hello" if kind=="welcome" else "goodbye"} feel personal.</p></div><label class="composer-switch"><input type="checkbox" name="enabled" value="yes"'+(' checked' if enabled(store,gid,kind) else '')+'><span>Automatic messages</span></label></header>'
        result+='<section class="composer-section"><label>Post in channel '+self.select('channel',[(0,'Choose a channel')]+[(c.id,'#'+c.name) for c in guild.text_channels],channel)+'</label><p class="field-hint">Used for automatic messages and anything you send from this editor.</p></section>'
        result+='<fieldset class="message-format"><legend>Message format</legend>'
        for value,label,hint in [('text','Text message','Simple, with optional welcome card'),('embed','Embed message','Styled titles, fields and images')]:
            result+=f'<label><input type="radio" name="mode" value="{value}"'+(' checked' if mode==value else '')+f'><span><strong>{label}</strong><small>{hint}</small></span></label>'
        result+='</fieldset><section class="composer-section" data-message-mode="text"'+(' hidden' if mode!='text' else '')+f'><div class="field-heading"><label for="welcome-message-text">Your message</label><span id="message-character-count">{len(text)} / 1,800</span></div><textarea id="welcome-message-text" name="text" rows="6" maxlength="1800" placeholder="Welcome {{member}} to {{server}}!">{E(text)}</textarea><div class="placeholder-chips"><span>Insert:</span>'
        for token,label in [('member','@Member'),('username','Username'),('server','Server'),('member_count','Member count')]:result+=f'<button type="button" data-insert-token="{token}" title="Insert {{{token}}}">{label}</button>'
        result+='</div><p class="field-hint">Click a chip to insert a placeholder at your cursor.</p>'

        result+='</section><section class="composer-section" data-message-mode="embed"'+(' hidden' if mode!='embed' else '')+'><label>Choose your embed '+self.select('template',[('',f'Current: {snapshot["name"]}' if snapshot else 'Choose a saved embed')]+[(ident,doc['name']) for ident,doc in documents.items() if ident], '')+'</label>'
        result+=f'<p class="field-hint">Pick a template from your shared library, or <a href="/embeds?guild={gid}" target="_blank" rel="noopener">create an embed →</a>.</p><button type="button" id="message-refresh-embeds">Refresh library</button><p id="embed-choice-status" role="status"></p><details class="embed-copy-note"><summary>How saved templates work</summary><p>A copy is saved with this message. After editing the library template, select it again here to apply its latest version.</p></details></section>'
        if kind=='welcome':result+='<section class="composer-section"><div class="welcome-card-option"><label><input type="checkbox" name="cards" value="yes"'+(' checked' if enabled(store,gid,'welcome_cards') else '')+f'><span>Add a welcome card<small>A personalized image alongside your message.</small></span></label><a href="#welcome-card-design">Design card →</a></div><p class="field-hint">Works with either text or embeds. The Welcome switch controls both.</p></section>'
        appearance=store.option(gid,kind+'_appearance',{})
        result+='<section class="composer-section" data-message-mode="embed"><h3>Personalize your embed</h3><p class="field-hint">Use the joining member’s profile picture or your server icon. Missing server icons are omitted.</p>'
        for key,label in [('thumbnail','Corner thumbnail'),('image','Large image')]:
            result+='<label>'+label+' '+self.select('appearance_'+key,[('template','Keep template image'),('member','Member profile picture'),('server','Server icon'),('none','No image')],appearance.get(key,'template'))+'</label>'
        result+='<label><input type="checkbox" name="custom_color" value="yes"'+(' checked' if appearance.get('color') else '')+'> Custom accent color</label><label>Accent color <input type="color" name="accent_color" value="'+E(appearance.get('color') or '#ff65ad')+'"></label><p class="field-hint">Turn custom color off to keep the template’s color. Welcome cards have their own Design card editor below.</p></section>'
        result+=f'<div id="message-preview-data" hidden data-documents="{E(json.dumps(documents))}" data-server="{E(guild.name)}" data-count="{E(getattr(guild,"member_count",0) or 0)}" data-member-avatar="{E(member_avatar)}" data-server-icon="{E(str(guild.icon.url) if getattr(guild,"icon",None) else "")}"></div>'
        result+='<footer class="composer-actions"><div><button name="action" value="save">Save settings</button><button type="button" id="message-send">Send to Discord →</button><button class="composer-preview-button" name="action" value="preview">Expanded preview</button></div><p>Save updates future automatic messages. Send posts your current draft once.</p><p id="message-send-status" role="status" aria-live="polite"></p></footer></form>'
        result+='<aside class="message-preview-panel"><div class="preview-heading"><h3>Live preview</h3><span class="preview-badge">LIVE</span></div><p class="preview-channel" id="message-preview-channel"></p><div class="discord-preview-shell"><div class="preview-author"><img src="/assets/vivi-avatar.png" alt="" width="36" height="36"><strong>Vivi</strong><span>APP</span><small>Sample message</small></div><article class="embed-preview" id="message-live-preview" aria-live="polite"></article></div><p class="field-hint">Preview uses a sample member. Sending uses your Discord profile, without pinging anyone.</p><details class="message-help"><summary>Before you turn it on</summary><p>Vivi needs View Channel and Send Messages, plus Embed Links for embeds or Attach Files for cards. You can save a draft while automatic messages are off.</p></details></aside></div>'
        result+='<dialog id="confirm-message-send" aria-labelledby="confirm-message-title"><span class="eyebrow">One message, right now</span><h2 id="confirm-message-title">Send to Discord?</h2><p id="confirm-message-destination"></p><p>The member placeholders will use your profile. This will not save your settings or enable automatic messages.</p><div class="send-dialog-actions"><button type="button" id="confirm-message-cancel">Cancel</button><button type="button" id="confirm-message-submit">Confirm send</button></div></dialog><script src="/assets/message-preview.js?v='+asset_stamp("message-preview.js")+'" defer></script>'
        return result

    async def save_messages(self,request):
        data,session,gid,guild=await self.form(request);kind=data.get('kind');store=self.service.store
        if kind not in {'welcome','goodbye'}:raise web.HTTPBadRequest(text='Invalid message type.')
        try:
            mode=data.get('mode');text=str(data.get('text',''));channel_id=int(data.get('channel',0));on=data.get('enabled')=='yes';cards=kind=='welcome' and data.get('cards')=='yes'
            appearance=validate_appearance(dict(color=str(data.get('accent_color','#ff65ad')) if data.get('custom_color')=='yes' else '',thumbnail=str(data.get('appearance_thumbnail','template')),image=str(data.get('appearance_image','template'))))
            validate_resources(store,guild,kind+'_channel',channel_id);validate_resources(store,guild,kind+'_mode',mode);validate_resources(store,guild,kind+'_text',text)
            snapshot=embed_writer.load(store,gid,str(data['template']))['data']['document'] if data.get('template') else store.option(gid,kind+'_embed',{})
            if mode=='embed' and not snapshot:raise ValueError('Choose a saved embed first.')
            if snapshot:embed_writer.validate(snapshot)
            if mode=='text' and not text.strip():raise ValueError('Write a message first.')
            if data.get('action')=='preview':
                sample=SimpleNamespace(display_name='Sample member',mention='@Sample member',display_avatar=SimpleNamespace(url='https://cdn.discordapp.com/embed/avatars/0.png'),guild=guild)
                if mode=='embed':
                    embed=message_embed(snapshot,sample,appearance);body=f'<article class="embed-preview" style="border-color:{E(str(embed.color))}"><h3>{E(embed.title or "")}</h3><p>{E(embed.description or "")}</p>'+''.join(f'<h4>{E(f.name)}</h4><p>{E(f.value)}</p>' for f in embed.fields)+f'<small>{E(embed.footer.text or "")}</small></article><p>Text preview; Discord renders markdown and images when sent.</p>'
                else:body=f'<article class="embed-preview"><p>{E(expand(text,sample))}</p></article>'
                return self.page('<h2>Message preview</h2><p>Nothing was saved or sent.</p>'+body+f'<p><a href="/configure?guild={gid}&module={kind}">Back to saved settings</a> · Use your browser’s Back button to keep this draft.</p>')
            if data.get('action')=='send':return await self.send_draft_message(request,data,session,gid,guild,kind,mode,text,snapshot,cards,channel_id,appearance)
            if data.get('action')!='save':raise ValueError('Unknown action.')
            channel=guild.get_channel(channel_id)
            if on:
                if not channel:raise ValueError('Choose a destination channel before enabling.')
                permissions=channel.permissions_for(guild.me)
                if not permissions.view_channel or not permissions.send_messages:raise ValueError('Vivi needs View Channel and Send Messages in this channel.')
                if mode=='embed' and not permissions.embed_links:raise ValueError('Vivi needs Embed Links in this channel.')
                if cards and not permissions.attach_files:raise ValueError('Vivi needs Attach Files for welcome cards.')
            values={kind+'_channel':channel_id,kind+'_mode':mode,kind+'_text':text,kind+'_embed':snapshot,kind+'_appearance':appearance,'feature:'+kind:on}
            if kind=='welcome':values['feature:welcome_cards']=cards
            # Validate everything before one transaction and one history entry.
            before=store.export_config(gid)
            with store.db:
                store.db.executemany('INSERT OR REPLACE INTO options VALUES (?,?,?)',[(gid,k,json.dumps(v)) for k,v in values.items()])
                if kind=='welcome' and channel_id:store.db.execute('UPDATE settings SET welcome=? WHERE guild=?',(channel_id,gid))
                store.log_config(gid,kind+' message composer',before)
        except (ValueError,TypeError) as error:raise web.HTTPBadRequest(text=str(error))
        raise web.HTTPSeeOther(f'/configure?guild={gid}&module={kind}&saved=yes')

    async def send_draft_message(self,request,data,session,gid,guild,kind,mode,text,snapshot,cards,channel_id,appearance):
        if data.get('confirm_send')!='yes':raise ValueError('Confirm the destination before sending.')
        channel=guild.get_channel(channel_id)
        if not isinstance(channel,discord.TextChannel):raise ValueError('Choose a destination text channel in this server.')
        try:
            member=await guild.fetch_member(session['user_id'])
            if not member.guild_permissions.administrator and member.id!=guild.owner_id:raise web.HTTPForbidden(text='Administrator permission is required to send messages.')
            permissions=channel.permissions_for(guild.me)
            if not permissions.view_channel or not permissions.send_messages:raise ValueError('Vivi needs View Channel and Send Messages in this channel.')
            if mode=='embed' and not permissions.embed_links:raise ValueError('Vivi needs Embed Links in this channel.')
            if cards and not permissions.attach_files:raise ValueError('Vivi needs Attach Files for welcome cards.')
            from vivi.site.message_templates import cut
            options=dict(allowed_mentions=discord.AllowedMentions.none())
            if mode=='embed':options['embed']=message_embed(snapshot,member,appearance)
            else:
                options['content']=cut(expand(text,member,mention=True),2000)
            if cards:
                import asyncio,io
                from vivi.site.studio_layout import render_layout,DEFAULT_LAYOUT
                avatar=await member.display_avatar.with_size(256).with_format('png').read()
                layout=self.service.store.option(gid,'welcome_layout',DEFAULT_LAYOUT)
                try:image=await asyncio.to_thread(render_layout,layout,member.display_name,guild.name,expand(text,member),avatar,None,self.service.store.option(gid,'branding',{}).get('name','Vivi'))
                except (OSError,ValueError):raise web.HTTPBadGateway(text='The welcome card could not be generated. No message was sent.') from None
                options['file']=discord.File(io.BytesIO(image),filename='vivi-welcome.png')
            try:message=await channel.send(**options)
            finally:
                if options.get('file'):
                    options['file'].close();options['file'].fp.close()
        except discord.Forbidden:raise web.HTTPForbidden(text='Discord refused the send. Check Vivi’s permissions in this channel.') from None
        except (discord.HTTPException,ClientError,OSError):raise web.HTTPBadGateway(text='Could not confirm the send. Check the channel before trying again.') from None
        if 'application/json' in request.headers.get('Accept',''):return web.json_response(dict(sent=True,url=message.jump_url))
        return self.page(f'<h2>Message sent</h2><p>Your {kind} draft was posted. Settings were not changed.</p><a href="{E(message.jump_url)}">View message</a><p><a href="/configure?guild={gid}&module={kind}">Back to editor</a></p>')
