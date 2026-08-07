#!/usr/bin/env python3
"""
acceptance_test.py — Contract tests T1–T10 for reddit-daily-brief.

Usage:
  python3 acceptance_test.py
  python3 acceptance_test.py --quick   # skip live gateway/compose (T5/T10)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
CFG = SKILL / "config/default_config.json"
SKILL_MD = SKILL / "SKILL.md"
REPORT_DIR = Path(
    os.environ.get(
        "RDB_QA_REPORT_DIR",
        str(
            Path.home()
            / "a0/workspace/ca3937ad-5c47-4bbd-83da-4a9188ca51b3/workspace/outputs/hive-rdb"
        ),
    )
)


def run(cmd, timeout=180, cwd=None):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def ok(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {name}" + (f" — {detail}" if detail else "")
    print(line, flush=True)
    return {"name": name, "pass": passed, "detail": detail}


def t1_discover():
    r = run(["python3", str(SCRIPTS / "bridge_auth.py"), "--discover"])
    out = (r.stdout or "") + (r.stderr or "")
    has = "online_count=" in out or "br_" in out or "NONE" in out.upper() or "online" in out.lower()
    return ok("T1 discover bridges", r.returncode == 0 and has, out.strip()[:200])


def t2_py_compile():
    pys = sorted(SCRIPTS.glob("*.py"))
    r = run(["python3", "-m", "py_compile", *[str(p) for p in pys]])
    return ok(
        "T2 py_compile all scripts",
        r.returncode == 0,
        r.stderr[:200] if r.returncode else f"{len(pys)} files",
    )


def t3_pipeline_help():
    r = run(["python3", str(SCRIPTS / "pipeline.py"), "--help"])
    help_txt = r.stdout + r.stderr
    has_strict = "--strict" in help_txt
    dry_ok = "harvest" in help_txt.lower() and "markdown" in help_txt.lower()
    # dry-run must state harvest runs (unless --skip-harvest), not that dry-run itself skips harvest
    dry_line = ""
    for line in help_txt.splitlines():
        if "dry-run" in line.lower() or "dry run" in line.lower():
            dry_line += " " + line
    # Bad only if dry-run is defined as skipping harvest without "unless --skip-harvest"
    bad = bool(
        re.search(r"dry[- ]run[^\n]{0,80}skips?\s+harvest", dry_line, re.I)
        and "unless" not in dry_line.lower()
    )
    good_phrase = bool(
        re.search(r"harvest\s*\+\s*markdown|runs harvest|Harvest \+ markdown", help_txt, re.I)
    )
    return ok(
        "T3 pipeline --help strict+dry-run",
        r.returncode == 0 and has_strict and dry_ok and good_phrase and not bad,
        f"strict={has_strict} dry_ok={dry_ok} good_phrase={good_phrase} bad={bad}",
    )


def t4_markdown_date():
    date = "2099-01-01"
    r = run(
        [
            "python3",
            str(SCRIPTS / "to_markdown.py"),
            "--config",
            str(CFG),
            "--date",
            date,
            "--input-dir",
            str(SKILL / "outputs/daily"),
            "--output-dir",
            str(SKILL / "outputs/markdown"),
        ],
        timeout=120,
    )
    combined = SKILL / "outputs/markdown/combined"
    found = list(combined.glob(f"*_{date}.md")) if combined.exists() else []
    # cleanup test files
    for f in found:
        try:
            f.unlink()
        except Exception:
            pass
    return ok(
        "T4 to_markdown --date stamps combined",
        r.returncode == 0 and len(found) >= 1,
        f"exit={r.returncode} files={len(found)} stderr={r.stderr[:120]}",
    )


def t5_query_gateway():
    # pick latest combined date that exists
    comb = SKILL / "outputs/markdown/combined"
    dates = set()
    if comb.exists():
        for p in comb.glob("*.md"):
            m = re.search(r"(20\d{2}-\d{2}-\d{2})\.md$", p.name)
            if m:
                dates.add(m.group(1))
    if not dates:
        return ok("T5 query_compose gateway", False, "no combined markdown dates")
    date = sorted(dates)[-1]
    env = os.environ.copy()
    env["REDDIT_BRIEF_QUERY_MODE"] = "gateway"
    r = subprocess.run(
        [
            "python3",
            str(SCRIPTS / "query_compose.py"),
            "--config",
            str(CFG),
            "--date",
            date,
            "--gateway-first",
            "--output",
            str(SKILL / "outputs/composed" / f"email_accept_{date}.md"),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    email = SKILL / "outputs/composed" / f"email_accept_{date}.md"
    body = email.read_text(encoding="utf-8") if email.exists() else ""
    empty = "No data" in body and body.count("No data") >= 4
    warning_only = body.startswith("WARNING: EMPTY")
    good = email.exists() and not empty and "Reddit Daily Brief" in body
    return ok(
        "T5 query_compose gateway non-empty",
        r.returncode == 0 and good,
        f"date={date} exit={r.returncode} empty={empty} warn={warning_only} len={len(body)} tail={body[-120:]!r}",
    )


def t6_dry_run_logic():
    src = (SCRIPTS / "pipeline.py").read_text(encoding="utf-8")
    # harvest must not be gated by dry_run negatively
    bad_pattern = re.search(
        r"if not args\.skip_harvest and not args\.dry_run", src
    )
    # dry-run should return after markdown
    has_early_return = "dry_run" in src and "Dry-run complete" in src or "dry-run complete" in src.lower()
    # check help text
    r = run(["python3", str(SCRIPTS / "pipeline.py"), "--help"])
    help_ok = "Harvest + markdown only" in r.stdout or "harvest + markdown" in r.stdout.lower()
    return ok(
        "T6 dry-run logic",
        bad_pattern is None and has_early_return and help_ok,
        f"bad_old_if={bool(bad_pattern)} early_return={has_early_return} help_ok={help_ok}",
    )


def t7_strict_flag_wiring():
    src = (SCRIPTS / "pipeline.py").read_text(encoding="utf-8")
    qsrc = (SCRIPTS / "query_compose.py").read_text(encoding="utf-8")
    return ok(
        "T7 strict wiring",
        "--strict" in src
        and "args.strict" in src
        and "--strict" in qsrc
        and "is_empty_brief" in qsrc,
        "pipeline+query strict present",
    )


def t8_skill_config_ids():
    cfg = json.loads(CFG.read_text())
    md = SKILL_MD.read_text()
    ids = {n["id"] for n in cfg["notebooks"]}
    ids.add(cfg["master_notebook_id"])
    ids.add(cfg["archive_notebook_id"])
    missing = [i for i in ids if i not in md]
    # skill must not still list old sample IDs exclusively
    old = "fe6df597-cc28-42b7-9036-e87aff68976f"
    return ok(
        "T8 SKILL.md IDs match config",
        not missing and old not in md,
        f"missing_in_skill={missing[:3]} old_present={old in md}",
    )


def t9_no_sole_hardcoded_bridge():
    offenders = []
    for name in ("pipeline.py", "harvest_24h.py", "bridge_auth.py"):
        p = SCRIPTS / name
        if not p.exists():
            offenders.append(f"missing:{name}")
            continue
        text = p.read_text(encoding="utf-8")
        # bridge_auth may mention examples; must still have machines API discovery
        if name == "bridge_auth.py":
            if "machines" not in text and "/api/bridge/machines" not in text:
                offenders.append("bridge_auth no machines API")
            continue
        if name == "pipeline.py":
            # allow only as non-sole fallback if machines discovery present
            if "br_" in text and "machines" not in text and "bridge_auth" not in text:
                offenders.append("pipeline hardcoded without discovery")
            if re.search(r"bridge_id\s*=\s*'br_[a-f0-9]+'", text):
                # hard assignment without discovery nearby is bad if sole
                if "list_online" not in text and "bridge_auth" not in text and "machines" not in text:
                    offenders.append("pipeline sole hardcoded bridge_id")
    # stronger: pipeline must import/call bridge_auth
    pipe = (SCRIPTS / "pipeline.py").read_text(encoding="utf-8")
    uses_auth = "bridge_auth" in pipe
    return ok(
        "T9 no sole hardcoded bridge",
        uses_auth and not offenders,
        f"uses_bridge_auth={uses_auth} offenders={offenders}",
    )


def t11_strict_empty_exit():
    """Strict empty date must exit 2 (no invented markdown from undated daily)."""
    # ensure no combined for 2099
    comb = SKILL / "outputs/markdown/combined"
    if comb.exists():
        for p in comb.glob("*2099*"):
            try:
                p.unlink()
            except Exception:
                pass
    r = run(
        [
            "python3",
            str(SCRIPTS / "query_compose.py"),
            "--date",
            "2099-01-01",
            "--strict",
            "--gateway-first",
        ],
        timeout=180,
    )
    r2 = run(
        [
            "python3",
            str(SCRIPTS / "pipeline.py"),
            "--strict",
            "--skip-harvest",
            "--skip-upload",
            "--skip-email",
            "--date",
            "2099-01-01",
        ],
        timeout=180,
    )
    return ok(
        "T11 strict empty exits 2",
        r.returncode == 2 and r2.returncode == 2,
        f"query_rc={r.returncode} pipeline_rc={r2.returncode}",
    )


def t10_e2e_compose_pdf():
    comb = SKILL / "outputs/markdown/combined"
    dates = set()
    if comb.exists():
        for p in comb.glob("*.md"):
            m = re.search(r"(20\d{2}-\d{2}-\d{2})\.md$", p.name)
            if m and not m.group(1).startswith("2099"):
                dates.add(m.group(1))
    if not dates:
        return ok("T10 e2e compose+pdf", False, "no real combined dates")
    date = sorted(dates)[-1]
    email = SKILL / "outputs/composed" / f"email_{date}.md"
    qa = SKILL / "outputs/composed" / f"qa_{date}.json"
    # compose if missing or empty-looking
    need = True
    if email.exists():
        body = email.read_text(encoding="utf-8")
        if body.count("No data") < 4 and "Reddit Daily Brief" in body:
            need = False
    if need:
        r = run(
            [
                "python3",
                str(SCRIPTS / "query_compose.py"),
                "--config",
                str(CFG),
                "--date",
                date,
                "--gateway-first",
            ],
            timeout=300,
        )
        if r.returncode != 0:
            return ok("T10 e2e compose+pdf", False, f"compose exit {r.returncode}: {r.stderr[:150]}")
    body = email.read_text(encoding="utf-8") if email.exists() else ""
    empty = body.count("No data") >= 4
    pdf_path = SKILL / "outputs/pdfs" / f"reddit-brief-{date}.pdf"
    # generate pdf if qa exists
    if qa.exists():
        run(
            [
                "python3",
                str(SCRIPTS / "generate_pdf.py"),
                "--config",
                str(CFG),
                "--date",
                date,
                "--qa-file",
                str(qa),
                "--daily-dir",
                str(SKILL / "outputs/daily"),
                "--output",
                str(pdf_path),
            ],
            timeout=120,
        )
    pdf_ok = pdf_path.exists() and pdf_path.stat().st_size > 1000
    return ok(
        "T10 e2e compose+pdf",
        (not empty) and email.exists() and (pdf_ok or qa.exists()),
        f"date={date} empty={empty} email_len={len(body)} pdf={pdf_ok} size={pdf_path.stat().st_size if pdf_path.exists() else 0}",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--round", default="1")
    args = ap.parse_args()

    tests = [
        t1_discover,
        t2_py_compile,
        t3_pipeline_help,
        t4_markdown_date,
        t6_dry_run_logic,
        t7_strict_flag_wiring,
        t8_skill_config_ids,
        t9_no_sole_hardcoded_bridge,
    ]
    if not args.quick:
        tests.extend([t5_query_gateway, t10_e2e_compose_pdf, t11_strict_empty_exit])

    results = []
    for fn in tests:
        try:
            results.append(fn())
        except Exception as e:
            results.append(ok(fn.__name__, False, f"exception: {e}"))

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\n=== RESULT {passed}/{total} ===", flush=True)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"qa_round_{args.round}.md"
    lines = [
        f"# QA Round {args.round}",
        f"Time: {datetime.now(timezone.utc).isoformat()}",
        f"Score: {passed}/{total}",
        "",
    ]
    for r in results:
        lines.append(f"- {'PASS' if r['pass'] else 'FAIL'} **{r['name']}**: {r['detail']}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {report}", flush=True)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
