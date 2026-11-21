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


CHAR_ID_PATTERNS = [
    r"qsna\.eu/eve/characters/(\d+)",
    r"evewho\.com/character/(\d+)",
    r"zkillboard\.com/character/(\d+)",
    r"images\.evetech\.net/characters/(\d+)",
]


def fetch_first_post(topic_id):
    """Return the topic's first post as a dict (username, name, avatar, text, char_id), best effort."""
    try:
        r = requests.get(f"{BASE}/t/{topic_id}.json", headers=HEADERS, timeout=30)
        r.raise_for_status()
        post = r.json()["post_stream"]["posts"][0]
    except Exception as e:
        print(f"first-post fetch failed for {topic_id}: {e}", file=sys.stderr)
        return {}
    cooked = post.get("cooked", "")
    char_id = next((m.group(1) for p in CHAR_ID_PATTERNS if (m := re.search(p, cooked))), None)
    # 連結預覽卡（onebox）的文字是別的網站的介紹，不算內文
    body = re.sub(r"<aside class=\"onebox.*?</aside>", " ", cooked, flags=re.S)
    body = re.sub(r"<br\s*/?>|</p>|</li>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = "\n".join(re.sub(r"[ 	]+", " ", line).strip() for line in body.splitlines())
    body = re.sub(r"\n{2,}", "\n", body).strip()
    avatar = post.get("avatar_template", "").replace("{size}", "96")
    if avatar.startswith("/"):
        avatar = BASE + avatar
    return {
        "username": post.get("username", ""),
        "name": post.get("name") or post.get("username", ""),
        "avatar": avatar,
        "text": body,
        "char_id": char_id,
    }


def post_kind(title):
    """從標題判斷是出售、收購還是拍賣。"""
    t = title.lower()
    if re.search(r"\bwts\b|for sale|selling", t):
        return "💰 出售", 0x2ECC71
    if re.search(r"\bwtb\b|buying|looking for", t):
        return "🛒 收購", 0xE67E22
    if re.search(r"\bwta\b|auction", t):
        return "🔨 拍賣", 0x9B59B6
    if re.search(r"\bsold\b|closed", t):
        return "✅ 已售出", 0x95A5A6
    return "📢 新文章", 0x2B7BE4


def find_sp(text):
    """抓出「70m SP」「5.5 mil sp」這類技能點數。"""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(m|mil|million|kk)?\s*\+?\s*sp\b", text, re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    if not m.group(2) and num >= 100_000:  # 寫成完整數字
        num /= 1_000_000
    return f"{num:g}M SP"


def find_price(text):
    """抓出「90 B ISK」「3.5b ISK start」「B/O 40bil」這類價格（以 B = billion 為主）。"""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(b|bil|bill|billion)\b(?:\s*isk)?", text, re.I)
    if not m:
        return None
    return f"{float(m.group(1).replace(',', '.')):g} B ISK"


def build_embed(topic, post, preview=False):
    url = f"{BASE}/t/{topic['slug']}/{topic['id']}"
    kind, color = post_kind(topic["title"])
    text = post.get("text", "")
    excerpt = text[:400].rstrip() + ("…" if len(text) > 400 else "")
    quoted = "\n".join(f"> {line}" for line in excerpt.splitlines()[:8]) if excerpt else "> （沒有內文）"

    fields = [{"name": "🏷️ 類型", "value": kind, "inline": True}]
    sp = find_sp(topic["title"]) or find_sp(text)
    if sp:
        fields.append({"name": "🧠 技能點", "value": f"**{sp}**", "inline": True})
    price = find_price(topic["title"]) or find_price(text)
    if price:
        fields.append({"name": "💰 價格", "value": f"**{price}**", "inline": True})
    tags = [t["name"] if isinstance(t, dict) else str(t) for t in topic.get("tags") or []]
    if tags:
        fields.append({"name": "🔖 標籤", "value": " ".join(f"`{t}`" for t in tags), "inline": True})
    if post.get("char_id"):
        cid = post["char_id"]
        fields.append({"name": "🔗 角色資料", "value": f"[EveWho](https://evewho.com/character/{cid}) · "
                                                    f"[zKillboard](https://zkillboard.com/character/{cid}/)",
                       "inline": False})

    embed = {
        "title": topic["title"][:256],
        "url": url,
        "description": quoted,
        "color": color,
        "fields": fields,
        "timestamp": topic["created_at"],
        "footer": {"text": "EVE Character Bazaar" + ("（預覽，不是新文章）" if preview else "")},
    }
    if post.get("username"):
        embed["author"] = {"name": post["name"], "url": f"{BASE}/u/{post['username']}"}
        if post.get("avatar"):
            embed["author"]["icon_url"] = post["avatar"]
    if post.get("char_id"):
        embed["thumbnail"] = {"url": f"https://images.evetech.net/characters/{post['char_id']}/portrait?size=128"}
    return embed


def notify(topic, preview=False):
    embed = build_embed(topic, fetch_first_post(topic["id"]), preview)
    payload = {"content": "🆕 **Character Bazaar 有新文章**" if not preview else "👀 **樣式預覽**",
               "embeds": [embed]}
    r = requests.post(WEBHOOK, json=payload, timeout=30)
    if r.status_code == 429:  # rate limited
        time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
        r = requests.post(WEBHOOK, json=payload, timeout=30)
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
    if os.environ.get("PREVIEW") == "1":
        # 把最新一篇發出來看樣式，不更新 seen.json
        notify(max(fetch_topics(), key=lambda t: t["created_at"]), preview=True)
        print("Preview sent.")
        return
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
