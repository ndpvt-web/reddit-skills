#!/usr/bin/env python3
"""
reddit_intel_harvest.py — Harvest 1 year of Reddit data per subreddit via Arctic Shift,
convert to monthly markdown chunks, and upload to NotebookLM category notebooks.

Usage:
    python3 reddit_intel_harvest.py [--category "Claude & Anthropic"] [--resume]
"""

import asyncio, json, time, re, argparse, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from calendar import monthrange
import urllib.request

# ── Config ───────────────────────────────────────────────────────────────────
SKILL_DIR    = Path(__file__).parent.parent
NOTEBOOKS_CFG = SKILL_DIR / 'config/reddit_intel_notebooks.json'
HARVEST_DIR  = SKILL_DIR / 'outputs/intel_harvest'
MARKDOWN_DIR = SKILL_DIR / 'outputs/intel_markdown'
STATUS_FILE  = SKILL_DIR / 'outputs/intel_harvest/harvest_status.json'

CATEGORIES = {
    "Claude & Anthropic": [
        "claudeai", "ClaudeCode", "claude", "Anthropic", "claudexplorers"
    ],
    "AI Agents & Automation": [
        "openclaw", "AI_Agents", "AgentsOfAI", "LangChain",
        "n8n_ai_agents", "AiAutomations", "AiBuilders"
    ],
    "AI Tools & Products": [
        "ChatGPT", "OpenAI", "GoogleGemini", "perplexity_ai", "notebooklm", "artificial"
    ],
    "AI Coding Tools": [
        "cursor", "opencodeCLI", "GithubCopilot", "LocalLLaMA"
    ],
    "Personal Finance": [
        "personalfinance", "investing", "financialindependence", "Bogleheads", "stocks"
    ],
    "Entrepreneurship": [
        "startups", "Entrepreneur", "smallbusiness", "SideProject", "IndieHackers"
    ],
    "Real Estate": [
        "realestate", "FirstTimeHomeBuyer", "realestateinvesting", "REBubble", "AskRealEstate"
    ],
}

# Score thresholds — filter low-quality posts
SCORE_THRESHOLD = {
    "ChatGPT": 5, "OpenAI": 5, "artificial": 5,
    "personalfinance": 5, "investing": 5, "stocks": 5,
    "startups": 3, "Entrepreneur": 3, "realestate": 3,
    "__default__": 1,  # keep almost everything for smaller subs
}

MAX_COMMENTS_PER_POST = 15
CHUNK_SIZE_POSTS = 200   # posts per markdown chunk
MAX_CHUNK_KB = 380       # stay under NotebookLM 500KB limit

# ── Arctic Shift helpers ──────────────────────────────────────────────────────

def arctic_get(endpoint, params):
    base = "https://arctic-shift.photon-reddit.com/api"
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{base}/{endpoint}?{qs}"
    req = urllib.request.Request(url, headers={'User-Agent': 'reddit-intel-harvester/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get('data', [])
    except Exception as e:
        print(f"    [arctic] {endpoint} error: {e}")
        return []

def fetch_posts_month(subreddit, year, month):
    """Fetch all posts for a subreddit in a given month, descending pagination."""
    days = monthrange(year, month)[1]
    after  = f"{year}-{month:02d}-01"
    before = f"{year}-{month:02d}-{days:02d}T23:59:59"
    threshold = SCORE_THRESHOLD.get(subreddit, SCORE_THRESHOLD['__default__'])

    all_posts, iters = [], 0
    cur_before = before
    while iters < 200:
        batch = arctic_get("posts/search", {
            "subreddit": subreddit, "limit": 100,
            "after": after, "before": cur_before
        })
        if not batch:
            break
        filtered = [p for p in batch if p.get('score', 0) >= threshold]
        all_posts.extend(filtered)
        if len(batch) < 100:
            break
        earliest = batch[-1]['created_utc']
        cur_before = datetime.fromtimestamp(earliest - 1, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        iters += 1
        time.sleep(0.25)
    return all_posts

def fetch_comments_for_posts(post_ids, subreddit, year, month, max_pages=5):
    """Fetch a sample of comments (max_pages*100) and join to post IDs.
    Capped to avoid memory exhaustion on large subreddits."""
    days = monthrange(year, month)[1]
    after  = f"{year}-{month:02d}-01"
    before = f"{year}-{month:02d}-{days:02d}T23:59:59"

    all_comments = []
    cur_before = before
    post_id_set = set(post_ids)

    for _ in range(max_pages):
        batch = arctic_get("comments/search", {
            "subreddit": subreddit, "limit": 100,
            "after": after, "before": cur_before
        })
        if not batch:
            break
        for c in batch:
            pid = c.get('link_id', '').replace('t3_', '')
            if pid in post_id_set:
                all_comments.append(c)
        if len(batch) < 100:
            break
        earliest = batch[-1]['created_utc']
        cur_before = datetime.fromtimestamp(earliest - 1, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        time.sleep(0.2)
    return all_comments

# ── Markdown conversion ───────────────────────────────────────────────────────

def posts_to_markdown(subreddit, year, month, posts, comments_by_post):
    lines = [
        f"# r/{subreddit} — {year}-{month:02d}",
        f"**Posts:** {len(posts)} | **Source:** Arctic Shift (Reddit archive)",
        ""
    ]
    for p in posts:
        ts = datetime.fromtimestamp(p.get('created_utc', 0), tz=timezone.utc)
        score = p.get('score', 0)
        title = p.get('title', '').strip()
        body  = (p.get('selftext', '') or '').strip()
        body  = body[:800] if body else ''  # cap post body
        pid   = p.get('id', '')

        lines.append(f"## {title}")
        lines.append(f"*{ts.strftime('%Y-%m-%d')} · score:{score} · id:{pid}*")
        if body and body not in ('[deleted]', '[removed]'):
            lines.append(body)

        comments = comments_by_post.get(pid, [])
        # Sort by score, take top N
        comments = sorted(comments, key=lambda c: c.get('score', 0), reverse=True)[:MAX_COMMENTS_PER_POST]
        if comments:
            lines.append("**Top comments:**")
            for c in comments:
                author = c.get('author', '[deleted]')
                cbody  = (c.get('body', '') or '').strip().replace('\n', ' ')[:300]
                cscore = c.get('score', 0)
                if cbody and cbody not in ('[deleted]', '[removed]'):
                    lines.append(f"- [{cscore}] {author}: {cbody}")
        lines.append("")
    return '\n'.join(lines)

def split_markdown_chunks(text, max_kb=MAX_CHUNK_KB):
    """Split markdown into chunks under max_kb KB."""
    max_bytes = max_kb * 1024
    if len(text.encode('utf-8')) <= max_bytes:
        return [text]

    sections = re.split(r'\n(?=## )', text)
    chunks, current = [], ''
    for sec in sections:
        candidate = current + '\n' + sec if current else sec
        if len(candidate.encode('utf-8')) > max_bytes and current:
            chunks.append(current)
            current = sec
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]

# ── NotebookLM upload ─────────────────────────────────────────────────────────

def refresh_csrf():
    from pathlib import Path
    import re
    storage = json.loads(Path('/home/node/.notebooklm/profiles/default/storage_state.json').read_text())
    cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in storage.get('cookies', []))
    from urllib.request import Request, urlopen
    req = Request('https://notebooklm.google.com/', headers={
        'Cookie': cookie_str,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    })
    with urlopen(req, timeout=20) as r:
        content = r.read().decode('utf-8', errors='replace')
    csrf = re.search(r'"SNlM0e":"([^"]+)"', content)
    sid  = re.search(r'"FdrFJe":"(-?\d+)"', content)
    if csrf and sid:
        Path('/home/node/.notebooklm/chrome_tokens.json').write_text(
            json.dumps({"csrf": csrf.group(1), "sid": sid.group(1)}))
        return True
    return False

async def upload_chunks_to_notebook(nb_id, chunks, base_title):
    from notebooklm.client import NotebookLMClient
    from notebooklm.auth import AuthTokens

    storage = json.loads(Path('/home/node/.notebooklm/profiles/default/storage_state.json').read_text())
    cookies = {c['name']: c['value'] for c in storage.get('cookies', [])}
    tokens  = json.loads(Path('/home/node/.notebooklm/chrome_tokens.json').read_text())
    auth = AuthTokens(cookies=cookies, csrf_token=tokens['csrf'], session_id=tokens['sid'])

    uploaded = []
    async with NotebookLMClient(auth) as client:
        for i, chunk in enumerate(chunks):
            title = base_title if len(chunks) == 1 else f"{base_title} (part {i+1})"
            try:
                src = await client.sources.add_text(nb_id, title, chunk, wait=False)
                uploaded.append(src.id)
                print(f"      uploaded: {title} ({len(chunk)//1024}KB) → {src.id[:8]}...")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"      ERROR uploading {title}: {e}")
    return uploaded

# ── Status tracking ───────────────────────────────────────────────────────────

def load_status():
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {}

def save_status(status):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2))

def is_done(status, subreddit, year, month):
    key = f"{subreddit}_{year}_{month:02d}"
    return status.get(key, {}).get('uploaded', False)

def mark_done(status, subreddit, year, month, post_count, source_ids):
    key = f"{subreddit}_{year}_{month:02d}"
    status[key] = {
        'uploaded': True, 'post_count': post_count,
        'source_ids': source_ids,
        'ts': datetime.now(timezone.utc).isoformat()
    }

# ── Main pipeline ─────────────────────────────────────────────────────────────

async def process_subreddit_month(nb_id, subreddit, year, month, status, resume):
    if resume and is_done(status, subreddit, year, month):
        print(f"    [skip] {subreddit} {year}-{month:02d} already uploaded")
        return 0

    print(f"  [{subreddit}] {year}-{month:02d}: fetching posts...")
    posts = fetch_posts_month(subreddit, year, month)
    if not posts:
        print(f"    → 0 posts, skipping")
        mark_done(status, subreddit, year, month, 0, [])
        save_status(status)
        return 0

    post_ids = [p['id'] for p in posts]
    print(f"    → {len(posts)} posts, fetching comments...")
    raw_comments = fetch_comments_for_posts(post_ids, subreddit, year, month)

    # Group comments by post
    comments_by_post = {}
    for c in raw_comments:
        pid = c.get('link_id', '').replace('t3_', '')
        comments_by_post.setdefault(pid, []).append(c)

    total_comments = sum(len(v) for v in comments_by_post.values())
    print(f"    → {total_comments} comments, converting to markdown...")

    md = posts_to_markdown(subreddit, year, month, posts, comments_by_post)
    chunks = split_markdown_chunks(md)

    base_title = f"r/{subreddit} — {year}-{month:02d}"
    print(f"    → {len(chunks)} chunk(s), uploading to NotebookLM...")

    # Refresh tokens before each upload batch
    refresh_csrf()

    # Refresh tokens immediately before upload
    refresh_csrf()
    source_ids = await upload_chunks_to_notebook(nb_id, chunks, base_title)
    mark_done(status, subreddit, year, month, len(posts), source_ids)
    save_status(status)

    print(f"    ✓ {subreddit} {year}-{month:02d}: {len(posts)} posts, {total_comments} comments, {len(chunks)} source(s)")
    return len(posts)

async def run(target_category=None, resume=True):
    notebooks = json.loads(NOTEBOOKS_CFG.read_text())
    status = load_status()

    # Date range: last 12 months
    now = datetime.now(timezone.utc)
    months = []
    for i in range(12):
        d = now - timedelta(days=30 * i)
        months.append((d.year, d.month))
    months.reverse()  # oldest first

    grand_total = 0
    cats = {target_category: CATEGORIES[target_category]} if target_category else CATEGORIES

    for cat, subs in cats.items():
        print(f"\n{'='*60}")
        print(f"CATEGORY: {cat} | Subreddits: {len(subs)}")
        print(f"{'='*60}")

        for sub in subs:
            # Each subreddit has its own dedicated notebook (key: "sub:{subreddit}")
            # DO NOT use the category key — those notebooks are full
            per_sub_key = "sub:" + sub
            nb_id = notebooks.get(per_sub_key)
            if not nb_id:
                print(f"  WARNING: no notebook ID for {per_sub_key}, skipping")
                continue
            print(f"\n  Subreddit: r/{sub} → notebook {nb_id[:8]}...")
            sub_total = 0
            for year, month in months:
                n = await process_subreddit_month(nb_id, sub, year, month, status, resume)
                sub_total += n
                time.sleep(0.5)  # brief pause between months
            print(f"  r/{sub} TOTAL: {sub_total:,} posts loaded")
            grand_total += sub_total

    print(f"\n{'='*60}")
    print(f"HARVEST COMPLETE — {grand_total:,} posts total")
    print(f"Status file: {STATUS_FILE}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', default=None, help='Run only one category')
    parser.add_argument('--no-resume', action='store_true', help='Re-harvest even if already done')
    args = parser.parse_args()

    HARVEST_DIR.mkdir(parents=True, exist_ok=True)
    MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

    asyncio.run(run(
        target_category=args.category,
        resume=not args.no_resume
    ))

if __name__ == '__main__':
    main()
