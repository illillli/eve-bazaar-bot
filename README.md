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
| `EXCLUDE_KEYWORDS` | `private` | comma-separated; topics whose title contains any (case-insensitive) are not sent |
| `STATE_FILE` | `seen.json` | where seen topic IDs are stored |

`python bot.py --once` does a single check and exits (handy for cron / Task Scheduler).

## Run for free on GitHub Actions

1. Fork/push this repo (public repos get unlimited free Actions minutes).
2. Settings → Secrets and variables → Actions → New secret: `DISCORD_WEBHOOK_URL`.
3. Actions tab → enable workflows → run "Check Character Bazaar" once (this seeds `seen.json`).

It then runs every ~5 minutes (GitHub's minimum; runs can be delayed). `seen.json` is committed back
only when new topics appear. Note: GitHub disables scheduled workflows after 60 days without repo activity.

## Run on your own machine instead

`python bot.py` loops forever (every `POLL_INTERVAL` seconds) - use `pm2`, `systemd`, or Task Scheduler.
