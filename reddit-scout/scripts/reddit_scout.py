#!/usr/bin/env python3
"""
Reddit Scout — Fetch real-time posts from subreddits.
Primary: Arctic Shift API | Fallback: Reddit RSS

Usage:
    python3 reddit_scout.py <subreddit> <hours> [limit]
    python3 reddit_scout.py AI_Agents 2 50
    python3 reddit_scout.py AI_Agents,ClaudeAI,SideProject 6 100

Output: JSON array of posts to stdout (for piping to relevance filter)
"""

import urllib.request
import json
import time
import xml.etree.ElementTree as ET
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

ARCTIC_SHIFT_BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"
RSS_BASE = "https://www.reddit.com/r/{subreddit}/new.rss"
UA_ARCTIC = "HappyCapyBot/1.0"
UA_RSS = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def fetch_arctic_shift(subreddit, after_utc, limit=50, truncate=500, before=None):
    # API hard-caps limit at 100 per request (limit>100 -> HTTP 400). Paginate with `before`.
    limit = min(limit, 100)
    url = (
        f"{ARCTIC_SHIFT_BASE}"
        f"?subreddit={subreddit}"
        f"&sort=desc"
        f"&limit={limit}"
        f"&after={after_utc}"
    )
    if before:
        url += f"&before={before}"
    req = urllib.request.Request(url, headers={"User-Agent": UA_ARCTIC})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    now = int(time.time())
    return [
        {
            "title": p["title"],
            "author": p["author"],
            "url": "https://www.reddit.com" + p["permalink"],
            "subreddit": p["subreddit"],
            "score": p.get("score", 0),
            "num_comments": p.get("num_comments", 0),
            "upvote_ratio": p.get("upvote_ratio"),
            "selftext": (
                (p.get("selftext") or "").replace("\r", " ").replace("\n", " ")[:truncate]
                if truncate else
                (p.get("selftext") or "").replace("\r", " ").replace("\n", " ")
            ),
            # A post can show selftext == "[removed]"/"[deleted]" within seconds of
            # posting — this is real Reddit-side moderation (site spam filter,
            # subreddit AutoMod, human mod, or author self-delete), not a fetch bug.
            # See ~/.claude/skills/reddit-scout/references/methods.md#removed-content.
            "is_removed_or_deleted": p.get("selftext") in ("[removed]", "[deleted]"),
            "removed_by_category": p.get("removed_by_category"),
            "removed_by": p.get("removed_by"),
            "flair": p.get("link_flair_text"),
            "created_utc": p["created_utc"],
            "age_minutes": round((now - p["created_utc"]) / 60, 1),
            "source": "arctic_shift",
        }
        for p in data.get("data", [])
    ]


def fetch_rss(subreddit, after_utc, limit=50):
    rss_limit = min(limit, 100)
    url = RSS_BASE.format(subreddit=subreddit) + f"?limit={rss_limit}"
    req = urllib.request.Request(url, headers={"User-Agent": UA_RSS})
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                xml_data = r.read()
                break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                reset = int(e.headers.get("x-ratelimit-reset", "35"))
                time.sleep(reset + 2)
                continue
            raise
    else:
        raise RuntimeError("RSS: rate-limited after 3 retries")

    root = ET.fromstring(xml_data)
    now = int(time.time())
    results = []
    for entry in root.findall("atom:entry", ns):
        pub = entry.findtext("atom:published", "", ns)
        if not pub:
            continue
        ts = int(datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp())
        if ts < after_utc:
            continue
        link_el = entry.find("atom:link", ns)
        url_val = link_el.get("href", "") if link_el is not None else ""
        author_raw = entry.findtext("atom:author/atom:name", "", ns)
        author = author_raw[3:] if author_raw.startswith("/u/") else author_raw
        content_el = entry.findtext("atom:content", "", ns)
        results.append(
            {
                "title": entry.findtext("atom:title", "", ns),
                "author": author,
                "url": url_val,
                "subreddit": subreddit,
                "score": None,
                "num_comments": None,
                "selftext": (content_el or "")[:500],
                "flair": None,
                "created_utc": ts,
                "age_minutes": round((now - ts) / 60, 1),
                "source": "rss",
            }
        )
    return results


def fetch_arctic_shift_paginated(subreddit, after_utc, target_limit, truncate=500):
    """Arctic Shift caps at 100 posts/request. Page back in time via `before`
    until target_limit is reached or the after_utc boundary is exhausted."""
    all_posts = []
    before = None
    while len(all_posts) < target_limit:
        page = fetch_arctic_shift(subreddit, after_utc, 100, truncate, before)
        if not page:
            break
        all_posts.extend(page)
        before = page[-1]["created_utc"] - 1
        if len(page) < 100:
            break
    return all_posts[:target_limit]


def fetch_subreddit(subreddit, max_age_hours, limit=50, truncate=500):
    after_utc = int(time.time()) - int(max_age_hours * 3600)
    try:
        if limit > 100:
            return fetch_arctic_shift_paginated(subreddit, after_utc, limit, truncate)
        return fetch_arctic_shift(subreddit, after_utc, limit, truncate)
    except Exception as e:
        sys.stderr.write(f"[Arctic Shift failed for r/{subreddit}: {e}] Falling back to RSS...\n")
    try:
        return fetch_rss(subreddit, after_utc, limit)
    except Exception as e2:
        sys.stderr.write(f"[RSS also failed for r/{subreddit}: {e2}]\n")
        return []


def fetch_multiple(subreddits, max_age_hours, limit_per_sub=50, truncate=500):
    all_posts = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fetch_subreddit, s, max_age_hours, limit_per_sub, truncate): s for s in subreddits}
        for f in as_completed(futs):
            try:
                all_posts.extend(f.result())
            except Exception as e:
                sys.stderr.write(f"[WARN] r/{futs[f]} failed: {e}\n")
    all_posts.sort(key=lambda p: p["created_utc"], reverse=True)
    return all_posts


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: reddit_scout.py <subreddit(s)> <hours> [limit] [truncate]", file=sys.stderr)
        print("  reddit_scout.py AI_Agents 2 50", file=sys.stderr)
        print("  reddit_scout.py AI_Agents,ClaudeAI 6 100", file=sys.stderr)
        print("  reddit_scout.py AI_Agents 6 50 0   # truncate=0 -> full untruncated selftext", file=sys.stderr)
        sys.exit(1)

    subs = [s.strip() for s in sys.argv[1].split(",")]
    hours = float(sys.argv[2])
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    truncate = int(sys.argv[4]) if len(sys.argv) > 4 else 500

    if len(subs) == 1:
        posts = fetch_subreddit(subs[0], hours, limit, truncate)
    else:
        posts = fetch_multiple(subs, hours, limit, truncate)

    json.dump(posts, sys.stdout, indent=2, ensure_ascii=True)
