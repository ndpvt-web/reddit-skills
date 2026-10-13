#!/usr/bin/env python3
"""
Convert synthesis.md into a beautiful dark-mode HTML analysis report.

Usage:
  python3 build_report.py --synthesis tmp/synthesis.md \
    --subreddit example --stats tmp/reddit_raw_full.json \
    --output outputs/report.html
"""
import argparse, json, re
from pathlib import Path


def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_fmt(s):
    s = escape(s)
    s = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', s)
    s = re.sub(r'\*\*(.+?)\*\*',     r'<strong>\1</strong>', s)
    s = re.sub(r'\*(.+?)\*',         r'<em>\1</em>', s)
    s = re.sub(r'`(.+?)`',           r'<code>\1</code>', s)
    return s


def md_to_html(text):
    lines   = text.split("\n")
    out     = []
    in_ul   = False
    in_ol   = False

    for line in lines:
        stripped = line.strip()

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:  out.append("</ul>"); in_ul = False
            if in_ol:  out.append("</ol>"); in_ol = False

        if stripped.startswith("### "):
            close_lists(); out.append(f'<h3>{inline_fmt(stripped[4:])}</h3>')
        elif stripped.startswith("## "):
            close_lists(); out.append(f'<h2>{inline_fmt(stripped[3:])}</h2>')
        elif stripped.startswith("# "):
            close_lists(); out.append(f'<h1>{inline_fmt(stripped[2:])}</h1>')
        elif re.match(r'^\d+\. ', stripped):
            if not in_ol: out.append("<ol>"); in_ol = True
            content = inline_fmt(re.sub(r'^\d+\. ', '', stripped))
            out.append(f'<li>{content}</li>')
        elif stripped.startswith(("- ", "* ")):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f'<li>{inline_fmt(stripped[2:])}</li>')
        elif stripped == "---":
            close_lists(); out.append("<hr>")
        elif stripped.startswith("> "):
            close_lists(); out.append(f'<blockquote>{inline_fmt(stripped[2:])}</blockquote>')
        elif stripped == "":
            close_lists(); out.append("")
        else:
            close_lists(); out.append(f'<p>{inline_fmt(stripped)}</p>')

    if in_ul: out.append("</ul>")
    if in_ol: out.append("</ol>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthesis",  required=True)
    ap.add_argument("--subreddit",  required=True)
    ap.add_argument("--stats",      default=None)
    ap.add_argument("--output",     default="outputs/report.html")
    args = ap.parse_args()

    synthesis = Path(args.synthesis).read_text()
    body      = md_to_html(synthesis)

    # Load stats if available
    stats = {}
    if args.stats and Path(args.stats).exists():
        data = json.loads(Path(args.stats).read_text())
        stats = data.get("summary", {})

    def display_stat(key):
        value = stats.get(key)
        return f"{value:,}" if isinstance(value, (int, float)) else "Not available"

    total_posts = display_stat('total_posts')
    unique_authors = display_stat('total_unique_authors')
    max_score = display_stat('max_score')
    period = escape(str(stats.get('period') or 'Period not provided'))
    status = escape(str(stats.get('collection_status') or 'Coverage not verified'))
    subreddit = escape(args.subreddit)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>r/{subreddit} Deep Analysis</title>
<style>
:root {{
  --bg: #0f1117; --surface: #1a1d27; --surface2: #222536;
  --border: #2d3148; --accent: #ff6b35; --accent2: #4ecdc4;
  --text: #e8eaf6; --dim: #8892b0; --green: #64ffda;
  --yellow: #ffd166; --red: #ef476f;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 16px; line-height: 1.75; }}
.hero {{ background: linear-gradient(135deg,#1a1d27,#0f1117); border-bottom: 2px solid var(--accent); padding: 56px 40px 36px; text-align: center; }}
.hero h1 {{ font-size: 2.5rem; color: var(--accent); margin-bottom: 10px; }}
.hero p {{ color: var(--dim); font-size: 1.05rem; }}
.stats-bar {{ display: flex; gap: 20px; justify-content: center; padding: 22px 40px; background: var(--surface); border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
.stat {{ text-align: center; background: var(--surface2); border: 1px solid var(--border); border-radius: 12px; padding: 14px 22px; min-width: 130px; }}
.stat-num {{ font-size: 1.7rem; font-weight: 700; color: var(--accent2); }}
.stat-label {{ font-size: .78rem; color: var(--dim); text-transform: uppercase; letter-spacing: .05em; margin-top: 4px; }}
.container {{ max-width: 920px; margin: 0 auto; padding: 40px 28px; }}
h1 {{ font-size: 2.1rem; color: var(--accent); margin: 28px 0 14px; border-bottom: 2px solid var(--accent); padding-bottom: 8px; }}
h2 {{ font-size: 1.55rem; color: var(--accent2); margin: 38px 0 14px; padding-left: 12px; border-left: 4px solid var(--accent2); }}
h3 {{ font-size: 1.15rem; color: var(--yellow); margin: 28px 0 10px; }}
p {{ margin: 10px 0; }}
ul, ol {{ margin: 10px 0 10px 26px; }}
li {{ margin: 7px 0; }}
strong {{ color: var(--green); }}
em {{ color: var(--yellow); font-style: italic; }}
code {{ background: var(--surface2); color: var(--accent); padding: 2px 6px; border-radius: 4px; font-size: .88em; font-family: monospace; }}
blockquote {{ background: var(--surface2); border-left: 4px solid var(--accent); padding: 14px 18px; margin: 18px 0; border-radius: 0 8px 8px 0; color: var(--dim); font-style: italic; }}
hr {{ border: none; border-top: 1px solid var(--border); margin: 32px 0; }}
.footer {{ text-align: center; padding: 36px; color: var(--dim); font-size: .83rem; border-top: 1px solid var(--border); margin-top: 56px; }}
</style>
</head>
<body>
<div class="hero">
  <h1>r/{subreddit} Deep Analysis</h1>
  <p>Community research &bull; {period} &bull; Collection: {status}</p>
</div>
<div class="stats-bar">
  <div class="stat"><div class="stat-num">{total_posts}</div><div class="stat-label">Total Posts</div></div>
  <div class="stat"><div class="stat-num">{unique_authors}</div><div class="stat-label">Unique Authors</div></div>
  <div class="stat"><div class="stat-num">{max_score}</div><div class="stat-label">Top Post Score</div></div>
  <div class="stat"><div class="stat-num">{status}</div><div class="stat-label">Collection Status</div></div>
</div>
<div class="container">
{body}
</div>
<div class="footer">
  Generated by subreddit-analyst skill &bull; r/{subreddit}
</div>
</body>
</html>"""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"Report saved → {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
