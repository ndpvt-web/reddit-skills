#!/usr/bin/env python3
"""
query_compose.py — Query NotebookLM notebooks, build QA JSON, compose email.

Usage:
    python3 query_compose.py --date 2026-04-26 --output /path/email.md
    python3 query_compose.py --gateway-first --date 2026-04-26
    python3 query_compose.py --strict --date 2026-04-26
"""

import json, subprocess, sys, os, argparse, re
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

SKILL_DIR = Path(__file__).parent.parent


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / 'config/default_config.json'
    with open(p) as f:
        return json.load(f)


# ── AI Gateway fallback ────────────────────────────────────────────────────
# When NotebookLM is unreachable (Mac offline / token expired), analyze the
# locally-harvested markdown directly via the AI Gateway so the brief still
# reflects REAL data instead of empty "No data" rows.

def _combined_md_path(date_str, nb_name):
    safe = nb_name.replace(' ', '_').replace('&', 'and')
    return SKILL_DIR / 'outputs/markdown/combined' / f'{safe}_{date_str}.md'


def read_combined_md(date_str, nb_name, max_chars=60000):
    p = _combined_md_path(date_str, nb_name)
    if not p.exists():
        return ''
    txt = p.read_text(encoding='utf-8', errors='replace')
    return txt[:max_chars]


def gateway_ask(question, context_md):
    """Ask the AI Gateway to answer `question` grounded in `context_md`.

    Returns answer text, or '' on failure. Mirrors nlm_ask's contract so it
    can be a drop-in fallback.
    """
    base = os.environ.get('AI_GATEWAY_BASE_URL', '').rstrip('/')
    key = os.environ.get('AI_GATEWAY_API_KEY', '')
    if not base or not key or not context_md.strip():
        return ''
    model = os.environ.get('REDDIT_BRIEF_MODEL', 'anthropic/claude-sonnet-4.6')
    system = (
        'You are a Reddit intelligence analyst. You are given the raw text of '
        'Reddit posts harvested in the last 24h. Analyze ONLY what is present in '
        'the provided text. Follow the requested output format exactly, one field '
        'per line, no preamble, no markdown, no extra commentary.'
    )
    user = f"{question}\n\n=== REDDIT POSTS (last 24h) ===\n{context_md}"
    payload = json.dumps({
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
        'temperature': 0.3,
    }).encode('utf-8')
    req = urllib.request.Request(
        f'{base}/api/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            # Cloudflare in front of the gateway blocks the default Python-urllib UA.
            'User-Agent': 'curl/8.4.0',
            # Gateway gzip quirk: claims Content-Encoding:gzip but body is plain JSON.
            'Accept-Encoding': 'identity',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f'  [warn] gateway_ask failed: {str(e)[:120]}')
        return ''


def nlm_ask(cfg, notebook_id, question):
    """Query a NotebookLM notebook. Returns answer text or empty string."""
    bin_path = os.path.expanduser(cfg.get('notebooklm_bin', '~/.local/bin/notebooklm'))
    profile = cfg.get('notebooklm_profile', '')
    profile_args = ['--profile', profile] if profile else []
    cmd = [bin_path] + profile_args + ['ask', '--notebook', notebook_id, question]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return r.stdout.strip()
        else:
            print(f'  [warn] ask failed for {notebook_id}: {r.stderr[:100]}')
            return ''
    except subprocess.TimeoutExpired:
        print(f'  [warn] ask timed out for {notebook_id}')
        return ''
    except Exception as e:
        print(f'  [warn] ask error: {e}')
        return ''


def resolve_query_mode(cfg, args):
    """Return 'gateway' or 'nlm' (default NLM-first with gateway fallback).

    Priority: --gateway-first flag > env REDDIT_BRIEF_QUERY_MODE > config query_mode.
    """
    if getattr(args, 'gateway_first', False):
        return 'gateway'
    env_mode = (os.environ.get('REDDIT_BRIEF_QUERY_MODE') or '').strip().lower()
    if env_mode == 'gateway':
        return 'gateway'
    cfg_mode = str(cfg.get('query_mode', '') or '').strip().lower()
    if cfg_mode == 'gateway':
        return 'gateway'
    return 'nlm'


def is_empty_brief(categories) -> bool:
    """True when every category is effectively empty (auth/data failure).

    Empty if:
    - all dominant_mood == 'No data', OR
    - every category has post_count == 0 AND no top_discussions, OR
    - all categories with post_count > 0 have empty top_discussions
      (and categories with post_count==0 also lack discussions)
    """
    if not categories:
        return True

    if all((c.get('dominant_mood') or '') == 'No data' for c in categories):
        return True

    # Zero posts everywhere and no discussions → empty (even if moods differ)
    if all((c.get('post_count') or 0) == 0 for c in categories) and all(
        not c.get('top_discussions') for c in categories
    ):
        return True

    # Posts present but analysis produced no discussions across the board
    any_posts = any((c.get('post_count') or 0) > 0 for c in categories)
    if any_posts:
        for c in categories:
            if (c.get('post_count') or 0) > 0 and c.get('top_discussions'):
                return False
        return True

    # No posts anywhere and no discussions either
    if all(not c.get('top_discussions') for c in categories):
        # Treat as empty only when moods are missing/No data too
        if all((c.get('dominant_mood') or 'No data') in ('', 'No data') for c in categories):
            return True

    return False


def parse_field(text, label):
    """Extract a labelled field from structured response text."""
    pattern = rf'^{re.escape(label)}:\s*(.+)$'
    m = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ''


def parse_int_field(text, label, default=0):
    val = parse_field(text, label)
    try:
        return int(re.sub(r'[^-\d]', '', val.split('/')[0]))
    except Exception:
        return default


def _empty_category(nb_name, subs, post_count):
    return {
        'name': nb_name,
        'sentiment_score': 0,
        'dominant_mood': 'No data',
        'subreddits': subs,
        'post_count': post_count,
        'top_discussions': [],
        'key_frustrations': [],
        'positive_signals': [],
        'viral_thread': '',
        'controversy': '',
    }


def _parse_category_answer(answer, nb_name, subs, post_count):
    score = parse_int_field(answer, 'SCORE', 0)
    score = max(-10, min(10, score))

    discussions = []
    for i in range(1, 4):
        d = parse_field(answer, f'DISCUSSION_{i}')
        if d:
            discussions.append(d)

    frustrations = []
    for i in range(1, 3):
        f = parse_field(answer, f'FRUSTRATION_{i}')
        if f:
            frustrations.append(f)

    positives = []
    for i in range(1, 3):
        p = parse_field(answer, f'POSITIVE_{i}')
        if p:
            positives.append(p)

    viral = parse_field(answer, 'VIRAL')
    controversy = parse_field(answer, 'CONTROVERSY')
    if controversy.upper() == 'NONE':
        controversy = ''

    return {
        'name': nb_name,
        'sentiment_score': score,
        'dominant_mood': parse_field(answer, 'MOOD') or 'Mixed',
        'subreddits': subs,
        'post_count': post_count,
        'top_discussions': discussions,
        'key_frustrations': frustrations,
        'positive_signals': positives,
        'viral_thread': viral,
        'controversy': controversy,
    }


def _count_daily_posts(daily_dir, subs):
    """Sum post_count from undated outputs/daily/*.json for the given subs."""
    post_count = 0
    for sub in subs:
        for fname in [f'{sub}.json', f'{sub.lower()}.json']:
            fp = Path(daily_dir) / fname
            if fp.exists():
                try:
                    d = json.loads(fp.read_text())
                    post_count += d.get('post_count', len(d.get('posts', [])))
                except Exception:
                    pass
                break
    return post_count


def query_category(cfg, nb_cfg, daily_dir, date_str, query_mode='nlm'):
    """Query a category notebook for sentiment analysis."""
    nb_id   = nb_cfg['id']
    nb_name = nb_cfg['name']
    subs    = nb_cfg.get('subreddits', [])

    # Combined MD is date-scoped; undated daily/*.json is not. Only trust
    # daily post counts when date-matched combined MD exists for this category.
    md = read_combined_md(date_str, nb_name)
    has_combined_md = bool(md.strip())
    post_count = _count_daily_posts(daily_dir, subs) if has_combined_md else 0

    print(f'  Querying: {nb_name} (id={nb_id[:8]}...)')

    question = (
        f"Analyze the Reddit posts from {date_str} in this notebook. "
        "Answer EXACTLY in this format — one field per line, no extra text:\n"
        "SCORE: <integer from -10 to +10>\n"
        "MOOD: <3-5 word phrase describing dominant mood>\n"
        "DISCUSSION_1: <most upvoted/engaged topic, one sentence>\n"
        "DISCUSSION_2: <second top topic, one sentence>\n"
        "DISCUSSION_3: <third top topic, one sentence>\n"
        "FRUSTRATION_1: <top user frustration, one sentence>\n"
        "FRUSTRATION_2: <second frustration, one sentence>\n"
        "POSITIVE_1: <top positive signal, one sentence>\n"
        "POSITIVE_2: <second positive signal, one sentence>\n"
        "VIRAL: <title or description of most viral/discussed thread>\n"
        "CONTROVERSY: <any controversial debate or drama in one sentence, or NONE>"
    )

    answer = ''

    if query_mode == 'gateway':
        # Gateway-first: skip NLM, analyze local combined MD directly.
        # No date-matched combined MD → empty with post_count=0 (do not use
        # undated daily/*.json counts for a missing date).
        if has_combined_md:
            print(f'    [gateway-first] analyzing local data via AI Gateway ({post_count or "?"} posts)')
            answer = gateway_ask(question, md)
        else:
            print(f'    [gateway-first] no local combined MD for {nb_name}')
            return _empty_category(nb_name, subs, 0)
    else:
        # Default: NLM first, then gateway fallback when NLM empty.
        answer = nlm_ask(cfg, nb_id, question)
        if not answer:
            if has_combined_md:
                print(f'    [fallback] NotebookLM empty — analyzing local data via AI Gateway ({post_count or "?"} posts)')
                answer = gateway_ask(question, md)

    if not answer:
        # Empty analysis: never report undated daily counts without combined MD.
        return _empty_category(nb_name, subs, post_count if has_combined_md else 0)

    return _parse_category_answer(answer, nb_name, subs, post_count)


def query_overall(cfg, date_str, categories, query_mode='nlm'):
    """Query master notebook (first notebook) for composite score + signals."""
    # Use the first notebook in config as master, or a dedicated master if configured
    master_nb = cfg.get('master_notebook') or (cfg['notebooks'][0] if cfg.get('notebooks') else None)
    if not master_nb:
        # Derive composite from category scores
        scores = [c['sentiment_score'] for c in categories]
        composite = int(sum(scores) / len(scores)) if scores else 0
        return {
            'composite_score': composite,
            'macro_signals': [],
            'overall_summary': '',
        }

    nb_id = master_nb.get('id', '') if isinstance(master_nb, dict) else master_nb

    print(f'  Querying master notebook for overall...')
    question = (
        f"Based on ALL the Reddit posts from {date_str}, give an overall AI/tech ecosystem analysis. "
        "Answer EXACTLY in this format — one field per line:\n"
        "COMPOSITE_SCORE: <integer from -10 to +10 representing overall community sentiment>\n"
        "SIGNAL_1: <most important macro signal in one sentence>\n"
        "SIGNAL_2: <second macro signal in one sentence>\n"
        "SIGNAL_3: <third macro signal in one sentence>\n"
        "OVERALL_SUMMARY: <2-3 sentence executive summary of today's AI/tech Reddit mood>"
    )

    # Build category context for gateway path / fallback
    ctx_lines = []
    for c in categories:
        ctx_lines.append(f"## {c['name']} — sentiment {c['sentiment_score']:+d}/10 ({c.get('dominant_mood','')})")
        for d in c.get('top_discussions', []):
            ctx_lines.append(f"- discussion: {d}")
        for fr in c.get('key_frustrations', []):
            ctx_lines.append(f"- frustration: {fr}")
        for pos in c.get('positive_signals', []):
            ctx_lines.append(f"- positive: {pos}")
        if c.get('viral_thread'):
            ctx_lines.append(f"- viral: {c['viral_thread']}")
    ctx = '\n'.join(ctx_lines)

    answer = ''
    if query_mode == 'gateway':
        if ctx.strip():
            print('  [gateway-first] synthesizing overall via AI Gateway')
            answer = gateway_ask(question, ctx)
    else:
        answer = nlm_ask(cfg, nb_id, question)
        if not answer:
            # Fallback: synthesize the overall view from the per-category analyses via AI Gateway.
            if ctx.strip():
                print('  [fallback] master NotebookLM empty — synthesizing overall via AI Gateway')
                answer = gateway_ask(question, ctx)

    if not answer:
        scores = [c['sentiment_score'] for c in categories]
        composite = int(sum(scores) / len(scores)) if scores else 0
        return {
            'composite_score': composite,
            'macro_signals': [],
            'overall_summary': '',
        }

    composite = parse_int_field(answer, 'COMPOSITE_SCORE', 0)
    composite = max(-10, min(10, composite))

    signals = []
    for i in range(1, 4):
        s = parse_field(answer, f'SIGNAL_{i}')
        if s:
            signals.append(s)

    summary = parse_field(answer, 'OVERALL_SUMMARY')

    return {
        'composite_score': composite,
        'macro_signals': signals,
        'overall_summary': summary,
    }


def compose_email(cfg, date_str: str, overall: dict, categories: list, empty_warning: bool = False) -> str:
    """Concise bullet-point email. No asterisks. One point per line."""
    composite = overall.get('composite_score', 0)
    sign = '+' if composite >= 0 else ''
    summary = overall.get('overall_summary', '')

    lines = []
    if empty_warning:
        lines.append('WARNING: EMPTY BRIEF — auth/data failure suspected')
        lines.append('')

    lines += [
        f"Reddit Daily Brief — {date_str}",
        "",
        f"Overall: {sign}{composite}/10. {summary}",
        "",
    ]

    for cat in categories:
        score = cat.get('sentiment_score', 0)
        s = '+' if score >= 0 else ''
        mood = cat.get('dominant_mood', 'Mixed')
        name = cat.get('name', '')
        lines.append(f"- {name}: {s}{score}/10 — {mood}")

    lines += [
        "",
        "- See attached PDF for full analysis.",
        f"- Reddit Daily Brief — {date_str}",
    ]

    return '\n'.join(lines)


def compose_archive_summary(date_str: str, overall: dict, categories: list) -> str:
    """Compact markdown summary for archive notebook."""
    composite = overall.get('composite_score', 0)
    sign = '+' if composite >= 0 else ''
    lines = [
        f"## {date_str} — Composite {sign}{composite}/10",
        "",
        overall.get('overall_summary', ''),
        "",
    ]
    for cat in categories:
        score = cat.get('sentiment_score', 0)
        s = '+' if score >= 0 else ''
        lines.append(f"- **{cat['name']}**: {s}{score}/10 — {cat.get('dominant_mood', '')}")
    lines += [""]
    for sig in overall.get('macro_signals', []):
        lines.append(f"- {sig}")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Query NotebookLM and compose brief')
    parser.add_argument('--config', default=None)
    parser.add_argument('--date', default=None)
    parser.add_argument('--output', default=None, help='Email markdown output path')
    parser.add_argument('--archive-output', default=None)
    parser.add_argument(
        '--gateway-first',
        action='store_true',
        help='Skip NotebookLM; analyze local combined MD via AI Gateway',
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit 2 if brief is empty (all No data / no discussions)',
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    date_str = args.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    query_mode = resolve_query_mode(cfg, args)

    composed_dir = SKILL_DIR / 'outputs/composed'
    composed_dir.mkdir(parents=True, exist_ok=True)
    daily_dir = SKILL_DIR / 'outputs/daily'

    qa_path = composed_dir / f'qa_{date_str}.json'
    email_path = Path(args.output) if args.output else composed_dir / f'email_{date_str}.md'

    print(f'=== Query & Compose — {date_str} ===')
    print(f'  query_mode={query_mode} strict={args.strict}')

    categories = []
    for nb_cfg in cfg.get('notebooks', []):
        cat = query_category(cfg, nb_cfg, daily_dir, date_str, query_mode=query_mode)
        categories.append(cat)
        print(f'    {cat["name"]}: {cat["sentiment_score"]:+d}/10 — {cat["dominant_mood"]}')

    overall = query_overall(cfg, date_str, categories, query_mode=query_mode)

    empty = is_empty_brief(categories)

    qa_data = {
        'date': date_str,
        'composite_score': overall['composite_score'],
        'macro_signals': overall['macro_signals'],
        'overall_summary': overall['overall_summary'],
        'categories': categories,
        'empty_brief': empty,
        'query_mode': query_mode,
    }

    qa_path.write_text(json.dumps(qa_data, indent=2, ensure_ascii=False))
    print(f'  QA saved: {qa_path}')

    if empty and args.strict:
        print('[strict] FAIL: empty brief')
        # Still write email for forensics, but fail loudly
        email_body = compose_email(cfg, date_str, overall, categories, empty_warning=True)
        email_path.write_text(email_body, encoding='utf-8')
        print(f'  Email body saved (strict fail): {email_path}')
        if args.archive_output:
            archive_md = compose_archive_summary(date_str, overall, categories)
            Path(args.archive_output).write_text(archive_md, encoding='utf-8')
        print('=== Query & Compose FAILED (strict empty) ===')
        sys.exit(2)

    email_body = compose_email(
        cfg, date_str, overall, categories,
        empty_warning=bool(empty and not args.strict),
    )
    email_path.write_text(email_body, encoding='utf-8')
    print(f'  Email body saved: {email_path}')
    if empty:
        print('  [warn] empty brief — WARNING prefix added to email body')

    if args.archive_output:
        archive_md = compose_archive_summary(date_str, overall, categories)
        Path(args.archive_output).write_text(archive_md, encoding='utf-8')
        print(f'  Archive summary saved: {args.archive_output}')

    print('=== Query & Compose complete ===')


if __name__ == '__main__':
    main()
