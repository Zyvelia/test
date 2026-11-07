# Vivi source map

```text
Vivi/
├── assets/                 Bot branding and artwork
├── docs/                   Guides and screenshots
├── scripts/                Preview and bootstrap helpers
├── tests/                  Python tests and browser checks
├── vivi/
│   ├── core/               Storage, settings, permissions, localization and shared helpers
│   ├── server/             Community, moderation, profiles, tickets, notifications and menus
│   ├── games/              Game engines, arcade UI, competitions and idle worlds
│   ├── site/               Website, dashboard, embed writer and event-message editors
│   │   ├── web/            Website JavaScript, CSS and favicon
│   │   └── static/         Dashboard studio JavaScript
│   ├── assets/             Shared fonts and starter profile backgrounds
│   ├── bot.py              Discord bot entry point
│   ├── supervisor.py       Crash recovery and startup updates
│   ├── tray.py             Windows tray controls
│   ├── updater.py          GitHub installation and rollback
│   ├── host_lock.py        Stable launcher/updater/bootstrap lock
│   ├── startup.py          Windows/Linux startup installation
│   ├── backup.py           Encrypted full-data backup CLI
│   ├── healthcheck.py      Health-check entry point
│   └── verify.py           Host verification CLI
├── start.bat / start.sh    Start Vivi
├── setup.bat / setup.sh    Set up the virtual environment
├── update.bat / update.sh  Update from GitHub
└── tray.bat                Open the Windows tray
```

Host entry points stay at their original paths so launcher scripts, services,
Docker commands and the updater bootstrap continue to work. Internal imports now
use the grouped packages; custom code importing old flat internal modules needs
to follow this map. Fonts and background images retain a shared asset directory.

Your `.env`, `.venv` and `data` remain local runtime files. They are not moved,
committed or included in source-folder cleanup. Archive updates remove obsolete
source paths only when a previous updater manifest records them and their contents
are unchanged. Old untracked source files can remain in older ZIP installations;
the updated bot imports the grouped packages.

## Moderation confirmations

Member-removal confirmation lives in `vivi/server/moderation.py`. `/kick` and `/ban`
remain direct commands in `vivi/bot.py`, preserving their permission defaults and
initial hierarchy checks. Their private, single-use prompt expires in two minutes.
Confirming refreshes the target, moderator and bot member before checking current
permissions, hierarchy and the moderation switch. Only successful removals create
cases; an error after removal but during logging is reported without retrying the
action.
