#!/usr/bin/env python3
"""
pipeline.py — Main orchestrator for the Reddit Daily Brief.

Stages:
  1. Refresh NotebookLM tokens (Mac must be online)
  2. Re-extract Reddit cookies from Mac Chrome
  3. Harvest 24h Reddit posts + comments
  4. Convert to Markdown
  5. Upload to NotebookLM (category + master notebooks, rolling window)
  6. Query NotebookLM, compose email body
  7. Append archive summary to monthly file, upload to archive notebook
  8. Generate LaTeX PDF
  9. Send email via capymail

Usage:
    python3 pipeline.py                    # Full run
    python3 pipeline.py --skip-harvest     # Skip step 3 (use existing daily dir)
    python3 pipeline.py --skip-upload      # Skip step 5
    python3 pipeline.py --skip-email       # Skip step 9
    python3 pipeline.py --dry-run          # Harvest + markdown only (no upload/query/pdf/email)
    python3 pipeline.py --date 2026-04-21  # Use specific date
    python3 pipeline.py --strict           # Fail loud on auth/data failures; no empty email
"""

import json, subprocess, sys, os, argparse, time
from pathlib import Path
from datetime import datetime, timezone

SKILL_DIR = Path(__file__).parent.parent
SCRIPTS   = SKILL_DIR / 'scripts'
LOGS_DIR  = SKILL_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)
BRIDGE_AUTH = SCRIPTS / 'bridge_auth.py'

# Ensure TinyTeX pdflatex is on PATH
_tinytex = Path.home() / '.TinyTeX/bin/x86_64-linux'
if _tinytex.exists():
    os.environ['PATH'] = str(_tinytex) + ':' + os.environ.get('PATH', '')


def load_config(path=None):
    p = Path(path) if path else SKILL_DIR / 'config/default_config.json'
    with open(p) as f:
        return json.load(f)


def log(msg, log_file=None):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    if log_file:
        with open(log_file, 'a') as f:
            f.write(line + '\n')


def run_step(label, cmd, log_file, check=True):
    """Run a pipeline stage. Always returns (ok, returncode) from the real exit code.

    check is retained for call-site compatibility; non-zero always yields ok=False so
    callers (e.g. query_compose exit 2) can propagate correctly.
    """
    log(f'=== {label} ===', log_file)
    log(f'  cmd: {" ".join(str(c) for c in cmd)}', log_file)
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        log(f'[stage-fail] FAILED: {label} (exit {result.returncode})', log_file)
        return False, result.returncode
    return True, result.returncode


def uses_gateway(cfg) -> bool:
    """True when analysis should use AI Gateway (not NotebookLM query path).

    Honors env REDDIT_BRIEF_QUERY_MODE over config query_mode.
    """
    qmode = (
        os.environ.get('REDDIT_BRIEF_QUERY_MODE')
        or (cfg or {}).get('query_mode')
        or ''
    ).lower().strip()
    return qmode == 'gateway'


def cookies_path(cfg):
    return Path(os.path.expanduser(cfg.get('reddit', {}).get('cookies_file', '/tmp/reddit_cookies.json')))


def cookies_present(cfg):
    p = cookies_path(cfg)
    if not p.exists() or p.stat().st_size < 10:
        return False
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return bool(data) and isinstance(data, dict)
    except Exception:
        return False


def refresh_notebooklm_tokens(log_file, strict=False):
    """Refresh NLM tokens. Returns True if ok/usable, False if completely failed."""
    log('[auth] Refreshing NotebookLM Chrome tokens...', log_file)
    script = Path.home() / '.notebooklm/scripts/refresh_tokens.py'
    if not script.exists():
        log(f'[auth] Token refresh script missing: {script}', log_file)
        return False
    try:
        result = subprocess.run(
            ['python3', str(script), '--force'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            log(f'[auth] Tokens refreshed: {result.stdout.strip()[-100:]}', log_file)
            return True
        log(f'[auth] Token refresh failed (exit {result.returncode}): {result.stderr[:200]}', log_file)
        return False
    except subprocess.TimeoutExpired:
        log('[auth] Token refresh timed out (Mac offline?) — cached tokens may be stale', log_file)
        return False
    except Exception as e:
        log(f'[auth] Token refresh error: {e}', log_file)
        return False


def re_extract_reddit_cookies(cfg, log_file, strict=False):
    """Re-extract Reddit cookies via bridge_auth if present, else machines discovery fallback."""
    log('[auth] Re-extracting Reddit cookies from Mac Chrome...', log_file)
    cookies_file = str(cookies_path(cfg))

    # Prefer shared bridge_auth module (AuthEngineer SSOT)
    if BRIDGE_AUTH.exists():
        log(f'[auth] Using bridge_auth: {BRIDGE_AUTH}', log_file)
        try:
            result = subprocess.run(
                ['python3', str(BRIDGE_AUTH), '--extract-cookies'],
                capture_output=True, text=True, timeout=90
            )
            out = (result.stdout or '') + (result.stderr or '')
            if out.strip():
                log(f'[auth] bridge_auth: {out.strip()[:300]}', log_file)
            if result.returncode == 0 and cookies_present(cfg):
                log(f'[auth] Cookies OK via bridge_auth → {cookies_file}', log_file)
                return True
            log(f'[auth] bridge_auth extract failed or cookies missing (exit {result.returncode})', log_file)
        except Exception as e:
            log(f'[auth] bridge_auth error: {e}', log_file)
        # Fall through to inline discovery if cookies still missing
        if cookies_present(cfg):
            return True

    return _extract_cookies_via_discovery(cfg, log_file, cookies_file)


def _discover_online_bridges(log_file):
    """Discover online bridge IDs from Capy machines API. No hardcoded sole ID."""
    capy_secret = os.environ.get('CAPY_SECRET', '')
    capy_base = os.environ.get('CAPY_BASE_URL', '').rstrip('/')
    capy_user = os.environ.get('CAPY_USER_ID', '')
    if not (capy_secret and capy_base and capy_user):
        log('[auth] CAPY_* env incomplete — cannot discover bridges', log_file)
        return []

    try:
        result = subprocess.run(
            ['curl', '-s', '-H', f'Authorization: Bearer {capy_secret}',
             f'{capy_base}/api/bridge/machines?userId={capy_user}'],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            log(f'[auth] machines API curl failed exit {result.returncode}', log_file)
            return []
        data = json.loads(result.stdout)
        machines = data.get('machines') or data.get('data') or []
        if isinstance(machines, dict):
            machines = list(machines.values()) if machines else []
        online = []
        for m in machines:
            if not isinstance(m, dict):
                continue
            bid = m.get('bridgeId') or m.get('id') or m.get('bridge_id')
            is_online = m.get('online') is True or m.get('status') == 'online'
            if bid and is_online:
                online.append(bid)
        log(f'[auth] Online bridges discovered: {online or "NONE"}', log_file)
        return online
    except Exception as e:
        log(f'[auth] Bridge discovery error: {e}', log_file)
        return []


def _extract_cookies_via_discovery(cfg, log_file, cookies_file):
    """Fallback: discover online Mac bridges and extract cookies (no sole hardcoded ID)."""
    capy_secret = os.environ.get('CAPY_SECRET', '')
    capy_base = os.environ.get('CAPY_BASE_URL', '').rstrip('/')
    capy_user = os.environ.get('CAPY_USER_ID', '')

    if not capy_secret:
        log('[auth] CAPY_SECRET not set — skipping cookie refresh (using existing)', log_file)
        return cookies_present(cfg)

    bridges = _discover_online_bridges(log_file)
    if not bridges:
        log('[auth] No online bridges — using existing cookies file if present', log_file)
        return cookies_present(cfg)

    extract_cmd = (
        'python3 -c "'
        'import pycookiecheat, json, os; '
        "profiles = [\"Default\",\"Profile 1\",\"Profile 2\",\"Profile 3\"]; "
        "base = os.path.expanduser(\"~/Library/Application Support/Google/Chrome\"); "
        'found = {}; '
        '[found.update(pycookiecheat.chrome_cookies("https://reddit.com", '
        'cookie_file=f"{base}/{p}/Cookies")) for p in profiles if os.path.exists(f"{base}/{p}/Cookies")]; '
        "open('/tmp/reddit_cookies.json','w').write(json.dumps(found)); "
        'print(f\"Cookies extracted: {len(found)}, token_v2: {bool(found.get(\'token_v2\'))}\") '
        '"'
    )

    for bridge_id in bridges:
        log(f'[auth] Trying bridge {bridge_id} for cookie extract...', log_file)
        try:
            payload = json.dumps({
                'userId': capy_user,
                'bridgeId': bridge_id,
                'command': 'terminal/exec',
                'payload': {'command': extract_cmd, 'timeout': 30}
            })
            result = subprocess.run(
                ['curl', '-s', '-X', 'POST',
                 '-H', f'Authorization: Bearer {capy_secret}',
                 '-H', 'Content-Type: application/json',
                 '-d', payload,
                 f'{capy_base}/api/bridge/command'],
                capture_output=True, text=True, timeout=45
            )
            if result.returncode != 0:
                log(f'[auth] Bridge {bridge_id} exec curl failed', log_file)
                continue

            try:
                resp = json.loads(result.stdout)
            except Exception:
                log(f'[auth] Bridge {bridge_id} non-JSON response', log_file)
                continue

            stdout = resp.get('data', {}).get('stdout', '') or ''
            log(f'[auth] Bridge result: {stdout[:120]}', log_file)

            read_payload = json.dumps({
                'userId': capy_user,
                'bridgeId': bridge_id,
                'command': 'files/read',
                'payload': {'path': '/tmp/reddit_cookies.json', 'encoding': 'utf8'}
            })
            read_result = subprocess.run(
                ['curl', '-s', '-X', 'POST',
                 '-H', f'Authorization: Bearer {capy_secret}',
                 '-H', 'Content-Type: application/json',
                 '-d', read_payload,
                 f'{capy_base}/api/bridge/command'],
                capture_output=True, text=True, timeout=30
            )
            if read_result.returncode != 0:
                continue
            read_resp = json.loads(read_result.stdout)
            cookie_content = read_resp.get('data', {}).get('content', '')
            if not cookie_content:
                continue
            Path(cookies_file).parent.mkdir(parents=True, exist_ok=True)
            with open(cookies_file, 'w') as f:
                f.write(cookie_content)
            log(f'[auth] Cookies saved to {cookies_file} via {bridge_id}', log_file)
            return True
        except Exception as e:
            log(f'[auth] Cookie bridge error on {bridge_id}: {e}', log_file)

    log('[auth] Cookie refresh failed on all bridges — using existing cookies file', log_file)
    return cookies_present(cfg)


def email_is_empty(email_path):
    """True if email body is missing or every category effectively empty / No data."""
    p = Path(email_path)
    if not p.exists():
        return True
    body = p.read_text(encoding='utf-8').strip()
    if not body or len(body) < 40:
        return True
    if 'WARNING: EMPTY BRIEF' in body:
        return True
    # Heuristic: all "No data" lines and no substantial content
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return True
    no_data_markers = sum(1 for ln in lines if 'no data' in ln.lower() or ln.lower() == 'n/a')
    content_lines = [ln for ln in lines if not ln.startswith('#') and 'no data' not in ln.lower()]
    if no_data_markers >= 2 and len(content_lines) <= 3:
        return True
    return False


def send_email(cfg, date_str, email_path, pdf_path, log_file, strict=False):
    """Send the daily brief email via capymail CLI."""
    email_cfg = cfg.get('email', {})
    to_addr = email_cfg.get('to', '')
    if not to_addr:
        log('[email] No email.to configured — skipping email send', log_file)
        return True

    if strict and email_is_empty(email_path):
        log('[strict] Refusing to send empty / all-No-data email', log_file)
        return False

    subj_tpl = email_cfg.get('subject_template', 'Reddit Daily Brief — {date}')
    subject = subj_tpl.format(date=date_str)

    body = Path(email_path).read_text(encoding='utf-8') if Path(email_path).exists() else 'See attached PDF.'

    send_script = Path.home() / '.claude/skills/capymail/scripts/send_email.py'
    cmd = ['python3', str(send_script), '--to', to_addr, '--subject', subject, '--body', body]

    from_alias = email_cfg.get('from_alias', os.environ.get('CAPY_USER_EMAIL_ALIAS', ''))
    if from_alias:
        cmd += ['--from', from_alias]

    if pdf_path and Path(pdf_path).exists():
        cmd += ['--attachment', str(pdf_path)]

    log(f'[email] Sending email to {to_addr}...', log_file)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        log(f'[email] Email sent: {result.stdout[:100]}', log_file)
        return True
    log(f'[stage-fail] Email send failed: {result.stderr[:150]}', log_file)
    return False


def main():
    parser = argparse.ArgumentParser(
        description='Reddit Daily Brief Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Dry-run: runs harvest (unless --skip-harvest) + markdown only; '
            'skips upload, query, pdf, and email.\n'
            'Strict: non-zero exit on auth/data failures; never sends empty email.'
        ),
    )
    parser.add_argument('--config', default=None)
    parser.add_argument('--date', default=None, help='YYYY-MM-DD (default: today UTC)')
    parser.add_argument('--skip-harvest',  action='store_true',
                        help='Skip harvest step (use existing daily JSON)')
    parser.add_argument('--skip-upload',   action='store_true')
    parser.add_argument('--skip-email',    action='store_true')
    parser.add_argument('--dry-run',       action='store_true',
                        help='Harvest + markdown only (no upload/query/pdf/email)')
    parser.add_argument('--strict',        action='store_true',
                        help='Fail loud on auth/data failures; no empty email')
    args = parser.parse_args()

    cfg = load_config(args.config)
    config_path = str(Path(args.config) if args.config else SKILL_DIR / 'config/default_config.json')
    date_str = args.date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    strict = bool(args.strict)

    log_file = LOGS_DIR / f'pipeline_{date_str}.log'
    log(f'Reddit Daily Brief pipeline starting — {date_str}'
        f'{" [DRY-RUN]" if args.dry_run else ""}{" [STRICT]" if strict else ""}', log_file)

    daily_dir    = SKILL_DIR / 'outputs/daily'
    md_dir       = SKILL_DIR / 'outputs/markdown'
    composed_dir = SKILL_DIR / 'outputs/composed'
    composed_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Refresh NotebookLM tokens ────────────────────────────────
    tokens_ok = refresh_notebooklm_tokens(log_file, strict=strict)

    # ── Step 2: Re-extract Reddit cookies ────────────────────────────────
    cookies_ok = re_extract_reddit_cookies(cfg, log_file, strict=strict)

    gateway = uses_gateway(cfg)

    if gateway:
        # Gateway path: analysis uses AI Gateway + local markdown.
        # NLM token failure is non-fatal. Cookies only required if harvest will run.
        if not tokens_ok:
            log('[auth] NotebookLM token refresh failed — non-fatal (gateway query mode)', log_file)
        if not cookies_ok:
            log('[auth] WARNING: cookies missing/unusable after refresh attempt', log_file)
            if strict and not args.skip_harvest:
                log('[strict] Aborting harvest path without cookies (gateway mode)', log_file)
                sys.exit(2)
            if args.skip_harvest:
                log('[auth] skip-harvest + gateway: proceeding without cookies', log_file)
    else:
        # Non-gateway: strict abort when both tokens and cookies fail
        if not tokens_ok and not cookies_ok:
            log('[auth] ERROR: token refresh completely failed AND cookies missing/unusable', log_file)
            if strict:
                log('[strict] Aborting — cannot proceed without auth', log_file)
                sys.exit(2)
        elif not cookies_ok:
            log('[auth] WARNING: cookies missing/unusable after refresh attempt', log_file)
            if strict and not args.skip_harvest:
                log('[strict] Aborting harvest path without cookies', log_file)
                sys.exit(2)

    # ── Step 3: Harvest 24h ───────────────────────────────────────────────
    # A7: harvest runs unless --skip-harvest. dry-run does NOT skip harvest.
    if not args.skip_harvest:
        harvest_cmd = [
            'python3', str(SCRIPTS / 'harvest_24h.py'),
            '--config', config_path,
            '--output', str(daily_dir),
            '--resume',
        ]
        # Pass --date only if harvest supports it (probe help)
        try:
            help_out = subprocess.run(
                ['python3', str(SCRIPTS / 'harvest_24h.py'), '--help'],
                capture_output=True, text=True, timeout=10
            )
            if '--date' in (help_out.stdout or ''):
                harvest_cmd += ['--date', date_str]
        except Exception:
            pass

        ok, rc = run_step('Harvest 24h Reddit', harvest_cmd, log_file)
        if not ok:
            log('[stage-fail] Harvest failed — aborting pipeline', log_file)
            sys.exit(1 if not strict else 2)
    else:
        log('=== Harvest skipped (--skip-harvest) ===', log_file)

    # ── Step 4: Convert to Markdown ───────────────────────────────────────
    # A4: do NOT invent dated combined files from undated daily JSON when
    # harvest was skipped — that stamps today's posts onto an arbitrary --date
    # and makes empty-date tests / historical re-runs falsely non-empty.
    if args.skip_harvest:
        log(
            f'=== Markdown skipped (--skip-harvest; using existing combined for {date_str}) ===',
            log_file,
        )
    else:
        md_cmd = [
            'python3', str(SCRIPTS / 'to_markdown.py'),
            '--config', config_path,
            '--input-dir', str(daily_dir),
            '--output-dir', str(md_dir),
            '--date', date_str,
        ]
        ok, rc = run_step('Convert to Markdown', md_cmd, log_file)
        if not ok:
            log('[stage-fail] Markdown conversion failed — aborting', log_file)
            sys.exit(1 if not strict else 2)

    # A7/A9: dry-run stops after harvest + markdown (no upload/query/pdf/email)
    if args.dry_run:
        log('Dry-run complete (harvest + markdown only; skipped upload/query/pdf/email)', log_file)
        return

    # ── Step 5: Upload to NotebookLM ──────────────────────────────────────
    if not args.skip_upload:
        ok, rc = run_step(
            'Sync to NotebookLM',
            ['python3', str(SCRIPTS / 'notebooklm_sync.py'),
             '--config', config_path,
             '--markdown-dir', str(md_dir),
             '--date', date_str],
            log_file,
            check=False,
        )
        if not ok:
            log('[stage-fail] NotebookLM sync failed — continuing', log_file)
            if strict:
                log('[strict] Upload failure recorded (non-fatal for query path if gateway)', log_file)
    else:
        log('=== NotebookLM upload skipped ===', log_file)

    # Index wait only needed when uploading to NotebookLM (not gateway path)
    if not args.skip_upload and not gateway:
        log('Waiting 30s for NotebookLM to index sources...', log_file)
        time.sleep(30)
    else:
        log('[query] Skipping NLM index wait (upload skipped or gateway mode)', log_file)

    # ── Step 6: Query NotebookLM + compose ───────────────────────────────
    qa_path    = composed_dir / f'qa_{date_str}.json'
    email_path = composed_dir / f'email_{date_str}.md'
    archive_summary_path = composed_dir / f'archive_summary_{date_str}.md'

    query_cmd = [
        'python3', str(SCRIPTS / 'query_compose.py'),
        '--config', config_path,
        '--date', date_str,
        '--output', str(email_path),
        '--archive-output', str(archive_summary_path),
        '--gateway-first',  # default for reliability (A8 / gateway path)
    ]
    if strict:
        query_cmd.append('--strict')

    # query_mode from config or env (uses_gateway); --gateway-first always on for reliability
    if gateway:
        log('[query] query_mode=gateway (AI Gateway + local markdown)', log_file)
    else:
        log('[query] query_mode non-gateway (still passing --gateway-first as default)', log_file)

    ok, rc = run_step('Query NotebookLM + compose', query_cmd, log_file, check=False)
    if not ok:
        log(f'[stage-fail] Query/compose failed (exit {rc})', log_file)
        # A8: if query_compose exits 2, pipeline exits 2 (run_step now captures rc correctly)
        if rc == 2 or strict:
            log('[strict] Propagating query_compose failure', log_file)
            sys.exit(2 if rc == 2 else 1)
        log('Query/compose failed — continuing to PDF/email with available body', log_file)

    if strict and email_is_empty(email_path):
        log('[strict] Composed email empty / all No data — aborting before PDF/email', log_file)
        sys.exit(2)

    # ── Step 7: Archive notebook sync ────────────────────────────────────
    if not args.skip_upload and archive_summary_path.exists():
        archive_summary = archive_summary_path.read_text(encoding='utf-8')
        ok, rc = run_step(
            'Archive sync',
            ['python3', str(SCRIPTS / 'notebooklm_sync.py'),
             '--config', config_path,
             '--markdown-dir', str(md_dir),
             '--date', date_str,
             '--summary', archive_summary],
            log_file,
            check=False,
        )

    # ── Step 8: Generate PDF ──────────────────────────────────────────────
    pdf_dir = Path(os.path.expanduser(cfg.get('pdf', {}).get('output_dir', str(SKILL_DIR / 'outputs/pdfs'))))
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f'reddit-brief-{date_str}.pdf'

    ok, rc = run_step(
        'Generate PDF',
        ['python3', str(SCRIPTS / 'generate_pdf.py'),
         '--config', config_path,
         '--date', date_str,
         '--qa-file', str(qa_path),
         '--daily-dir', str(daily_dir),
         '--output', str(pdf_path)],
        log_file,
        check=False,
    )
    if not ok:
        log('[stage-fail] PDF generation failed — sending email without attachment', log_file)
        pdf_path = None

    # ── Step 9: Send email ────────────────────────────────────────────────
    if not args.skip_email:
        sent = send_email(cfg, date_str, email_path, pdf_path, log_file, strict=strict)
        if not sent and strict:
            log('[strict] Email not sent (empty or failure) — exiting 2', log_file)
            sys.exit(2)
    else:
        log('=== Email skipped ===', log_file)

    log(f'Pipeline complete for {date_str}', log_file)
    log(f'Log: {log_file}', log_file)
    if pdf_path and Path(str(pdf_path)).exists():
        log(f'PDF: {pdf_path}', log_file)


if __name__ == '__main__':
    main()
