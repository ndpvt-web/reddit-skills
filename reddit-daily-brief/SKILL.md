# reddit-daily-brief

Automated daily Reddit intelligence pipeline. Harvests 24h activity from configured subreddits, uploads to NotebookLM, queries with AI, generates a PDF, and sends an email — every morning at 7 AM HKT.

## What It Does

1. **Refresh tokens** — re-extracts NotebookLM + Reddit cookies from Mac Chrome
2. **Harvest** — fetches last 24h posts + comments from all configured subreddits
3. **Convert** — transforms JSON to readable Markdown (zero token cost for NotebookLM)
4. **Upload** — syncs to category notebooks + master notebook (rolling 30-day window)
5. **Query** — asks NotebookLM configurable questions via the master notebook
6. **Archive** — appends daily AI summary to monthly file (permanent retention)
7. **PDF** — generates a beautiful LaTeX PDF (cover + 1 page per category + Q&A)
8. **Email** — sends hook-driven, bullet-format email via capymail

## Quick Start

```bash
# Discover online Mac bridges + extract Reddit cookies
python3 ~/.claude/skills/reddit-daily-brief/scripts/bridge_auth.py --discover
python3 ~/.claude/skills/reddit-daily-brief/scripts/bridge_auth.py --extract-cookies

# Full run (all 9 steps)
python3 ~/.claude/skills/reddit-daily-brief/scripts/pipeline.py

# Dry run = harvest + markdown ONLY (no upload / query / PDF / email)
python3 ~/.claude/skills/reddit-daily-brief/scripts/pipeline.py --dry-run

# Strict: non-zero exit + no empty email on auth/data failure
python3 ~/.claude/skills/reddit-daily-brief/scripts/pipeline.py --strict --skip-email

# Skip harvest (use existing daily output)
python3 ~/.claude/skills/reddit-daily-brief/scripts/pipeline.py --skip-harvest

# Acceptance suite
python3 ~/.claude/skills/reddit-daily-brief/scripts/acceptance_test.py

# Individual steps
python3 ~/.claude/skills/reddit-daily-brief/scripts/harvest_24h.py
python3 ~/.claude/skills/reddit-daily-brief/scripts/to_markdown.py --date 2026-07-16
python3 ~/.claude/skills/reddit-daily-brief/scripts/notebooklm_sync.py
python3 ~/.claude/skills/reddit-daily-brief/scripts/query_compose.py --gateway-first
python3 ~/.claude/skills/reddit-daily-brief/scripts/generate_pdf.py
```

## Configuration

All settings in `config/default_config.json` — no hardcoded values in scripts:

| Key | Description |
|-----|-------------|
| `timezone` | Pipeline timezone (Asia/Hong_Kong) |
| `schedule.harvest_hour` | Hour to harvest (7 = 7 AM HKT) |
| `schedule.email_hour` | Hour to send email (10 = 10 AM HKT) |
| `reddit.posts_per_subreddit` | Max posts per subreddit (default 50) |
| `reddit.comments_per_post` | Max comments per post (default 20) |
| `reddit.lookback_hours` | How far back to look (default 24) |
| `notebooks` | Array of `{id, name, subreddits}` — add/remove freely |
| `master_notebook_id` | ID of the master daily notebook |
| `archive_notebook_id` | ID of the historic archive notebook |
| `rolling_window_days` | Keep last N days in category/master notebooks |
| `questions` | List of questions to ask NotebookLM |
| `email.to` | Recipient email address |
| `email.subject_template` | Email subject with `{date}` placeholder |

### Adding a new subreddit

Edit `config/default_config.json` and add the subreddit name to the appropriate notebook's `subreddits` array. No other changes needed.

### Adding a new notebook category

Add a new entry to the `notebooks` array:
```json
{
  "id": "<notebooklm-id>",
  "name": "My New Category",
  "subreddits": ["sub1", "sub2"]
}
```

## Notebook IDs

Synced from `config/default_config.json` (SSOT — do not hand-edit here):

| Notebook | ID |
|----------|----|
| Claude & Anthropic Ecosystem | `b61c75f2-c938-4d56-8c0c-b1671b6e8121` |
| OpenClaw Ecosystem | `eb9f8914-e69f-46dd-bcf2-5787ca63bcf4` |
| AI Agents & Builders | `9de0e231-a415-4962-abf9-8091005b1c1d` |
| AI Products & Tools | `cfbabec7-8d70-44eb-ba78-57d13acd9dc4` |
| Other | `6459cf20-98e2-4627-b588-ca945fc4576d` |
| Reddit Daily Brief — Master | `ca258968-92e8-487f-a6e3-e01d939a2b7d` |
| Reddit Historic Archive | `2d6d758b-aa50-4cd6-9c06-c33bad7d9448` |

## Directory Layout

```
~/.claude/skills/reddit-daily-brief/
├── SKILL.md                      ← This file
├── config/
│   └── default_config.json       ← All settings here
├── scripts/
│   ├── pipeline.py               ← Main orchestrator
│   ├── harvest_24h.py            ← Step 3: Reddit harvest
│   ├── to_markdown.py            ← Step 4: JSON → Markdown
│   ├── notebooklm_sync.py        ← Step 5+7: NotebookLM upload
│   ├── query_compose.py          ← Step 6: Query + compose email
│   └── generate_pdf.py           ← Step 8: LaTeX PDF
├── outputs/
│   ├── daily/                    ← Harvest JSON files
│   ├── markdown/                 ← Per-subreddit .md files
│   │   └── combined/             ← Per-category combined .md
│   ├── composed/                 ← Email body + Q&A JSON
│   ├── pdfs/                     ← Generated PDFs
│   └── archive/                  ← Monthly archive .md files
└── logs/                         ← Per-run pipeline logs
```

## Scheduling

The daily cron is set up as a HappyCapy automation. It fires at 7 AM HKT daily.

To set it up in a new session:

```python
# Trigger daily at 7 AM HKT (UTC+8 → 23:00 UTC previous day)
# CronCreate cron: "0 23 * * *"
# prompt: "Run the Reddit Daily Brief pipeline: python3 ~/.claude/skills/reddit-daily-brief/scripts/pipeline.py 2>&1 | tail -20"
```

Or via Claude Code:
```
Use CronCreate with cron "0 23 * * *" and the pipeline command.
```

## Auth Requirements

- **Bridges**: `scripts/bridge_auth.py` discovers online machines via CAPY machines API (IDs rotate — never hardcode as sole path)
- **NotebookLM** (optional if `query_mode=gateway`): Mac online with notebooklm.google.com open in Chrome for token refresh
- **Reddit**: Cookies extracted to durable `config/reddit_cookies.json` via bridge + pycookiecheat. Without `token_v2`, harvest degrades to RSS (posts only, 0 comments)
- **Query**: Default `query_mode=gateway` uses AI Gateway on local markdown (NLM optional)
- **Email**: capymail `scripts/send_email.py`
- **Strict**: `--strict` fails loud and refuses empty emails

## Troubleshooting

**"No posts in last 24h"**: Quiet day or subreddit is private/inactive. Normal.

**NotebookLM token expired**: Run `python3 ~/.notebooklm/scripts/refresh_tokens.py --force`

**Reddit 401**: Token expired. Re-extract cookies from Mac Chrome manually.

**PDF fails**: Ensure `pdflatex` is installed. The script tries to auto-install via `apt-get`.

**Email not sent**: Check `email.to` is set in `config/default_config.json`.
