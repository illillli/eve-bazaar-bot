# EVE Character Bazaar → Discord

Polls the [Character Bazaar](https://forums.eveonline.com/c/marketplace/character-bazaar/60) forum
(Discourse JSON API) and posts every **new topic** to a Discord channel via webhook, with title,
poster, a preview of the first post and a link.

## Setup

1. In Discord: channel settings → Integrations → Webhooks → New Webhook → copy the URL.
2. Install and run:

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."   # PowerShell: $env:DISCORD_WEBHOOK_URL="..."
python bot.py
```

The first run only records existing topics (no spam). After that, each new topic is sent once.

| Env var | Default | Meaning |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | – | required |
| `POLL_INTERVAL` | `120` | seconds between checks |
| `STATE_FILE` | `seen.json` | where seen topic IDs are stored |

`python bot.py --once` does a single check and exits (handy for cron / Task Scheduler).

## Keep it running

Run it on any always-on machine (VPS, Raspberry Pi, your PC) with `pm2`, `systemd`, `tmux`, or Windows Task Scheduler.
