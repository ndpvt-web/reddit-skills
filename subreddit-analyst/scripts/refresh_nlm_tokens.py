#!/usr/bin/env python3
"""
Refresh NotebookLM Chrome session tokens from the online Mac bridge.

Finds the first ONLINE bridge, runs pycookiecheat + osascript, and
saves fresh cookies + CSRF/SID to ~/.notebooklm/.

Key lessons baked in:
  - Never hardcode a bridge ID — query the machines list for the online one
  - Use subprocess + curl, NOT urllib.request (urllib gets HTTP 403 from bridge API)
  - Need both cookies AND the live f.sid from an open NotebookLM tab
  - If no NLM tab is open, osascript returns empty SID → tokens won't work
  - Chrome must be open on the Mac for pycookiecheat to work
"""
import json, os, subprocess, base64, time, sys
from pathlib import Path

CAPY_SECRET = os.environ.get("CAPY_SECRET", "")
CAPY_USER   = os.environ.get("CAPY_USER_ID", "")
CAPY_BASE   = os.environ.get("CAPY_BASE_URL", "https://happycapy.ai")

NLM_DIR     = Path.home() / ".notebooklm"
TOKENS_PATH = NLM_DIR / "chrome_tokens.json"
STORAGE_PATH = NLM_DIR / "profiles" / "default" / "storage_state.json"
MAX_AGE_MIN = 25


def is_stale(path: Path) -> bool:
    if not path.exists():
        return True
    return (time.time() - path.stat().st_mtime) / 60 > MAX_AGE_MIN


def find_online_bridge() -> str | None:
    """Query machines API and return the first online bridge ID."""
    result = subprocess.run([
        "curl", "-s",
        "-H", f"Authorization: Bearer {CAPY_SECRET}",
        f"{CAPY_BASE}/api/bridge/machines?userId={CAPY_USER}",
    ], capture_output=True, text=True, timeout=15)
    data = json.loads(result.stdout)
    for m in data.get("machines", []):
        if m.get("online"):
            return m["bridgeId"]
    return None


def bridge_exec(bridge_id: str, command: str, timeout: int = 30) -> dict:
    """Run a command on the Mac bridge via curl."""
    body = json.dumps({
        "userId": CAPY_USER,
        "bridgeId": bridge_id,
        "command": "terminal/exec",
        "payload": {"command": command, "timeout": timeout},
    })
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {CAPY_SECRET}",
        "-H", "Content-Type: application/json",
        "-d", body,
        f"{CAPY_BASE}/api/bridge/command",
    ], capture_output=True, text=True, timeout=timeout + 10)
    return json.loads(result.stdout)


def bridge_read(bridge_id: str, path: str) -> str | None:
    """Read a file from the Mac bridge (base64-encoded)."""
    body = json.dumps({
        "userId": CAPY_USER,
        "bridgeId": bridge_id,
        "command": "files/read",
        "payload": {"path": path, "encoding": "base64"},
    })
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {CAPY_SECRET}",
        "-H", "Content-Type: application/json",
        "-d", body,
        f"{CAPY_BASE}/api/bridge/command",
    ], capture_output=True, text=True, timeout=20)
    r = json.loads(result.stdout)
    if r.get("data"):
        return base64.b64decode(r["data"]["content"]).decode()
    return None


def refresh(force: bool = False):
    if not force and not is_stale(TOKENS_PATH):
        age = (time.time() - TOKENS_PATH.stat().st_mtime) / 60
        print(f"Tokens fresh ({age:.0f}m old). Skipping.")
        return True

    bridge_id = find_online_bridge()
    if not bridge_id:
        print("ERROR: No Mac bridge is online. Cannot refresh tokens.")
        return False

    print(f"Refreshing via bridge {bridge_id}...", flush=True)

    # Detect Mac username
    r = bridge_exec(bridge_id, "whoami")
    mac_user = r.get("data", {}).get("stdout", "").strip() or "nivesh"

    chrome_path = f"/Users/{mac_user}/Library/Application Support/Google/Chrome/Default/Cookies"

    # Cookie extraction script
    cookie_script = f"""import pycookiecheat, json
cf = '{chrome_path}'
c  = pycookiecheat.chrome_cookies('https://notebooklm.google.com', cookie_file=cf)
c2 = pycookiecheat.chrome_cookies('https://accounts.google.com', cookie_file=cf)
merged = {{**c2, **c}}
storage = {{'cookies': [
  {{'name': k, 'value': v, 'domain': '.google.com', 'path': '/',
   'expires': -1, 'httpOnly': False, 'secure': True, 'sameSite': 'None'}}
  for k, v in merged.items()], 'origins': []}}
with open('/tmp/nlm_cookies_refresh.json', 'w') as f: json.dump(storage, f)
print(len(merged))
"""
    # Write and run cookie script
    bridge_exec(bridge_id, f"cat > /tmp/nlm_cookie_extract.py << 'PYEOF'\n{cookie_script}\nPYEOF")
    r = bridge_exec(bridge_id, "python3 /tmp/nlm_cookie_extract.py 2>&1")
    count_out = r.get("data", {}).get("stdout", "").strip()
    print(f"  Cookies extracted: {count_out}")

    # Token extraction script (CSRF + f.sid from live Chrome tab)
    token_script = """import subprocess, json
js = ('(function(){'
      'var h=document.documentElement.innerHTML;'
      'var c=(h.match(/SNlM0e.:.([^"]+)"/) || [])[1]||"";'
      'var s=(h.match(/FdrFJe.:.([^"]+)"/) || [])[1]||"";'
      "return c+'|||'+s;})();")
r = subprocess.run(
  ['osascript','-e','on run argv','-e','tell application "Google Chrome"',
   '-e','repeat with w in windows','-e','repeat with t in tabs of w',
   '-e','if URL of t contains "notebooklm.google.com" then',
   '-e','return execute t javascript (item 1 of argv)',
   '-e','end if','-e','end repeat','-e','end repeat',
   '-e','end tell','-e','end run','--', js],
  capture_output=True, text=True, timeout=15)
parts = r.stdout.strip().split('|||')
csrf = parts[0] if len(parts)>0 else ''
sid  = parts[1] if len(parts)>1 else ''
with open('/tmp/nlm_tokens_refresh.json','w') as f: json.dump({'csrf':csrf,'sid':sid},f)
print(f'CSRF={len(csrf)},SID={sid[:15]}')
"""
    bridge_exec(bridge_id, f"cat > /tmp/nlm_token_extract.py << 'PYEOF'\n{token_script}\nPYEOF")
    r = bridge_exec(bridge_id, "python3 /tmp/nlm_token_extract.py 2>&1")
    tok_out = r.get("data", {}).get("stdout", "").strip()
    print(f"  Tokens: {tok_out}")

    # Pull files back and save locally
    storage_content = bridge_read(bridge_id, "/tmp/nlm_cookies_refresh.json")
    tokens_content  = bridge_read(bridge_id, "/tmp/nlm_tokens_refresh.json")

    if not storage_content or not tokens_content:
        print("ERROR: Could not read token files from Mac.")
        return False

    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORAGE_PATH.write_text(storage_content)
    TOKENS_PATH.write_text(tokens_content)

    tokens = json.loads(tokens_content)
    if not tokens.get("csrf"):
        print("WARNING: CSRF token is empty — NotebookLM tab may not be open in Chrome.")
        return False

    print("  Refresh complete.")
    return True


if __name__ == "__main__":
    force = "--force" in sys.argv
    ok = refresh(force=force)
    sys.exit(0 if ok else 1)
