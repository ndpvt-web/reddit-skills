#!/usr/bin/env python3
"""
Arctic Shift subreddit post fetcher — checkpoint-based, resumable.

Usage:
  python3 fetch_arctic_shift.py --subreddit example --after YYYY-MM-DD --before YYYY-MM-DD

Outputs:
  tmp/checkpoint_posts.jsonl  — append-only line-per-post (crash-safe)
  tmp/checkpoint_ts.txt       — last fetched timestamp (enables resume)
  tmp/reddit_raw_full.json    — final merged output (written only on success)

Key lessons baked in:
  - sort=asc (NOT sort=desc&order=desc — 'order' param doesn't exist)
  - HTTP errors are incomplete collection, never proof of full coverage
  - Paginate by advancing 'after' timestamp, NOT by cursor/page number
  - Checkpoint after every page so a crash doesn't lose all data
  - Specific timestamps work; dates alone also work
"""
import argparse, json, time, datetime, re, requests
from pathlib import Path

BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subreddit", required=True)
    ap.add_argument("--after", required=True, help="Inclusive UTC start, YYYY-MM-DD")
    ap.add_argument("--before", required=True, help="Exclusive UTC end, YYYY-MM-DD")
    ap.add_argument("--limit",  type=int, default=100)
    ap.add_argument("--outdir", default="tmp")
    args = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_]{2,21}", args.subreddit):
        ap.error("subreddit must be a valid name without r/ prefix")
    try:
        start = datetime.date.fromisoformat(args.after)
        end = datetime.date.fromisoformat(args.before)
    except ValueError:
        ap.error("after and before must be ISO dates (YYYY-MM-DD)")
    if start >= end:
        ap.error("before must be later than after")

    out_dir   = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    CHECKPOINT = out_dir / "checkpoint_posts.jsonl"
    RESUME_TS  = out_dir / "checkpoint_ts.txt"
    FINAL_OUT  = out_dir / "reddit_raw_full.json"

    # Checkpoints belong to one community and date range only.
    manifest = out_dir / "request.json"
    request = {"subreddit": args.subreddit, "after": args.after, "before": args.before}
    if CHECKPOINT.exists() and not manifest.exists():
        ap.error("existing checkpoint has no request manifest; use a new outdir")
    if manifest.exists() and json.loads(manifest.read_text()) != request:
        ap.error("outdir contains a different collection; choose a separate outdir")
    manifest.write_text(json.dumps(request, indent=2))

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

    complete = False
    failure = None
    with open(CHECKPOINT, "a") as out_f:
        while True:
            params["after"] = after_fixed

            try:
                resp = requests.get(BASE, params=params, timeout=30)

                resp.raise_for_status()
            except requests.exceptions.Timeout:
                failure = f"Timeout at page {page}"
                break
            except requests.exceptions.RequestException as exc:
                failure = f"Request failure at page {page}: {exc}"
                break

            try:
                posts = resp.json().get("data") or []
            except (ValueError, AttributeError) as exc:
                failure = f"Invalid response at page {page}: {exc}"
                break

            if not posts:
                print(f"[page {page}] Empty response — end of data.")
                complete = True
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
        "collection_status": "complete" if complete else "partial",
        "collection_error": failure,
        "last_cursor": after_fixed,
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
    if not complete:
        raise SystemExit("Collection is partial; do not describe it as exhaustive")

if __name__ == "__main__":
    main()
