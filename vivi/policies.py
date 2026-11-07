"""Public policy copy and contact details for the ZyVelia-operated Vivi service."""
from html import escape

OPERATOR='ZyVelia'
OPERATOR_LOCATION='Massachusetts, United States'
EMAIL='Vivi-Roseveil@proton.me'
SUPPORT_SERVER='https://discord.gg/MWEJm7yJ4x'
UPDATED='November 7, 2026'


def contact_html():
    return (f'<section class="help-callout" aria-labelledby="contact-title"><h2 id="contact-title">Contact Vivi</h2>'
            f'<p>Operated by <strong>{escape(OPERATOR)}</strong> in {escape(OPERATOR_LOCATION)}.</p>'
            f'<p>Email <a href="mailto:{escape(EMAIL,quote=True)}">{escape(EMAIL)}</a> for support, privacy questions, '
            'data requests or concerns about Vivi.</p>'
            f'<p><a href="{SUPPORT_SERVER}">Join VELVET RUINS on Discord</a> for community support.</p>'
            '<p>For private requests, use email or a private support ticket. Include your Discord user ID, relevant server ID '
            'and a description of your request. Never send your password, bot token, OAuth secret or recovery codes. '
            'Do not post personal information in public channels or GitHub issues.</p></section>')

PRIVACY=[
 ('Who operates Vivi and what this covers',
  'ZyVelia operates Vivi, its connected website and dashboard from Massachusetts, United States. This policy explains how that service handles information. '
  'Server administrators choose which optional features to enable and control their own server records. '
  'Independently hosted copies of the open-source software are operated by their respective hosts; contact that host for its practices.'),
 ('Information Vivi processes',
  'Vivi uses Discord user, server, channel, role and message identifiers; display names and avatars; server configuration; '
  'command inputs and interaction data. Enabled features can store moderation reasons and evidence, reports, appeals, '
  'support ticket records and transcripts, profile uploads, birthdays, timezones, reminders, game progress, XP, fictional currency and votes. '
  'Message content can be processed for enabled moderation, activity and other message-based features. This does not mean every server message is saved; '
  'ticket transcripts, case evidence and other feature records can retain message text or attachments. '
  'Support messages you send to the operator are also information you provide.'),
 ('Why information is used',
  'Information is used to deliver requested features, apply server rules, prevent abuse, check administrative permissions, '
  'remember saved preferences, troubleshoot failures and answer support or privacy requests. '
  'Features may publish information in Discord: for example a leaderboard, suggestion, giveaway result or profile card. '
  'Review the feature and channel before submitting information you do not want other members to see.'),
 ('Dashboard login and cookies',
  'Discord OAuth requests identify and guilds permissions to obtain your identity and server list. '
  'Your name and avatar appear in the account menu; current server owner or Administrator permissions are checked for private settings. '
  'OAuth access tokens and login sessions stay in the running application’s memory. Sessions last up to one hour and are lost on restart. '
  'Essential cookies bind sign-in requests and maintain your session. Vivi does not ask for your Discord password and does not include advertising or analytics trackers in its website. '
  'The host, reverse proxy or support provider may keep operational logs, including request times, IP addresses and errors, depending on deployment.'),
 ('Optional AI and translation',
  'AI requires a server feature switch, approved channels and a configured provider. Translation is sent to a configured provider when requested. '
  'These requests disclose the submitted text to that provider; AI requests can also include recent conversation turns if you enabled memory. '
  'AI memory is optional, can be disabled or cleared, and its short saved conversation is no longer reused after 24 hours of inactivity; '
  'cleanup requires the bot to be running. Provider retention, training practices and processing locations depend on the selected provider. '
  'Ask ZyVelia which providers are currently configured before sending sensitive information. Turning a feature off does not recall text already sent.'),
 ('Who can receive information',
  'Discord receives bot interactions, messages, attachments and OAuth requests under its own policies. '
  'ZyVelia and authorized hosting personnel can access data held by the service for operation, support and security. '
  'Server staff can access moderation and support records according to their permissions. '
  'Enabled integrations may contact Twitch, YouTube, GitHub, Steam or other configured services; hosting, email and optional AI or translation providers '
  'process the information necessary for their role. External services have their own terms and privacy practices. '
  'The bot has no feature for selling member data or using it for targeted advertising. '
  'Information may also need to be preserved or disclosed where legally required.'),
 ('Storage, retention and backups',
  'Vivi stores active data in a host-managed database and files. Configuration, moderation records, transcripts, uploads and other feature records '
  'do not all have automatic expiry; they can remain until removed or reviewed by the operator or responsible server staff. '
  'There is no single fixed deletion period for all record types. Backups and exports can retain earlier copies after an active record is deleted. '
  'The operator must separately review those copies and prevent deleted information from being unnecessarily restored. '
  'Encrypted full-data backups are an optional feature, not a promise that every file, database or export is encrypted. '
  'The operator’s location does not guarantee that all information stays in Massachusetts or the United States. Storage and processing locations depend on hosting and external providers; contact ZyVelia for the current deployment details.'),
 ('Your choices and data requests',
  'You can choose whether to supply optional profile details, birthday or timezone information, change supported profile visibility, '
  'opt out of supported leaderboards and disable or clear AI memory. Use /tools delete_data in the relevant server and confirm the request. '
  'It removes your profile, associated birthday and AI memory, and attributable votes from that server’s active database, and asks staff to review retained records. '
  'It does not automatically remove every transcript, upload, moderation record, reminder, previously published message, backup or record in another server. '
  'Uploaded profile banners have a separate /profile banner_delete control. '
  'For access, correction, deletion or other applicable privacy requests, email ZyVelia using the contact details below. '
  'We may need to verify control of your Discord account without asking for passwords or tokens. '
  'Some records may require staff review or retention for safety, disputes or legal obligations; we will explain relevant limitations when responding. '
  'Your applicable rights depend on your location and circumstances.'),
 ('United States privacy requests',
  'You can contact ZyVelia to ask about, access, correct or request deletion of information held about your use of Vivi. '
  'Whether a particular state or federal privacy law applies depends on the service and your circumstances; '
  'being based in Massachusetts does not by itself give every user the same statutory rights. '
  'Where applicable law provides additional rights or response deadlines, those requirements apply. '
  'If you believe a request was not handled correctly, reply to the contact email asking for a review.'),
 ('Age, security and changes',
  'Vivi is not directed to children under 13. In the United States, you must be at least 13 and meet Discord’s eligibility requirements; a higher minimum age may apply elsewhere. If you believe a child under the permitted age submitted personal information, contact ZyVelia privately for review and appropriate removal. '
  'Do not submit sensitive personal information that a feature does not need. '
  'The dashboard uses permission checks, session cookies and CSRF protection, but no system guarantees absolute security. '
  'Report suspected data exposure privately by email. If a security incident requires notice under applicable law, the operator will provide the required notifications. Updated policy wording will appear on this page with a revised date; '
  'significant changes should also be announced through the support community.')]

TERMS=[
 ('About these terms',
  'These terms cover the Vivi Discord bot and connected website operated by ZyVelia. '
  'By using the service, you agree to follow these terms and the rules applicable to your server. '
  'If you do not agree, stop using Vivi and contact your server administrator about removing associated data. '
  'These service terms are separate from the repository’s software license and do not replace rights you have under applicable law.'),
 ('Eligibility and Discord rules',
  'You must meet Discord’s minimum age and other eligibility requirements in your country. '
  'Follow Discord’s Terms of Service and Community Guidelines, as well as the rules of each server where you use Vivi. '
  'Vivi is an independent project and is not sponsored, endorsed or operated by Discord.'),
 ('Acceptable use',
  'Do not use Vivi to harass, threaten, scam, spam, distribute unlawful material, expose someone’s private information or bypass access controls. '
  'Do not exploit vulnerabilities, abuse integrations, automate disruptive requests or attempt to obtain credentials or private server data. '
  'Report vulnerabilities privately using the contact email rather than testing against other users or servers without permission.'),
 ('Server administration and moderation',
  'Only manage servers where you have the necessary authority. Server owners and administrators choose modules, roles, channels and settings, '
  'and are responsible for configuring permissions and informing members about enabled features. '
  'Automated moderation can make mistakes; review significant actions. Server moderation decisions and appeals belong first with the responsible server staff. '
  'For suspected abuse of Vivi itself, contact ZyVelia.'),
 ('Your content and privacy',
  'Only submit messages, images, evidence and other content you are entitled to use and share. You retain your rights in your content. '
  'You allow Vivi to process, store, display and transmit it as needed to provide the feature you requested, subject to the Privacy Policy. '
  'Do not upload unrelated sensitive information. Access, retention, optional provider disclosures and deletion limitations are described in the Privacy Policy.'),
 ('Games, rewards and virtual items',
  'XP, achievements, virtual currency and cosmetics are for entertainment. They have no real-money value, are not redeemable for money '
  'and do not create a right to payment. Progress or virtual items may change or be reset for maintenance, balancing or abuse prevention. '
  'Giveaway organizers are responsible for eligibility rules, prize delivery and applicable requirements; Vivi does not guarantee third-party prizes.'),
 ('Optional services and costs',
  'Vivi currently requires no premium subscription. Hosting and external providers may have their own costs and terms. '
  'Optional AI can produce inaccurate or inappropriate output; verify answers before relying on them. '
  'Integrations depend on external services and may change or become unavailable. '
  'Server owners should disclose enabled providers and consider what information members send to them.'),
 ('Availability, changes and access restrictions',
  'The service is provided as available, without a promise of uninterrupted operation, permanent storage or error-free results. '
  'Maintenance, host restarts, Discord limits and provider outages may interrupt features. Keep your own copies of important information. '
  'ZyVelia may restrict access, disable features or suspend service to address abuse, security risks, legal obligations or operational problems. '
  'Where practical, contact the operator to resolve an issue or request review of a restriction. '
  'Stopping use or removing Vivi from a server does not by itself delete all retained records; see the Privacy Policy.'),
 ('Applicable law and resolving concerns',
  'Vivi is operated from Massachusetts, United States. To the extent permitted by law, these terms are governed by '
  'United States federal law and the laws of the Commonwealth of Massachusetts. '
  'This does not override mandatory protections that apply where you live or limit rights that cannot legally be waived. '
  'Contact ZyVelia by email to try to resolve a concern. These terms do not require private arbitration or waive class-action rights.'),
 ('Responsibility and updates',
  'To the extent permitted by applicable law, Vivi makes no additional guarantees about fitness for a particular purpose '
  'and is not responsible for losses caused by third-party services or server administrators’ decisions. '
  'Nothing in these terms excludes rights or liability that cannot legally be excluded. '
  'These terms may change as the service develops. The current version and revision date will be published here; '
  'significant changes should also be announced through the support community. Contact ZyVelia if you have questions about a change.')]


def policy_html(sections,other_path,other_label):
    return (f'<article class="prose"><p class="policy-meta">Last updated: {UPDATED} · Operator: {OPERATOR}</p>'
            +''.join(f'<h2>{escape(title)}</h2><p>{escape(text)}</p>' for title,text in sections)
            +f'<p>Read the <a href="/{other_path}">{other_label}</a>.</p></article>'+contact_html())
