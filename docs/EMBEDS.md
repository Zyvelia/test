# Vivi embed writer

Create reusable rules, announcements, guides and other messages without writing JSON. Templates are shared by administrators of the same server and persist across restarts in Vivi’s database. Each server can save up to 100 templates.

## Dashboard

Sign in with Discord, choose **Embed writer** in the navigation and select your server. You can also open it from **Server settings → Saved embed writer**.

1. Choose **New embed** or **Rules starter**, or open a template from the library.
2. Give it a template name, then enter its title and message. Discord markdown such as `**bold**`, lists and links works in posted messages.
3. Optionally set an accent color, footer, title link, image URL and thumbnail URL. URLs must use HTTPS. Vivi passes image URLs to Discord rather than downloading them itself.
4. Add up to 25 fields. Fields have a heading, text and an optional inline setting; use Move up/down to reorder them.
5. Review the live text preview. It shows text and field order; Discord renders markdown, inline layouts and remote images on posting. The character counter uses Discord’s text limits, including its combined 6,000-character limit.
6. Choose **Save template**, or **Save as new copy**. Saving never posts to Discord.
7. To post, expand **Post to Discord**, select a text channel, check the confirmation and choose **Post embed**. Posting sends the current editor contents, without saving those changes to the library. Save your template first if you want to keep it.

Delete removes a template from the library after confirmation. Messages already posted to Discord remain. Editing a saved template also leaves previously posted messages unchanged. Leaving an edited page warns about unsaved changes; failed form submissions can be revisited with your browser’s Back button.

## Discord

Use **`/embed`**. This is one menu, rather than a collection of subcommands:

- **New embed** opens a form for a name, title, message, color and footer.
- Select an existing template, then **Preview**, **Edit**, **Post** or **Delete**.
- **Post** shows the actual Discord embed privately. Select a channel, then press **Confirm post** to publish once.
- **Previous / Next** browse libraries larger than 20 templates.

The Discord form supports descriptions up to 4,000 characters because of Discord modal limits. The website supports the full 4,096-character description, images, links and fields. Editing the basic text in Discord preserves advanced fields configured on the website.

## Permissions and storage

Administrator permission is required to manage and post templates. Website actions use the existing Discord login, fresh permission verification and CSRF protection. Discord menus are bound to their opening account and server, expire after 15 minutes and recheck administrator permissions. Posting additionally fetches the current server member from Discord.

Vivi needs **View Channel**, **Send Messages** and **Embed Links** in the destination text channel. Posts disable all mentions; text containing `@everyone`, user IDs or role IDs will not send notifications through this writer.

Saved templates are server records in Vivi’s SQLite database, including the editing administrator’s ID and last update time. They are included in full-data backups; the settings-only configuration export does not include message templates. Keep private information out of templates meant for public posting. Deleting the template does not delete posted messages.
