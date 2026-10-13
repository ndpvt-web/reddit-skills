#!/usr/bin/env python3
"""Read-only, per-subreddit Arctic Shift post collector for brand audits.

Each invocation writes one subreddit/term archive with a retrieval ledger. An API
error is never interpreted as an empty result. Search-only archives are marked so.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE = "https://arctic-shift.photon-reddit.com/api"


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def fetch_page(session, path, params):
    for attempt in range(4):
        response = session.get(f"{BASE}/{path}", params=params, timeout=60)
        if response.status_code != 422 or "Timeout" not in response.text or attempt == 3:
            break
        time.sleep(2 ** attempt)
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]} ({response.url})")
    value = response.json()
    if not isinstance(value, dict) or not isinstance(value.get("data"), list):
        raise ValueError(f"Unexpected API response for {response.url}")
    return value["data"]


def collect(subreddit, start, end, query, max_pages, page_size):
    session = requests.Session()
    params = {"subreddit": subreddit, "after": start, "before": end, "limit": page_size, "sort": "asc"}
    if query:
        params["query"] = query
    ledger = {"source": BASE, "subreddit": subreddit, "start": start, "end": end,
              "query": query, "mode": "search_only" if query else "full_subreddit",
              "pages": 0, "status": "partial", "errors": []}
    posts = {}
    previous_cursor = None
    previous_page_ids = None
    while ledger["pages"] < max_pages:
        try:
            page = fetch_page(session, "posts/search", params)
        except Exception as error:
            ledger["errors"].append(str(error))
            break
        ledger["pages"] += 1
        page_ids = tuple(post.get("id") for post in page if isinstance(post, dict))
        if page_ids and page_ids == previous_page_ids:
            ledger["errors"].append("Repeated identical page at timestamp boundary")
            break
        previous_page_ids = page_ids
        for post in page:
            if isinstance(post, dict) and post.get("id"):
                posts[post["id"]] = post
        if not page:
            ledger["status"] = "verified_empty_page_after_pagination"
            break
        last_ts = int(page[-1]["created_utc"])
        cursor = datetime.fromtimestamp(last_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        if cursor == previous_cursor and len(page) >= page_size:
            ledger["errors"].append("Timestamp cursor failed to advance on a full page")
            break
        previous_cursor = cursor
        params["after"] = cursor
        time.sleep(0.25)
    else:
        ledger["errors"].append(f"Stopped at max_pages={max_pages}")
    records = sorted(posts.values(), key=lambda p: (p.get("created_utc", 0), p["id"]))
    ledger["unique_posts"] = len(records)
    ledger["oldest"] = stamp(records[0]["created_utc"]) if records else None
    ledger["newest"] = stamp(records[-1]["created_utc"]) if records else None
    return records, ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subreddit", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--query")
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    posts, ledger = collect(args.subreddit, args.after, args.before, args.query, args.max_pages, args.page_size)
    (outdir / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=2) + "\n")
    (outdir / "ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ledger))


if __name__ == "__main__":
    main()
