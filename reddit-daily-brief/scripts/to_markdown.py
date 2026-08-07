#!/usr/bin/env python3
"""
to_markdown.py — Convert daily harvest JSON files to readable Markdown.

Produces one .md file per subreddit (lightweight, zero token cost for NotebookLM).
Also produces one combined .md per notebook category.
"""

import json, argparse, os
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent.parent


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / 'config/default_config.json'
    with open(p) as f:
        return json.load(f)


def post_to_md(post):
    lines = []
    s = post['stats']
    score = s['score'] if s.get('score') is not None else 'n/a'
    ncom = s['num_comments'] if s.get('num_comments') is not None else 'n/a'
    lines.append(f"### {post['title']}")
    lines.append(f"**Score:** {score} | **Comments:** {ncom} | "
                 f"**Type:** {s['post_type']} | **Author:** u/{s['author']} | "
                 f"**Date:** {s['created_utc'][:10]}")
    if s.get('flair'):
        lines.append(f"**Flair:** {s['flair']}")
    lines.append(f"**URL:** {s['permalink']}")
    if post.get('body'):
        lines.append('')
        lines.append(post['body'])
    if post.get('comments'):
        lines.append('')
        lines.append('**Top Comments:**')
        for c in post['comments'][:10]:  # top 10 comments per post in md
            indent = '  ' * c.get('depth', 0)
            op_tag = ' [OP]' if c.get('is_op') else ''
            lines.append(f'{indent}- **{c["score"]} pts** u/{c["author"]}{op_tag}: {c["body"][:300]}')
    return '\n'.join(lines)


def json_to_md(json_path):
    with open(json_path) as f:
        data = json.load(f)

    sub = data['subreddit']
    nb = data.get('notebook', '')
    harvested = data.get('harvested_at', '')[:19]
    lookback = data.get('lookback_hours', 24)
    stats = data.get('stats', {})
    posts = data.get('posts', [])

    lines = [
        f"# r/{sub} — Daily Activity",
        f"",
        f"**Notebook:** {nb}",
        f"**Harvested:** {harvested} UTC | **Lookback:** {lookback}h",
        f"**Posts:** {stats.get('posts', len(posts))} | "
        f"**Comments:** {stats.get('comments', 0)} | "
        f"**Avg Score:** {stats.get('avg_score', 0)}",
        f"",
        f"---",
        f"",
    ]

    for post in posts:
        lines.append(post_to_md(post))
        lines.append('')
        lines.append('---')
        lines.append('')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=None)
    parser.add_argument('--input-dir', default=None, help='Dir with daily JSON files')
    parser.add_argument('--output-dir', default=None, help='Where to write .md files')
    parser.add_argument('--date', default=None,
                        help='Date stamp for combined filenames (YYYY-MM-DD). Default: UTC today')
    args = parser.parse_args()

    cfg = load_config(args.config)

    in_dir  = Path(args.input_dir) if args.input_dir else SKILL_DIR / 'outputs/daily'
    out_dir = Path(args.output_dir) if args.output_dir else SKILL_DIR / 'outputs/markdown'
    out_dir.mkdir(parents=True, exist_ok=True)

    # A4: date coupling — combined files use pipeline/CLI date, not wall-clock only
    if args.date:
        date_str = args.date.strip()
        # light validation
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            print(f'ERROR: --date must be YYYY-MM-DD, got {args.date!r}')
            return
    else:
        date_str = datetime.utcnow().strftime('%Y-%m-%d')

    # Build subreddit → notebook map
    sub_to_notebook = {}
    for nb in cfg['notebooks']:
        for sub in nb['subreddits']:
            sub_to_notebook[sub] = nb['name']

    # Per-subreddit markdown
    notebook_texts = {}  # notebook_name → list of md texts

    json_files = sorted(in_dir.glob('*.json'))
    if not json_files:
        print(f'No JSON files found in {in_dir}')
        return

    for jf in json_files:
        if jf.name.startswith('_'):
            continue
        sub = jf.stem
        print(f'  Converting {sub}.json → {sub}.md')
        md = json_to_md(jf)
        md_path = out_dir / f'{sub}.md'
        md_path.write_text(md, encoding='utf-8')

        nb_name = sub_to_notebook.get(sub, 'Other')
        notebook_texts.setdefault(nb_name, []).append(md)

    # Per-notebook combined markdown (for upload as single source)
    combined_dir = out_dir / 'combined'
    combined_dir.mkdir(exist_ok=True)

    for nb_name, texts in notebook_texts.items():
        safe_name = nb_name.replace(' ', '_').replace('&', 'and')
        combined_path = combined_dir / f'{safe_name}_{date_str}.md'
        header = f"# {nb_name} — Daily Digest {date_str}\n\n"
        combined_path.write_text(header + '\n\n'.join(texts), encoding='utf-8')
        size_kb = os.path.getsize(combined_path) // 1024
        print(f'  Combined: {combined_path.name}  ({size_kb}KB)')

    print(f'\nMarkdown written to: {out_dir}')
    return str(out_dir)


if __name__ == '__main__':
    main()
