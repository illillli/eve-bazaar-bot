"""Watch the EVE Online Character Bazaar forum and post new topics to a Discord webhook."""
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://forums.eveonline.com"
CATEGORY_URL = f"{BASE}/c/marketplace/character-bazaar/60.json"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
INTERVAL = int(os.environ.get("POLL_INTERVAL", "120"))
STATE_FILE = Path(os.environ.get("STATE_FILE", "seen.json"))
EXCLUDE = [k.strip().lower() for k in os.environ.get("EXCLUDE_KEYWORDS", "private").split(",") if k.strip()]
HEADERS = {"User-Agent": "eve-bazaar-bot/1.0 (+discord notifier)"}


def load_seen():
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return None  # first run


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen)))


def fetch_topics():
    r = requests.get(CATEGORY_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return [t for t in r.json()["topic_list"]["topics"] if not t.get("pinned")]


def fetch_first_post(topic_id):
    """Return (author, plain-text body) of the topic's first post, best effort."""
    try:
        r = requests.get(f"{BASE}/t/{topic_id}.json", headers=HEADERS, timeout=30)
        r.raise_for_status()
        post = r.json()["post_stream"]["posts"][0]
        text = re.sub(r"<[^>]+>", " ", post["cooked"])
        text = re.sub(r"\s+", " ", html.unescape(text)).strip()
        return post.get("username", ""), text
    except Exception as e:
        print(f"first-post fetch failed for {topic_id}: {e}", file=sys.stderr)
        return "", ""


def notify(topic):
    author, body = fetch_first_post(topic["id"])
    url = f"{BASE}/t/{topic['slug']}/{topic['id']}"
    embed = {
        "title": topic["title"][:256],
        "url": url,
        "description": body[:500] + ("…" if len(body) > 500 else ""),
        "color": 0x2B7BE4,
        "timestamp": topic["created_at"],
        "footer": {"text": "EVE Character Bazaar"},
    }
    if author:
        embed["author"] = {"name": author}
    r = requests.post(WEBHOOK, json={"content": "🆕 New Character Bazaar post", "embeds": [embed]}, timeout=30)
    if r.status_code == 429:  # rate limited
        time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
        r = requests.post(WEBHOOK, json={"embeds": [embed]}, timeout=30)
    r.raise_for_status()


def check_once():
    topics = fetch_topics()
    seen = load_seen()
    if seen is None:
        save_seen({t["id"] for t in topics})
        print(f"First run: recorded {len(topics)} existing topics, no notifications sent.")
        return
    new = sorted((t for t in topics if t["id"] not in seen), key=lambda t: t["created_at"])
    for t in new:
        if any(k in t["title"].lower() for k in EXCLUDE):
            seen.add(t["id"])
            save_seen(seen)
            print(f"Skipped (excluded keyword): {t['title']}")
            continue
        notify(t)
        seen.add(t["id"])
        save_seen(seen)  # save per topic so a crash never causes duplicates
        print(f"Notified: {t['title']}")
        time.sleep(1)


def main():
    if not WEBHOOK:
        sys.exit("Set DISCORD_WEBHOOK_URL (see README).")
    once = "--once" in sys.argv
    while True:
        try:
            check_once()
        except Exception as e:
            print(f"check failed: {e}", file=sys.stderr)
        if once:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
