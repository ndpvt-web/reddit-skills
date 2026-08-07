#!/usr/bin/env python3
"""
Format r/personalfinance (or any subreddit) data into monthly markdown chunks
and upload them to a NotebookLM notebook.

Usage:
  python3 upload_to_notebooklm.py --json tmp/reddit_raw_full.json --notebook NOTEBOOK_ID

Key lessons baked in:
  - `notebooklm source add --notebook ID --title TITLE FILEPATH`
    (--notebook goes AFTER the subcommand, not before it)
  - Do NOT use `notebooklm -n ID source add ...` — the -n flag position is wrong
  - Split into MONTHLY files (~1-2MB each), NOT quarterly (quarterly = 7MB+ which may fail)
  - Run the script only ONCE — running twice creates duplicate sources
  - Check `notebooklm source list` first to avoid duplicate uploads
"""
import argparse, json, datetime, subprocess
from pathlib import Path
from collections import defaultdict

NLM = str(Path.home() / ".local/bin/notebooklm")


def ts_date(ts): return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
def ts_month(ts): return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m")


def add_source(notebook_id: str, filepath: Path, title: str) -> bool:
    sz = filepath.stat().st_size
    print(f"  Uploading: {title} ({sz:,} bytes)")
    result = subprocess.run(
        [NLM, "source", "add",
         "--notebook", notebook_id,
         "--title", title,
         str(filepath)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:200]
        print(f"  FAIL: {err}")
        return False
    print(f"  OK: {result.stdout.strip()[:100]}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json",     required=True, help="Path to reddit_raw_full.json")
    ap.add_argument("--notebook", required=True, help="NotebookLM notebook ID")
    ap.add_argument("--outdir",   default="tmp/nlm_chunks")
    args = ap.parse_args()

    chunks_dir = Path(args.outdir)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    data    = json.loads(Path(args.json).read_text())
    summary = data["summary"]
    posts   = data["posts"]
    print(f"Loaded {len(posts):,} posts")

    # --- Check for existing sources to avoid duplicates ---
    existing = subprocess.run(
        [NLM, "source", "list", "--notebook", args.notebook],
        capture_output=True, text=True, timeout=30
    )
    if "00_summary" in existing.stdout:
        print("WARNING: Sources already exist in this notebook.")
        print("Run `notebooklm source list` to check before proceeding.")
        print("Aborting to avoid duplicates.")
        return

    # --- Chunk 0: Summary + top posts + monthly stats ---
    monthly_map = defaultdict(list)
    for p in posts:
        monthly_map[ts_month(p["created_utc"])].append(p)

    lines = [
        f"# r/{summary['subreddit']} — 1-Year Summary",
        f"## Period: {summary['period']}",
        "",
        "## Key Statistics",
        f"- Total posts: {summary['total_posts']:,}",
        f"- Unique authors: {summary['total_unique_authors']:,}",
        f"- Average score: {summary['avg_score']}",
        f"- Max score: {summary['max_score']:,}",
        f"- Average comments: {summary['avg_comments']}",
        f"- Max comments: {summary['max_comments']:,}",
        "",
        "## Top 30 Posts by Score",
    ]
    for i, p in enumerate(sorted(posts, key=lambda x: x.get("score",0), reverse=True)[:30], 1):
        lines.append(f"{i}. [{ts_date(p['created_utc'])}] score={p.get('score',0):,} comments={p.get('num_comments',0):,} by u/{p['author']} — {p['title'][:120]}")
    lines += ["", "## Top 30 Posts by Comments"]
    for i, p in enumerate(sorted(posts, key=lambda x: x.get("num_comments",0), reverse=True)[:30], 1):
        lines.append(f"{i}. [{ts_date(p['created_utc'])}] comments={p.get('num_comments',0):,} score={p.get('score',0):,} by u/{p['author']} — {p['title'][:120]}")
    lines += ["", "## Monthly Volume"]
    for month in sorted(monthly_map.keys()):
        mp  = monthly_map[month]
        avg = round(sum(x.get("score",0) for x in mp) / len(mp), 1)
        lines.append(f"- {month}: {len(mp):,} posts | avg_score={avg}")

    summary_path = chunks_dir / "00_summary.md"
    summary_path.write_text("\n".join(lines))

    # --- Monthly chunks ---
    chunk_paths = [summary_path]
    for month, mposts in sorted(monthly_map.items()):
        mposts_sorted = sorted(mposts, key=lambda x: x.get("score",0), reverse=True)
        mlines = [
            f"# r/{summary['subreddit']} Posts — {month}",
            f"Total: {len(mposts):,} posts | {ts_date(mposts[0]['created_utc'])} to {ts_date(mposts[-1]['created_utc'])}",
            "",
        ]
        for p in mposts_sorted:
            ptitle = p["title"][:120].replace("\n", " ")
            body   = (p.get("selftext") or "")[:180].replace("\n", " ").strip()
            mlines.append(
                f"[{ts_date(p['created_utc'])}] score={p.get('score',0):,} comments={p.get('num_comments',0):,}"
                f" author=u/{p['author']} | {ptitle}"
            )
            if body:
                mlines.append(f"  TEXT: {body}")
        path = chunks_dir / f"posts_{month}.md"
        path.write_text("\n".join(mlines))
        chunk_paths.append(path)
        print(f"  Chunk {month}: {len(mposts):,} posts → {path.stat().st_size:,} bytes")

    # --- Upload ---
    print(f"\nUploading {len(chunk_paths)} sources to notebook {args.notebook}...")
    ok = 0
    for path in chunk_paths:
        title = path.stem.replace("_", " ").replace("posts ", "Posts ").title()
        if add_source(args.notebook, path, title):
            ok += 1
    print(f"\nDone: {ok}/{len(chunk_paths)} sources uploaded.")


if __name__ == "__main__":
    main()
