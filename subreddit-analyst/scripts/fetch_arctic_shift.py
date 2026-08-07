#!/usr/bin/env python3
"""
Arctic Shift subreddit post fetcher — checkpoint-based, resumable.

Usage:
  python3 fetch_arctic_shift.py --subreddit personalfinance --after 2025-06-17 --before 2026-06-17

Outputs:
  tmp/checkpoint_posts.jsonl  — append-only line-per-post (crash-safe)
  tmp/checkpoint_ts.txt       — last fetched timestamp (enables resume)
  tmp/reddit_raw_full.json    — final merged output (written only on success)

Key lessons baked in:
  - sort=asc (NOT sort=desc&order=desc — 'order' param doesn't exist)
  - 422 / 400 = data gap, not a bug — stop gracefully and save
  - Paginate by advancing 'after' timestamp, NOT by cursor/page number
  - Checkpoint after every page so a crash doesn't lose all data
  - Specific timestamps (2026-05-08T23:01:17) work; dates alone also work
"""
import argparse, json, time, datetime, requests
from pathlib import Path

BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subreddit", required=True)
    ap.add_argument("--after",  default="2025-06-17")
    ap.add_argument("--before", default="2026-06-17")
    ap.add_argument("--limit",  type=int, default=100)
    ap.add_argument("--outdir", default="tmp")
    args = ap.parse_args()

    out_dir   = Path(args.outdir)
    out_dir.mkdir(exist_ok=True)
    CHECKPOINT = out_dir / "checkpoint_posts.jsonl"
    RESUME_TS  = out_dir / "checkpoint_ts.txt"
    FINAL_OUT  = out_dir / "reddit_raw_full.json"

    # Resume from last saved timestamp if available
    if RESUME_TS.exists():
        after_fixed = RESUME_TS.read_text().strip()
        print(f"Resuming from: {after_fixed}")
    else:
        after_fixed = args.after

    existing = 0
    if CHECKPOINT.exists():
        with open(CHECKPOINT) as f:
            existing = sum(1 for line in f if line.strip())
        print(f"Checkpoint has {existing:,} posts already saved")

    params = {
        "subreddit": args.subreddit,
        "before": args.before,
        "limit": args.limit,
        "sort": "asc",   # IMPORTANT: no 'order' param — use sort=asc or sort=desc
    }

    page  = 0
    total = existing

    with open(CHECKPOINT, "a") as out_f:
        while True:
            params["after"] = after_fixed

            try:
                resp = requests.get(BASE, params=params, timeout=30)

                # 422 / 400 = data gap (e.g. future dates or API limit) — stop cleanly
                if resp.status_code in (422, 400):
                    err = resp.json().get("error", resp.status_code)
                    print(f"[page {page}] HTTP {resp.status_code} → stopping ({err}). Saving what we have.")
                    break

                resp.raise_for_status()
            except requests.exceptions.Timeout:
                print(f"[page {page}] Timeout — retrying in 5s...")
                time.sleep(5)
                continue

            posts = resp.json().get("data") or []

            if not posts:
                print(f"[page {page}] Empty response — end of data.")
                break

            for p in posts:
                out_f.write(json.dumps(p) + "\n")
            out_f.flush()

            last_ts = posts[-1]["created_utc"]
            after_fixed = datetime.datetime.utcfromtimestamp(last_ts + 1).strftime("%Y-%m-%dT%H:%M:%S")
            RESUME_TS.write_text(after_fixed)

            total += len(posts)
            page  += 1
            print(f"[page {page}] +{len(posts)} → total {total:,} | {datetime.datetime.utcfromtimestamp(last_ts).date()}")

            if len(posts) < args.limit:
                print("Last page reached.")
                break

            time.sleep(0.4)

    # Build final JSON from checkpoint
    print("\nBuilding final JSON...")
    all_posts = []
    with open(CHECKPOINT) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    all_posts.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Deduplicate by id
    seen, unique = set(), []
    for p in all_posts:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)

    scores   = [p.get("score", 0) for p in unique]
    comments = [p.get("num_comments", 0) for p in unique]
    authors  = set(p.get("author", "") for p in unique)

    summary = {
        "subreddit": args.subreddit,
        "period": f"{args.after} to {args.before}",
        "total_posts": len(unique),
        "total_unique_authors": len(authors),
        "avg_score": round(sum(scores)/len(scores), 2) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "avg_comments": round(sum(comments)/len(comments), 2) if comments else 0,
        "max_comments": max(comments) if comments else 0,
        "top_10_by_score": sorted(unique, key=lambda x: x.get("score",0), reverse=True)[:10],
        "top_10_by_comments": sorted(unique, key=lambda x: x.get("num_comments",0), reverse=True)[:10],
    }

    FINAL_OUT.write_text(json.dumps({"summary": summary, "posts": unique}, indent=2))
    print(f"\nSaved {len(unique):,} unique posts → {FINAL_OUT}")
    print(json.dumps({k: v for k, v in summary.items() if "top" not in k}, indent=2))

if __name__ == "__main__":
    main()
