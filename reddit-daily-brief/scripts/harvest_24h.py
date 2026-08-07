#!/usr/bin/env python3
"""
harvest_24h.py — Harvest last 24h of Reddit posts + comments for all configured subreddits.

Reads config from config/default_config.json (or --config path).
Outputs: one JSON file per subreddit to <output_dir>/<subreddit>.json
"""

import json, time, sys, os, argparse, gzip, random, re, html
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import datetime, timezone, timedelta
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
BASE_URL   = 'https://oauth.reddit.com'
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)

_consecutive_errors = 0


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / 'config/default_config.json'
    with open(p) as f:
        return json.load(f)


def resolve_cookies_file(primary, cli_override=None):
    """Resolve cookies path: CLI override → config primary → durable skill fallback."""
    candidates = []
    if cli_override:
        candidates.append(os.path.expanduser(cli_override))
    if primary:
        candidates.append(os.path.expanduser(primary))
    # Durable fallback under skill config (survives /tmp wipe)
    candidates.append(str(SKILL_DIR / 'config' / 'reddit_cookies.json'))

    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.exists(path):
            print(f'  [auth] cookies file: {path}')
            return path
        print(f'  [auth] cookies missing: {path}')
    print('  [info] No cookies file found — using public Reddit API')
    return None


def harvest_mode(token):
    """Map auth token to explicit harvest mode for manifest (A2 degrade signal)."""
    if token == '__public__':
        return 'rss'
    if token:
        return 'oauth'
    return 'public_json'


def is_fresh_harvest(out_file, lookback_hours):
    """True if JSON exists and harvested_at is within lookback window (A1 resume age-check)."""
    try:
        with open(out_file) as f:
            data = json.load(f)
        harvested_at = data.get('harvested_at')
        if not harvested_at:
            return False, data
        # Parse ISO (handle Z and offsets)
        ts = harvested_at.replace('Z', '+00:00')
        harvested_dt = datetime.fromisoformat(ts)
        if harvested_dt.tzinfo is None:
            harvested_dt = harvested_dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - harvested_dt
        if age <= timedelta(hours=lookback_hours):
            return True, data
        print(f'  [resume] stale harvest ({age.total_seconds()/3600:.1f}h old) — re-harvesting')
        return False, data
    except Exception as e:
        print(f'  [resume] could not parse existing file ({e}) — re-harvesting')
        return False, None


def load_auth(cookies_file):
    # If cookies file missing, fall back to public Reddit API directly
    if not cookies_file or not os.path.exists(cookies_file):
        print('  [info] No cookies file found — using public Reddit API')
        return '__public__', ''
    with open(cookies_file) as f:
        cookies = json.load(f)
    token = cookies.get('token_v2', '')
    cookie_str = '; '.join(f'{k}={v}' for k, v in cookies.items())
    if not token:
        print('  [warn] No token_v2 in cookies — using public Reddit API')
        return '__public__', cookie_str
    # Check token expiry — fall back to public API if expired
    try:
        import base64, time as _time
        payload_b64 = token.split('.')[1] + '=='
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get('exp', 0) < _time.time():
            print('  [warn] token_v2 is expired — switching to public Reddit API (no auth required)')
            return '__public__', cookie_str
    except Exception:
        pass
    return token, cookie_str


def safe_delay(mn=0.5, mx=1.2):
    time.sleep(random.uniform(mn, mx))


def api_get(path, token, cookie_str, retries=3):
    global _consecutive_errors
    # Use public API if token is expired/unavailable
    if token == '__public__':
        url = 'https://www.reddit.com' + path
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json',
        }
    else:
        url = f'{BASE_URL}{path}'
        headers = {
            'Authorization': f'Bearer {token}',
            'Cookie': cookie_str,
            'User-Agent': USER_AGENT,
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=20) as resp:
                remaining = float(resp.headers.get('X-Ratelimit-Remaining', 60))
                reset_secs = float(resp.headers.get('X-Ratelimit-Reset', 0))
                if remaining < 8:
                    pause = reset_secs + random.uniform(1, 3)
                    print(f'  [rate limit] {remaining:.0f} left — pausing {pause:.0f}s')
                    time.sleep(pause)
                _consecutive_errors = 0
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except HTTPError as e:
            _consecutive_errors += 1
            if e.code == 429:
                retry_after = e.headers.get('Retry-After')
                wait = int(retry_after) if retry_after else (60 * (2 ** attempt))
                wait += random.uniform(5, 15)
                print(f'  [429] rate limited — waiting {wait:.0f}s')
                time.sleep(wait)
            elif e.code == 401:
                print('  [401] Token expired — retrying with public API')
                token = '__public__'
                url = 'https://www.reddit.com' + path
                headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
                req = Request(url, headers=headers)
            elif e.code in (403, 404):
                _consecutive_errors = 0
                return None
            elif e.code >= 500:
                time.sleep(10 * (attempt + 1))
            else:
                if attempt == retries - 1:
                    return None
                time.sleep(5)
            if _consecutive_errors >= 4:
                print(f'  [circuit breaker] cooling off 120s')
                time.sleep(120)
                _consecutive_errors = 0
        except Exception as e:
            _consecutive_errors += 1
            print(f'  [error] {e}')
            if attempt == retries - 1:
                return None
            time.sleep(5 * (attempt + 1))
    return None


def classify_post_type(post):
    if post.get('is_video'): return 'video'
    if post.get('is_self'): return 'text'
    url = post.get('url', '')
    if any(url.lower().endswith(ext) for ext in ('.jpg','.jpeg','.png','.gif','.webp')):
        return 'image'
    if 'gallery' in url: return 'gallery'
    return 'link'


ATOM_NS = {'a': 'http://www.w3.org/2005/Atom'}


def _strip_html(raw):
    """Reddit RSS <content> is HTML — reduce to readable text."""
    if not raw:
        return ''
    txt = html.unescape(raw)
    # Reddit wraps self-text in a table with a "[link] [comments]" footer; drop tags.
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = html.unescape(txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt


def _rss_get(url, retries=5):
    """GET a Reddit RSS feed with browser UA and 429 backoff.

    Reddit blocks the JSON/OAuth API from datacenter IPs but serves the Atom
    RSS feed (heavily throttled — ~1 request / 45s). Returns raw XML or None.
    """
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
        ),
        'Accept': 'application/atom+xml,application/xml,text/xml,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=25) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return raw.decode('utf-8', 'replace')
        except HTTPError as e:
            if e.code == 429:
                wait = 30 * (attempt + 1) + random.uniform(3, 10)
                print(f'    [429 rss] throttled — waiting {wait:.0f}s (attempt {attempt+1}/{retries})')
                time.sleep(wait)
            elif e.code in (403, 404):
                return None
            else:
                time.sleep(8 * (attempt + 1))
        except Exception as e:
            print(f'    [rss error] {e}')
            time.sleep(8 * (attempt + 1))
    return None


def fetch_new_posts_rss(subreddit, max_posts, cutoff_ts):
    """Fetch recent posts via the Atom RSS feed (no comments/score available)."""
    url = f'https://www.reddit.com/r/{subreddit}/new/.rss?limit={min(max_posts, 100)}'
    print(f'  [rss] Fetching r/{subreddit} (cutoff: {datetime.fromtimestamp(cutoff_ts).isoformat()})...')
    raw = _rss_get(url)
    if not raw:
        print(f'    0 posts collected from r/{subreddit} (rss unavailable)')
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f'    [rss parse error] {e}')
        return []

    posts = []
    for entry in root.findall('a:entry', ATOM_NS):
        def _t(tag):
            el = entry.find(f'a:{tag}', ATOM_NS)
            return (el.text or '') if el is not None else ''

        pub = _t('published') or _t('updated')
        try:
            created_dt = datetime.fromisoformat(pub.replace('Z', '+00:00'))
            created_ts = created_dt.timestamp()
        except Exception:
            continue
        if created_ts < cutoff_ts:
            continue

        raw_id = _t('id')  # e.g. "t3_abc123"
        pid = raw_id.split('_', 1)[1] if '_' in raw_id else raw_id
        author_el = entry.find('a:author/a:name', ATOM_NS)
        author = author_el.text if author_el is not None else '[unknown]'
        if author.startswith('/u/'):
            author = author[3:]
        link_el = entry.find('a:link', ATOM_NS)
        permalink = link_el.get('href') if link_el is not None else ''
        content_el = entry.find('a:content', ATOM_NS)
        body = _strip_html(content_el.text if content_el is not None else '')
        # Trim Reddit's trailing "submitted by /u/... [link] [comments]" boilerplate
        body = re.sub(r'submitted by\s+/u/\S+.*$', '', body).strip()

        posts.append({
            'id': pid,
            'title': _t('title'),
            'stats': {
                'score': None,
                'upvote_ratio': None,
                'num_comments': None,
                'flair': '',
                'post_type': 'link',
                'author': author,
                'created_utc': created_dt.astimezone(timezone.utc).isoformat(),
                'awards': 0,
                'crossposts': 0,
                'is_nsfw': False,
                'url': permalink,
                'permalink': permalink,
                'source': 'rss',
            },
            'body': body,
            'comments': [],
        })
        if len(posts) >= max_posts:
            break

    print(f'    {len(posts)} posts collected from r/{subreddit} (rss, last 24h)')
    return posts


def fetch_new_posts(subreddit, token, cookie_str, max_posts, cutoff_ts):
    """Fetch 'new' posts, stop when created_utc < cutoff_ts."""
    # Datacenter IPs are blocked on the JSON/OAuth API → use the RSS feed instead.
    if token == '__public__':
        return fetch_new_posts_rss(subreddit, max_posts, cutoff_ts)

    posts, after = [], None
    print(f'  Fetching new posts from r/{subreddit} (cutoff: {datetime.fromtimestamp(cutoff_ts).isoformat()})...')

    while len(posts) < max_posts:
        batch = min(100, max_posts - len(posts))
        path = f'/r/{subreddit}/new?limit={batch}&raw_json=1'
        if after:
            path += f'&after={after}'

        data = api_get(path, token, cookie_str)
        if not data:
            break

        children = data['data']['children']
        if not children:
            break

        stop = False
        for child in children:
            p = child['data']
            if p['created_utc'] < cutoff_ts:
                stop = True
                break
            created = datetime.fromtimestamp(p['created_utc'], tz=timezone.utc).isoformat()
            posts.append({
                'id': p['id'],
                'title': p['title'],
                'stats': {
                    'score': p['score'],
                    'upvote_ratio': round(p.get('upvote_ratio', 0), 3),
                    'num_comments': p['num_comments'],
                    'flair': p.get('link_flair_text') or '',
                    'post_type': classify_post_type(p),
                    'author': p.get('author', '[deleted]'),
                    'created_utc': created,
                    'awards': p.get('total_awards_received', 0),
                    'crossposts': p.get('num_crossposts', 0),
                    'is_nsfw': p.get('over_18', False),
                    'url': p.get('url', ''),
                    'permalink': f"https://reddit.com{p.get('permalink', '')}",
                },
                'body': (p.get('selftext', '') or '').strip(),
                'comments': [],
            })

        if stop:
            break
        after = data['data'].get('after')
        print(f'    {len(posts)} posts within 24h...', end='\r', flush=True)
        if not after:
            break
        safe_delay()

    print(f'    {len(posts)} posts collected from r/{subreddit}')
    return posts


def flatten_comments(children, depth=0, max_depth=6):
    result = []
    for item in children:
        if not isinstance(item, dict): continue
        if item.get('kind') == 'more': continue
        c = item.get('data', {})
        body = (c.get('body') or '').strip()
        if not body or body in ('[deleted]', '[removed]'): continue
        created = ''
        if c.get('created_utc'):
            created = datetime.fromtimestamp(c['created_utc'], tz=timezone.utc).isoformat()
        result.append({
            'comment_id': c.get('id', ''),
            'body': body,
            'score': c.get('score', 0),
            'depth': depth,
            'author': c.get('author', '[deleted]'),
            'created_utc': created,
            'is_op': c.get('is_submitter', False),
            'awards': c.get('total_awards_received', 0),
        })
        if depth < max_depth:
            replies = c.get('replies')
            if isinstance(replies, dict):
                sub = replies.get('data', {}).get('children', [])
                result.extend(flatten_comments(sub, depth + 1, max_depth))
    return result


def attach_comments(post, subreddit, token, cookie_str, limit):
    path = f'/r/{subreddit}/comments/{post["id"]}?limit={limit}&depth=6&raw_json=1&sort=top'
    try:
        data = api_get(path, token, cookie_str)
        if not data or len(data) < 2:
            return
        children = data[1]['data']['children']
        post['comments'] = flatten_comments(children)
    except Exception as e:
        print(f'\n    [warn] comments failed for {post["id"]}: {e}')


def main():
    parser = argparse.ArgumentParser(description='Harvest last 24h of Reddit posts')
    parser.add_argument('--config', default=None, help='Path to config JSON')
    parser.add_argument('--output', default=None, help='Output directory')
    parser.add_argument('--subreddit', default=None, help='Run single subreddit only')
    parser.add_argument('--resume', action='store_true',
                        help='Skip subreddits with fresh harvest within lookback_hours')
    parser.add_argument('--cookies', default=None,
                        help='Override path to reddit cookies JSON')
    args = parser.parse_args()

    cfg = load_config(args.config)
    reddit_cfg = cfg['reddit']

    out_dir = Path(args.output) if args.output else SKILL_DIR / 'outputs/daily'
    out_dir.mkdir(parents=True, exist_ok=True)

    lookback = reddit_cfg.get('lookback_hours', 24)
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=lookback)).timestamp()
    max_posts = reddit_cfg.get('posts_per_subreddit', 50)
    max_comments = reddit_cfg.get('comments_per_post', 20)

    cookies_path = resolve_cookies_file(
        reddit_cfg.get('cookies_file'),
        cli_override=args.cookies,
    )
    token, cookie_str = load_auth(cookies_path)
    mode = harvest_mode(token)
    print(f'  [harvest] mode={mode}')

    # Build flat subreddit list with notebook name
    targets = []
    for nb in cfg['notebooks']:
        for sub in nb['subreddits']:
            targets.append((nb['name'], sub))

    if args.subreddit:
        sub_clean = args.subreddit.strip().lstrip('r/')
        targets = [(nb, s) for nb, s in targets if s.lower() == sub_clean.lower()]
        if not targets:
            print(f'ERROR: {args.subreddit} not in config')
            return

    results = {}
    total = len(targets)

    for i, (notebook_name, subreddit) in enumerate(targets):
        print(f'\n[{i+1}/{total}] r/{subreddit}  ({notebook_name})')

        try:
            out_file = out_dir / f'{subreddit}.json'
            # A1: --resume only skips if file is fresh within lookback window
            if args.resume and out_file.exists():
                fresh, existing = is_fresh_harvest(out_file, lookback)
                if fresh:
                    print(f'  [resume] fresh harvest within {lookback}h — skipping')
                    results[subreddit] = {
                        'notebook': notebook_name,
                        'posts': existing.get('stats', {}).get('posts', 0) if existing else 0,
                        'comments': existing.get('stats', {}).get('comments', 0) if existing else 0,
                    }
                    continue

            posts = fetch_new_posts(subreddit, token, cookie_str, max_posts, cutoff_ts)

            if not posts:
                print(f'  No posts in last {lookback}h — skipping')
                results[subreddit] = {'notebook': notebook_name, 'posts': 0, 'comments': 0}
                continue

            if token == '__public__':
                # RSS mode: no comment API available on this IP. A2 explicit degrade.
                print(f'  [rss] comments unavailable via RSS — posts only (mode={mode})')
            else:
                print(f'  Fetching comments ({max_comments}/post)...')
                for j, post in enumerate(posts):
                    print(f'    [{j+1}/{len(posts)}] {post["title"][:55]}...', end='\r', flush=True)
                    attach_comments(post, subreddit, token, cookie_str, max_comments)
                    safe_delay()

            total_comments = sum(len(p['comments']) for p in posts)
            print(f'\n  {total_comments} comments collected.')

            output = {
                'subreddit': subreddit,
                'notebook': notebook_name,
                'harvested_at': datetime.now(timezone.utc).isoformat(),
                'lookback_hours': lookback,
                'mode': mode,
                'stats': {
                    'posts': len(posts),
                    'comments': total_comments,
                    'avg_score': round(sum(s for p in posts if (s := p['stats'].get('score')) is not None) / len(posts), 1) if any(p['stats'].get('score') is not None for p in posts) else None,
                },
                'posts': posts,
            }

            out_file = out_dir / f'{subreddit}.json'
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f'  Saved: {out_file}  ({os.path.getsize(out_file)//1024}KB)')
            results[subreddit] = {'notebook': notebook_name, 'posts': len(posts), 'comments': total_comments}

        except Exception as e:
            print(f'\n  ERROR on r/{subreddit}: {e}')
            results[subreddit] = {'notebook': notebook_name, 'error': str(e)}

        if i < total - 1:
            # RSS feed is throttled to ~1 req/45s on this IP; JSON path can go faster.
            gap = random.uniform(48, 58) if token == '__public__' else random.uniform(5, 12)
            print(f'  [cooldown] {gap:.0f}s before next...')
            time.sleep(gap)

    # Summary
    print(f'\n=== Harvest complete ===')
    total_posts = sum(v.get('posts', 0) for v in results.values())
    total_cmts = sum(v.get('comments', 0) for v in results.values())
    print(f'  Subreddits: {len(results)} | Posts: {total_posts} | Comments: {total_cmts}')
    print(f'  Mode: {mode}')
    print(f'  Output: {out_dir}')

    # Save manifest — A2: mode makes RSS/oauth degrade explicit
    manifest = {
        'harvested_at': datetime.now(timezone.utc).isoformat(),
        'lookback_hours': lookback,
        'mode': mode,
        'output_dir': str(out_dir),
        'subreddits': results,
    }
    manifest_path = out_dir / '_manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'  Manifest: {manifest_path}')


if __name__ == '__main__':
    main()
