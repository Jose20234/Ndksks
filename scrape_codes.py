import sys
import json
import argparse
from datetime import datetime, timezone

try:
    import cloudscraper
except ImportError:
    print("ERROR: cloudscraper not installed. Run: pip install cloudscraper", file=sys.stderr)
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip install beautifulsoup4", file=sys.stderr)
    sys.exit(1)

TARGET_URL  = "https://fortnite.gg/lobby-hacks"
SOURCE_NAME = "site:fortnitegg"
SEASON      = "C7S4"
SEASON_NAME = "Chapter 7 Season 4 — Override"

CATEGORY_RULES = [
    (["sprite dust"],                                          "Sprite Dust"),
    (["xp"],                                                   "XP"),
    (["loading screen"],                                       "Loading Screen"),
    (["lobby"],                                                "Lobby Effect"),
    (["spray"],                                                "Spray"),
    (["emoticon"],                                             "Emoticon"),
    (["cheat master"],                                         "Cheat Master Sprite"),
    (["sprite"],                                               "Cheat Master Sprite"),
    (["llama", "extractor", "accelerator", "taco", "locator", "supply drop"], "Gizmo"),
]

def infer_category(reward):
    lower = reward.lower()
    for keywords, category in CATEGORY_RULES:
        if any(kw in lower for kw in keywords):
            return category
    return "Other"

def scrape(merge_data):
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )

    try:
        resp = scraper.get(
            TARGET_URL,
            headers={
                "Referer": "https://fortnite.gg/",
                "Accept":  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=20,
            allow_redirects=True,
        )
    except Exception as e:
        print(f"ERROR: request failed: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"ERROR: HTTP {resp.status_code}", file=sys.stderr)
        sys.exit(1)

    soup  = BeautifulSoup(resp.text, "html.parser")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now   = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    existing = {}
    if merge_data:
        for entry in merge_data.get("codes", []):
            existing[entry["id"]] = entry

    scraped_ids = set()
    codes = []

    for el in soup.select(".pinpad"):
        code = el.get("data-code", "").strip()
        if not code:
            continue

        reward_el = el.select_one(".pinpad-gift")
        reward = reward_el.get_text(strip=True) if reward_el else ""
        if not reward:
            continue

        is_expired   = bool(el.find_parent(class_="pinpad-expired"))
        availability = "expired" if is_expired else "active"
        entry_id     = code.upper().replace(" ", "")
        category     = infer_category(reward)

        if entry_id in existing:
            prev    = existing[entry_id]
            sources = list(dict.fromkeys(prev.get("observedSources", []) + [SOURCE_NAME]))
            entry   = {
                **prev,
                "code":            code,
                "reward":          reward,
                "category":        category,
                "status":          "confirmed",
                "lastSeen":        today,
                "availability":    availability,
                "observedSources": sources,
                "sourceCount":     len(sources),
            }
        else:
            entry = {
                "id":              entry_id,
                "code":            code,
                "reward":          reward,
                "category":        category,
                "status":          "confirmed",
                "firstSeen":       today,
                "lastSeen":        today,
                "availability":    availability,
                "observedSources": [SOURCE_NAME],
                "sourceCount":     1,
                "expiredSources":  [],
            }

        scraped_ids.add(entry_id)
        codes.append(entry)

    if not codes:
        print("WARNING: no .pinpad elements found — page structure may have changed.", file=sys.stderr)

    for entry_id, prev in existing.items():
        if entry_id not in scraped_ids:
            codes.append({**prev, "availability": "expired"})

    codes.sort(key=lambda e: (e["availability"] != "active", e["status"] != "confirmed", e["id"]))

    return {
        "databaseVersion": datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M"),
        "updated":         now,
        "season":          SEASON,
        "seasonName":      SEASON_NAME,
        "sources":         [TARGET_URL],
        "codes":           codes,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="codes.json")
    parser.add_argument("--merge",  default=None)
    args = parser.parse_args()

    merge_data = None
    if args.merge:
        try:
            with open(args.merge, "r", encoding="utf-8") as f:
                merge_data = json.load(f)
        except FileNotFoundError:
            pass

    data = scrape(merge_data)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    active    = sum(1 for c in data["codes"] if c["availability"] == "active")
    confirmed = sum(1 for c in data["codes"] if c["status"] == "confirmed")
    print(f"{len(data['codes'])} codes ({active} active, {confirmed} confirmed) → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
