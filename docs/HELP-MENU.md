# Vivi help menu

Run `/help` to open a private, mobile-friendly command browser.

- Choose a category from the dropdown: games, profiles, community, support, voice,
  notifications, moderation, settings or tools.
- Choose **All commands** to browse the full available directory.
- Use **Previous / Next** to browse ten commands per page.
- Select a command to read its description, required and optional arguments, and
  supported choices. Type the slash command in Discord to run it.
- **Search** opens a text form that searches command names and descriptions.
- **Save favorite / Remove favorite** on a detail page uses the same per-server
  favorites as `/social favorite` and `/social favorites` (maximum 20).
- **Back** returns from instructions to the current results. **Home** clears the
  current category and search. **Close** dismisses the interactive controls.

The menu reads the live command registry, including registered server aliases.
It filters Discord default permission requirements on commands and parent groups;
that discovery filter does not replace runtime checks, server feature switches,
role hierarchy, channel restrictions or server-specific Discord command settings.
Commands still enforce those when executed. The menu never executes a command.

Controls belong to the requesting member and server. They time out after
15 minutes of inactivity; reopen `/help` for a new menu. In DMs, server-only
commands and server favorites are unavailable.
