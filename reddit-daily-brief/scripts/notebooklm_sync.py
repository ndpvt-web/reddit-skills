#!/usr/bin/env python3
"""
notebooklm_sync.py — Upload today's markdown to NotebookLM.

Per category notebook: rolling 30-day window (delete oldest, add today).
Master notebook: same rolling window.
Archive notebook: append AI summary to monthly .md file (permanent).
"""

import json, subprocess, sys, os, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

SKILL_DIR = Path(__file__).parent.parent


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / 'config/default_config.json'
    with open(p) as f:
        return json.load(f)


def nlm(cfg, *args, capture=True):
    """Run notebooklm CLI. Returns (returncode, stdout, stderr)."""
    bin_path = os.path.expanduser(cfg.get('notebooklm_bin', '~/.local/bin/notebooklm'))
    profile = cfg.get('notebooklm_profile', '')
    profile_args = ['--profile', profile] if profile else []
    cmd = [bin_path] + profile_args + list(args)
    if capture:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    else:
        subprocess.run(cmd, timeout=120)
        return 0, '', ''


def list_sources(cfg, notebook_id):
    """Return list of sources in a notebook."""
    rc, out, err = nlm(cfg, 'source', 'list', '--notebook', notebook_id, '--json')
    if rc != 0:
        print(f'  [warn] source list failed for {notebook_id}: {err[:100]}')
        return []
    try:
        return json.loads(out).get('sources', [])
    except Exception:
        return []


def delete_source(cfg, notebook_id, source_id, title=''):
    rc, out, err = nlm(cfg, 'source', 'delete', source_id, '--notebook', notebook_id)
    if rc == 0:
        print(f'  Deleted old source: {title or source_id}')
    else:
        print(f'  [warn] delete failed for {source_id}: {err[:80]}')


def upload_source(cfg, notebook_id, file_path, title):
    rc, out, err = nlm(cfg, 'source', 'add', str(file_path),
                       '--notebook', notebook_id,
                       '--title', title,
                       '--type', 'text',
                       '--json')
    if rc == 0:
        try:
            data = json.loads(out)
            sid = data.get('source', {}).get('id', '?')
            print(f'  Uploaded: {title}  (source_id: {sid})')
            return sid
        except Exception:
            print(f'  Uploaded: {title}')
            return None
    else:
        print(f'  [FAILED] {title}: {err[:150]}')
        return None


def rolling_window_cleanup(cfg, notebook_id, notebook_name, date_str, rolling_days):
    """Delete sources older than rolling_days for this notebook."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=rolling_days)
    sources = list_sources(cfg, notebook_id)

    for src in sources:
        title = src.get('title', '')
        # Source titles follow pattern: "daily-{notebook_slug}-YYYY-MM-DD"
        # or "combined-{notebook_slug}-YYYY-MM-DD"
        if 'daily-' not in title and 'combined-' not in title:
            continue
        # Extract date from title (last 10 chars)
        date_part = title[-10:]
        try:
            src_date = datetime.strptime(date_part, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            if src_date < cutoff:
                delete_source(cfg, notebook_id, src['id'], title)
        except ValueError:
            pass  # title doesn't match date pattern — skip


def sync_category_notebook(cfg, nb_cfg, md_combined_dir, date_str):
    """Upload today's combined md to a category notebook, with rolling cleanup."""
    nb_id   = nb_cfg['id']
    nb_name = nb_cfg['name']
    safe_name = nb_name.replace(' ', '_').replace('&', 'and')

    md_file = Path(md_combined_dir) / f'{safe_name}_{date_str}.md'
    if not md_file.exists():
        print(f'  [skip] No combined file for {nb_name}: {md_file.name}')
        return

    rolling_days = cfg.get('rolling_window_days', 30)
    title = f'daily-{safe_name}-{date_str}'

    print(f'\n  [{nb_name}]')
    rolling_window_cleanup(cfg, nb_id, nb_name, date_str, rolling_days)
    upload_source(cfg, nb_id, md_file, title)


def sync_master_notebook(cfg, md_combined_dir, date_str):
    """Upload all category combined files to master notebook (rolling window)."""
    master_id = cfg.get('master_notebook_id')
    if not master_id:
        print('  [skip] No master_notebook_id in config')
        return

    rolling_days = cfg.get('rolling_window_days', 30)
    print(f'\n  [Master Notebook]')
    rolling_window_cleanup(cfg, master_id, 'Master', date_str, rolling_days)

    # Upload each category's combined file to master
    for nb_cfg in cfg['notebooks']:
        safe_name = nb_cfg['name'].replace(' ', '_').replace('&', 'and')
        md_file = Path(md_combined_dir) / f'{safe_name}_{date_str}.md'
        if not md_file.exists():
            continue
        title = f'daily-{safe_name}-{date_str}'
        upload_source(cfg, master_id, md_file, title)


def sync_archive_notebook(cfg, summary_text, date_str):
    """Append AI summary to monthly archive file, upload/replace in archive notebook."""
    archive_id = cfg.get('archive_notebook_id')
    if not archive_id:
        print('  [skip] No archive_notebook_id in config')
        return

    archive_dir = SKILL_DIR / 'outputs/archive'
    archive_dir.mkdir(parents=True, exist_ok=True)

    month_str = date_str[:7]  # YYYY-MM
    archive_file = archive_dir / f'reddit-digest-{month_str}.md'

    # Append today's entry
    entry = f"\n\n## {date_str}\n\n{summary_text}\n"
    with open(archive_file, 'a', encoding='utf-8') as f:
        if archive_file.stat().st_size == 0:
            f.write(f"# Reddit Daily Digest — {month_str}\n")
        f.write(entry)

    size_kb = archive_file.stat().st_size // 1024
    print(f'\n  [Archive Notebook] {archive_file.name} ({size_kb}KB)')

    # Delete existing source for this month if present (replace with updated file)
    title = f'archive-{month_str}'
    sources = list_sources(cfg, archive_id)
    for src in sources:
        if src.get('title') == title:
            delete_source(cfg, archive_id, src['id'], title)
            break

    upload_source(cfg, archive_id, archive_file, title)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=None)
    parser.add_argument('--markdown-dir', default=None)
    parser.add_argument('--summary', default='', help='AI summary text for archive')
    parser.add_argument('--date', default=None, help='YYYY-MM-DD (default: today UTC)')
    args = parser.parse_args()

    cfg = load_config(args.config)
    date_str = args.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    md_dir = Path(args.markdown_dir) if args.markdown_dir else SKILL_DIR / 'outputs/markdown'
    md_combined_dir = md_dir / 'combined'

    print(f'=== NotebookLM Sync — {date_str} ===')

    # 1. Category notebooks
    for nb_cfg in cfg['notebooks']:
        sync_category_notebook(cfg, nb_cfg, md_combined_dir, date_str)

    # 2. Master notebook
    sync_master_notebook(cfg, md_combined_dir, date_str)

    # 3. Archive notebook
    if args.summary:
        sync_archive_notebook(cfg, args.summary, date_str)
    else:
        print('\n  [Archive] No summary provided — skipping archive append')

    print('\n=== Sync complete ===')


if __name__ == '__main__':
    main()
