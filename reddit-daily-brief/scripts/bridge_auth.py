#!/usr/bin/env python3
"""
bridge_auth.py — Dynamic Mac bridge discovery for Reddit cookies + NotebookLM tokens.

Restores axioms:
  A3 Reddit auth  — extract token_v2 via any online Mac bridge (no hardcoded sole path)
  A5 NLM tokens   — refresh csrf/sid via discovery; never uncaught KeyError on missing data

Usage:
  python3 bridge_auth.py --discover
  python3 bridge_auth.py --extract-cookies
  python3 bridge_auth.py --extract-cookies --cookies-path ~/.claude/skills/reddit-daily-brief/config/reddit_cookies.json
  python3 bridge_auth.py --refresh-nlm
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_COOKIES_PATH = SKILL_DIR / "config" / "reddit_cookies.json"
COMPAT_COOKIES_PATH = Path("/tmp/reddit_cookies.json")
NLM_REFRESH_SCRIPT = Path.home() / ".notebooklm" / "scripts" / "refresh_tokens.py"
NLM_TOKENS_PATH = Path.home() / ".notebooklm" / "chrome_tokens.json"
NLM_STORAGE_PATH = Path.home() / ".notebooklm" / "profiles" / "default" / "storage_state.json"

CHROME_PROFILES = ("Default", "Profile 1", "Profile 2", "Profile 3")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _capy_creds() -> Dict[str, str]:
    """Return CAPY env dict; empty strings if missing (callers handle gracefully)."""
    return {
        "secret": _env("CAPY_SECRET"),
        "user_id": _env("CAPY_USER_ID"),
        "base_url": _env("CAPY_BASE_URL", "https://happycapy.ai").rstrip("/"),
    }


def _log(msg: str) -> None:
    print(f"[auth] {msg}", flush=True)


def _curl_json(
    method: str,
    url: str,
    *,
    headers: Optional[List[str]] = None,
    body: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Run curl and parse JSON. Raises RuntimeError on transport/parse failure."""
    cmd = ["curl", "-sS", "-X", method, "--max-time", str(max(5, timeout))]
    for h in headers or []:
        cmd += ["-H", h]
    if body is not None:
        cmd += ["-d", body]
    cmd.append(url)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 10
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"curl timeout for {method} {url}") from e
    except FileNotFoundError as e:
        raise RuntimeError("curl not found on PATH") from e

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:400]
        raise RuntimeError(f"curl exit {result.returncode} for {method} {url}: {err}")

    raw = (result.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"empty response from {method} {url}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-JSON response from {url}: {raw[:300]}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"expected JSON object from {url}, got {type(data).__name__}")
    return data


def list_online_machines() -> List[Dict[str, Any]]:
    """
    GET $CAPY_BASE_URL/api/bridge/machines?userId=$CAPY_USER_ID
    Return list of online machine dicts (online == True).
    """
    creds = _capy_creds()
    if not creds["secret"] or not creds["user_id"] or not creds["base_url"]:
        _log("missing CAPY_SECRET / CAPY_USER_ID / CAPY_BASE_URL — cannot list machines")
        return []

    url = f"{creds['base_url']}/api/bridge/machines?userId={creds['user_id']}"
    try:
        resp = _curl_json(
            "GET",
            url,
            headers=[f"Authorization: Bearer {creds['secret']}"],
            timeout=30,
        )
    except Exception as e:
        _log(f"machines API failed: {e}")
        return []

    machines = resp.get("machines")
    if machines is None and isinstance(resp.get("data"), dict):
        machines = resp["data"].get("machines")
    if machines is None and isinstance(resp.get("data"), list):
        machines = resp["data"]
    if not isinstance(machines, list):
        _log(f"machines API unexpected shape keys={list(resp.keys())}")
        return []

    online: List[Dict[str, Any]] = []
    for m in machines:
        if not isinstance(m, dict):
            continue
        if m.get("online") is True or str(m.get("online", "")).lower() == "true":
            online.append(m)
    return online


def _machine_label(m: Dict[str, Any]) -> str:
    parts = [
        str(m.get("name") or ""),
        str(m.get("hostname") or ""),
        str(m.get("hostName") or ""),
        str(m.get("displayName") or ""),
        str(m.get("label") or ""),
        str(m.get("platform") or ""),
        str(m.get("os") or ""),
        str(m.get("deviceName") or ""),
    ]
    return " ".join(parts)


def _bridge_id_of(m: Dict[str, Any]) -> Optional[str]:
    bid = m.get("bridgeId") or m.get("bridge_id") or m.get("id")
    if not bid:
        return None
    return str(bid)


def pick_bridge(prefer_hostname_substr: Optional[str] = None) -> Optional[str]:
    """
    Prefer an online Mac. Optional prefer_hostname_substr matches name/hostname
    (e.g. 'Pro' or 'Air'). Returns bridgeId or None.
    """
    online = list_online_machines()
    if not online:
        _log("no online bridges")
        return None

    def is_mac(m: Dict[str, Any]) -> bool:
        label = _machine_label(m).lower()
        platform = str(m.get("platform") or m.get("os") or "").lower()
        return (
            "mac" in label
            or "darwin" in label
            or "macos" in platform
            or "darwin" in platform
            or "mac" in platform
            or bool(m.get("isMac") or m.get("is_mac"))
        )

    macs = [m for m in online if is_mac(m)]
    pool = macs if macs else online

    if prefer_hostname_substr:
        needle = prefer_hostname_substr.lower()
        preferred = [m for m in pool if needle in _machine_label(m).lower()]
        if preferred:
            pool = preferred

    # Stable-ish preference: prefer Pro when no explicit substr, else first online Mac
    if not prefer_hostname_substr:
        pro = [m for m in pool if "pro" in _machine_label(m).lower()]
        if pro:
            pool = pro

    chosen = pool[0]
    bid = _bridge_id_of(chosen)
    if not bid:
        _log(f"online machine missing bridgeId: {chosen}")
        return None
    _log(
        f"picked bridge {bid} label={_machine_label(chosen)!r} "
        f"(online={len(online)}, macs={len(macs)})"
    )
    return bid


def bridge_exec(bridge_id: str, command: str, timeout: int = 60) -> str:
    """
    POST terminal/exec to bridge. Return stdout string.
    Raise RuntimeError with full response if data/stdout missing.
    """
    if not bridge_id:
        raise RuntimeError("bridge_exec: empty bridge_id")
    creds = _capy_creds()
    if not creds["secret"] or not creds["user_id"] or not creds["base_url"]:
        raise RuntimeError("bridge_exec: missing CAPY_SECRET / CAPY_USER_ID / CAPY_BASE_URL")

    body = json.dumps(
        {
            "userId": creds["user_id"],
            "bridgeId": bridge_id,
            "command": "terminal/exec",
            "payload": {"command": command, "timeout": timeout},
        }
    )
    try:
        resp = _curl_json(
            "POST",
            f"{creds['base_url']}/api/bridge/command",
            headers=[
                f"Authorization: Bearer {creds['secret']}",
                "Content-Type: application/json",
            ],
            body=body,
            timeout=timeout + 15,
        )
    except Exception as e:
        raise RuntimeError(f"bridge_exec transport failed: {e}") from e

    data = resp.get("data")
    if not isinstance(data, dict) or "stdout" not in data:
        raise RuntimeError(
            f"bridge_exec: no data.stdout in response for bridge={bridge_id}: "
            f"{json.dumps(resp)[:800]}"
        )
    stdout = data.get("stdout")
    if stdout is None:
        raise RuntimeError(
            f"bridge_exec: stdout is null for bridge={bridge_id}: {json.dumps(resp)[:800]}"
        )
    return str(stdout)


def bridge_read(bridge_id: str, path: str) -> str:
    """
    files/read utf8 or base64-decode content from bridge path.
    Raises RuntimeError with full response if data missing.
    """
    if not bridge_id:
        raise RuntimeError("bridge_read: empty bridge_id")
    creds = _capy_creds()
    if not creds["secret"] or not creds["user_id"] or not creds["base_url"]:
        raise RuntimeError("bridge_read: missing CAPY_SECRET / CAPY_USER_ID / CAPY_BASE_URL")

    def _read_once(encoding: str) -> Dict[str, Any]:
        body = json.dumps(
            {
                "userId": creds["user_id"],
                "bridgeId": bridge_id,
                "command": "files/read",
                "payload": {"path": path, "encoding": encoding},
            }
        )
        return _curl_json(
            "POST",
            f"{creds['base_url']}/api/bridge/command",
            headers=[
                f"Authorization: Bearer {creds['secret']}",
                "Content-Type: application/json",
            ],
            body=body,
            timeout=45,
        )

    last_resp: Dict[str, Any] = {}
    for encoding in ("utf8", "base64"):
        try:
            resp = _read_once(encoding)
            last_resp = resp
        except Exception as e:
            last_resp = {"error": str(e)}
            continue
        data = resp.get("data")
        if not isinstance(data, dict):
            continue
        content = data.get("content")
        if content is None:
            continue
        content_s = str(content)
        if encoding == "base64":
            try:
                return base64.b64decode(content_s).decode("utf-8", errors="replace")
            except Exception:
                # Some bridges already return plain text even when base64 requested
                return content_s
        return content_s

    raise RuntimeError(
        f"bridge_read: no data for path={path!r} bridge={bridge_id}: "
        f"{json.dumps(last_resp)[:800]}"
    )


def _write_cookies_files(cookies: Dict[str, Any], cookies_path: Path) -> None:
    text = json.dumps(cookies, indent=2, sort_keys=True)
    cookies_path = Path(os.path.expanduser(str(cookies_path)))
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    cookies_path.write_text(text, encoding="utf-8")
    try:
        COMPAT_COOKIES_PATH.write_text(text, encoding="utf-8")
    except OSError as e:
        _log(f"could not write compat cookies path {COMPAT_COOKIES_PATH}: {e}")


def _parse_cookies_payload(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or "").strip()
    if not raw:
        return None
    # Prefer last JSON object if stdout has log lines
    candidates = [raw]
    if "\n" in raw:
        candidates.append(raw.splitlines()[-1].strip())
        # also try first '{' ... last '}'
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            candidates.append(raw[i : j + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


_EXTRACT_PY = r"""
import json, os
try:
    import pycookiecheat
except Exception as e:
    print(json.dumps({"__error__": f"pycookiecheat import failed: {e}"}))
    raise SystemExit(0)

profiles = ["Default", "Profile 1", "Profile 2", "Profile 3"]
bases = [
    os.path.expanduser("~/Library/Application Support/Google/Chrome"),
    "/Users/niveshdandyan/Library/Application Support/Google/Chrome",
    "/Users/nivesh/Library/Application Support/Google/Chrome",
]
found = {}
errors = []
for base in bases:
    if not os.path.isdir(base):
        continue
    for p in profiles:
        cf = os.path.join(base, p, "Cookies")
        if not os.path.exists(cf):
            continue
        try:
            found.update(pycookiecheat.chrome_cookies("https://reddit.com", cookie_file=cf))
            found.update(pycookiecheat.chrome_cookies("https://www.reddit.com", cookie_file=cf))
        except Exception as e:
            errors.append(f"{cf}: {e}")
out_path = "/tmp/reddit_cookies.json"
with open(out_path, "w") as f:
    json.dump(found, f)
print(json.dumps({
    "count": len(found),
    "token_v2": bool(found.get("token_v2")),
    "keys": sorted(list(found.keys()))[:40],
    "errors": errors[:5],
    "path": out_path,
}))
"""


def extract_reddit_cookies(cookies_path: str | Path) -> bool:
    """
    Try each online bridge; run pycookiecheat on Chrome profiles for reddit.com;
    write JSON to cookies_path and /tmp/reddit_cookies.json.
    Return True if token_v2 present or any cookies written.
    """
    cookies_path = Path(os.path.expanduser(str(cookies_path)))
    online = list_online_machines()
    if not online:
        _log("extract_reddit_cookies: no online machines")
        return False

    # Prefer Macs; try Pro then Air then others
    ordered: List[Dict[str, Any]] = []
    for needle in ("pro", "air", ""):
        for m in online:
            if m in ordered:
                continue
            label = _machine_label(m).lower()
            if needle and needle not in label:
                continue
            ordered.append(m)
    for m in online:
        if m not in ordered:
            ordered.append(m)

    last_err = ""
    for m in ordered:
        bid = _bridge_id_of(m)
        if not bid:
            continue
        label = _machine_label(m)
        _log(f"trying cookie extract on {bid} ({label})")
        try:
            # Write helper script via python -c to avoid shell-quote hell
            write_cmd = (
                "python3 - <<'PY'\n"
                "from pathlib import Path\n"
                f"Path('/tmp/_rdb_extract_cookies.py').write_text({_EXTRACT_PY!r})\n"
                "print('wrote')\n"
                "PY"
            )
            bridge_exec(bid, write_cmd, timeout=30)
            out = bridge_exec(bid, "python3 /tmp/_rdb_extract_cookies.py 2>&1", timeout=45)
            _log(f"extract stdout: {out.strip()[:200]}")
            meta = _parse_cookies_payload(out) or {}
            if meta.get("__error__"):
                last_err = str(meta["__error__"])
                _log(f"remote extract error: {last_err}")
                continue

            raw = bridge_read(bid, "/tmp/reddit_cookies.json")
            cookies = _parse_cookies_payload(raw)
            if not cookies:
                last_err = f"empty/invalid cookies json from {bid}"
                _log(last_err)
                continue
            # Drop internal markers
            cookies = {k: v for k, v in cookies.items() if not str(k).startswith("__")}
            if not cookies:
                last_err = f"zero cookies from {bid}"
                _log(last_err)
                continue

            _write_cookies_files(cookies, cookies_path)
            has_token = bool(cookies.get("token_v2"))
            _log(
                f"wrote {len(cookies)} cookies to {cookies_path} "
                f"(token_v2={has_token}) via {bid}"
            )
            return True
        except Exception as e:
            last_err = str(e)
            _log(f"bridge {bid} extract failed: {e}")
            continue

    _log(f"extract_reddit_cookies failed on all bridges: {last_err}")
    return False


def _nlm_refresh_via_bridge(bridge_id: str) -> bool:
    """Extract NotebookLM cookies + csrf/sid from a bridge without KeyError."""
    cookie_script = r"""
import json, os
try:
    import pycookiecheat
except Exception as e:
    print('ERR import ' + str(e))
    raise SystemExit(1)
profiles = ['Default', 'Profile 1', 'Profile 2', 'Profile 3']
bases = [
    os.path.expanduser('~/Library/Application Support/Google/Chrome'),
    '/Users/niveshdandyan/Library/Application Support/Google/Chrome',
    '/Users/nivesh/Library/Application Support/Google/Chrome',
]
merged = {}
for base in bases:
    if not os.path.isdir(base):
        continue
    for p in profiles:
        cf = os.path.join(base, p, 'Cookies')
        if not os.path.exists(cf):
            continue
        try:
            merged.update(pycookiecheat.chrome_cookies('https://notebooklm.google.com', cookie_file=cf))
            merged.update(pycookiecheat.chrome_cookies('https://accounts.google.com', cookie_file=cf))
        except Exception:
            pass
storage = {
  'cookies': [
    {'name': k, 'value': v, 'domain': '.google.com', 'path': '/',
     'expires': -1, 'httpOnly': False, 'secure': True, 'sameSite': 'None'}
    for k, v in merged.items()
  ],
  'origins': []
}
open('/tmp/fresh_storage_nb.json','w').write(json.dumps(storage))
print(len(merged))
"""
    token_script = r"""
import subprocess, json
js = '(function(){var h=document.documentElement.innerHTML;'
js += 'var c=(h.match(/SNlM0e.:.([^\"]+)\"/) || [])[1]||\"\";'
js += 'var s=(h.match(/FdrFJe.:.([^\"]+)\"/) || [])[1]||\"\";'
js += "return c+'|||'+s;})();"
r = subprocess.run(
  ['osascript','-e','on run argv','-e','tell application "Google Chrome"',
   '-e','repeat with w in windows','-e','repeat with t in tabs of w',
   '-e','if URL of t contains "notebooklm.google.com" then',
   '-e','return execute t javascript (item 1 of argv)',
   '-e','end if','-e','end repeat','-e','end repeat',
   '-e','end tell','-e','end run','--',js],
  capture_output=True, text=True, timeout=15)
parts = r.stdout.strip().split('|||')
csrf = parts[0] if len(parts)>0 else ''
sid = parts[1] if len(parts)>1 else ''
open('/tmp/chrome_tokens_nb.json','w').write(json.dumps({'csrf':csrf,'sid':sid}))
print(f'{len(csrf)}|{sid}')
"""

    write_cookies = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"Path('/tmp/_rdb_nlm_cookies.py').write_text({cookie_script!r})\n"
        "print('ok')\n"
        "PY"
    )
    write_tokens = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"Path('/tmp/_rdb_nlm_tokens.py').write_text({token_script!r})\n"
        "print('ok')\n"
        "PY"
    )
    bridge_exec(bridge_id, write_cookies, timeout=20)
    count_out = bridge_exec(bridge_id, "python3 /tmp/_rdb_nlm_cookies.py 2>&1", timeout=30)
    storage_raw = bridge_read(bridge_id, "/tmp/fresh_storage_nb.json")
    NLM_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NLM_STORAGE_PATH.write_text(storage_raw, encoding="utf-8")
    _log(f"NLM cookies written ({count_out.strip()[:40]}) via {bridge_id}")

    bridge_exec(bridge_id, write_tokens, timeout=20)
    tok_out = bridge_exec(bridge_id, "python3 /tmp/_rdb_nlm_tokens.py 2>&1", timeout=30)
    tokens_raw = bridge_read(bridge_id, "/tmp/chrome_tokens_nb.json")
    tokens = _parse_cookies_payload(tokens_raw) or {}
    csrf = str(tokens.get("csrf") or "")
    sid = str(tokens.get("sid") or "")
    NLM_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    NLM_TOKENS_PATH.write_text(
        json.dumps({"csrf": csrf, "sid": sid}), encoding="utf-8"
    )
    _log(f"NLM tokens via {bridge_id}: csrf_len={len(csrf)} sid={sid!r} out={tok_out.strip()[:60]}")
    # Success if we at least wrote storage cookies OR non-empty tokens
    try:
        storage = json.loads(storage_raw)
        n_cookies = len(storage.get("cookies") or [])
    except Exception:
        n_cookies = 0
    return n_cookies > 0 or bool(csrf) or bool(sid)


def refresh_notebooklm_tokens() -> bool:
    """
    Try existing ~/.notebooklm/scripts/refresh_tokens.py first (wrapped — no KeyError leak).
    On failure, rediscover online bridges and extract tokens directly.
    Return False without raising if all paths fail.
    """
    # 1) Prefer existing script, fully guarded
    if NLM_REFRESH_SCRIPT.exists():
        try:
            result = subprocess.run(
                ["python3", str(NLM_REFRESH_SCRIPT), "--force"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0 and "Refresh failed" not in out and "KeyError" not in out:
                # Verify tokens not empty when file exists
                ok = True
                if NLM_TOKENS_PATH.exists():
                    try:
                        data = json.loads(NLM_TOKENS_PATH.read_text(encoding="utf-8"))
                        if not data.get("csrf") and not data.get("sid"):
                            ok = False
                            _log("existing refresh_tokens.py wrote empty csrf/sid — falling back")
                    except Exception:
                        ok = False
                if ok:
                    _log(f"NLM refresh via existing script OK: {out.strip()[-120:]}")
                    return True
            else:
                _log(
                    f"existing refresh_tokens.py failed (rc={result.returncode}): "
                    f"{out.strip()[:200]}"
                )
        except Exception as e:
            _log(f"existing refresh_tokens.py error (wrapped): {e}")
    else:
        _log(f"NLM refresh script missing: {NLM_REFRESH_SCRIPT}")

    # 2) Dynamic bridge discovery fallback
    online = list_online_machines()
    if not online:
        _log("refresh_notebooklm_tokens: no online machines")
        return False

    ordered: List[Dict[str, Any]] = []
    for needle in ("air", "pro", ""):
        for m in online:
            if m in ordered:
                continue
            if needle and needle not in _machine_label(m).lower():
                continue
            ordered.append(m)
    for m in online:
        if m not in ordered:
            ordered.append(m)

    for m in ordered:
        bid = _bridge_id_of(m)
        if not bid:
            continue
        try:
            if _nlm_refresh_via_bridge(bid):
                return True
        except Exception as e:
            # Never raise KeyError / missing data — soft fail per bridge
            _log(f"NLM refresh via {bid} failed: {e}")
            continue

    _log("refresh_notebooklm_tokens: all bridges failed")
    return False


def _cli_discover() -> int:
    online = list_online_machines()
    if not online:
        print("NONE")
        print("[auth] no online bridges (or CAPY env missing)")
        return 0
    print(f"online_count={len(online)}")
    for m in online:
        bid = _bridge_id_of(m) or "?"
        label = _machine_label(m).strip() or "(no label)"
        print(f"{bid}\t{label}\tonline={m.get('online')}")
    picked = pick_bridge()
    print(f"picked={picked or 'NONE'}")
    return 0


def _cli_extract_cookies(cookies_path: Path) -> int:
    ok = extract_reddit_cookies(cookies_path)
    if ok:
        _log(f"extract-cookies success → {cookies_path}")
        return 0
    _log("extract-cookies FAILED")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Dynamic bridge auth for reddit-daily-brief")
    parser.add_argument("--discover", action="store_true", help="List online bridges")
    parser.add_argument(
        "--extract-cookies",
        action="store_true",
        help="Extract Reddit cookies via online Mac bridge",
    )
    parser.add_argument(
        "--cookies-path",
        default=str(DEFAULT_COOKIES_PATH),
        help=f"Durable cookies path (default: {DEFAULT_COOKIES_PATH})",
    )
    parser.add_argument(
        "--refresh-nlm",
        action="store_true",
        help="Refresh NotebookLM tokens via discovery",
    )
    parser.add_argument(
        "--prefer",
        default=None,
        help="Prefer hostname/name substring when picking bridge (e.g. Pro, Air)",
    )
    args = parser.parse_args(argv)

    if not any([args.discover, args.extract_cookies, args.refresh_nlm]):
        parser.print_help()
        return 2

    rc = 0
    if args.discover:
        if args.prefer:
            bid = pick_bridge(prefer_hostname_substr=args.prefer)
            print(f"prefer={args.prefer!r} picked={bid or 'NONE'}")
        rc = max(rc, _cli_discover())
    if args.extract_cookies:
        rc = max(rc, _cli_extract_cookies(Path(os.path.expanduser(args.cookies_path))))
    if args.refresh_nlm:
        ok = refresh_notebooklm_tokens()
        rc = max(rc, 0 if ok else 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
