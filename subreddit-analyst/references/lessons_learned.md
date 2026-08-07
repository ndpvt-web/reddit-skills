# Lessons Learned — subreddit-analyst

Every mistake made during the first r/personalfinance run, with root cause and fix.
Read this before running ANY step so you don't repeat them.

---

## ARCTIC SHIFT FETCH

### ❌ Mistake 1: Wrong sort/order parameters
**What happened:** Used `sort=created_utc&order=desc` → API returned `{"error": "'order' is not a valid field"}`.
**Root cause:** Assumed the API mirrored common REST conventions.
**Fix:** Use `sort=asc` or `sort=desc` only. There is NO `order` parameter.
```python
params = {"sort": "asc"}   # CORRECT
# NOT: params = {"sort": "created_utc", "order": "desc"}
```

### ❌ Mistake 2: No incremental saving — crash lost 96,600 posts
**What happened:** Script collected 96,600 posts across ~966 pages then hit HTTP 422 (data gap near future dates). Script crashed before saving → ALL data lost. Had to re-fetch from scratch.
**Root cause:** Saving only at the end with no checkpointing.
**Fix:** Append each page's posts to a `.jsonl` file immediately. Also save the last timestamp to a separate file. This enables crash-safe resume.
```python
# After EVERY page:
for p in posts:
    out_f.write(json.dumps(p) + "\n")
out_f.flush()
RESUME_TS.write_text(after_fixed)  # save cursor
```

### ❌ Mistake 3: HTTP 422 caused unhandled crash
**What happened:** Arctic Shift returns 422 when querying dates beyond its data range (e.g., future dates). This crashed the script mid-run.
**Root cause:** `resp.raise_for_status()` without handling 422 specifically.
**Fix:** Treat 422 and 400 as "end of data" signals, not fatal errors. Stop and save gracefully.
```python
if resp.status_code in (422, 400):
    print("Data gap — stopping. Saving what we have.")
    break
resp.raise_for_status()
```

### ❌ Mistake 4: Hardcoded bridge ID in scripts
**What happened:** Used Mac Air bridge ID `br_eccb88c4e5504593999a36dd` which was offline. Mac Pro `br_cae5e0a4dee79bbeecd75145` was online.
**Root cause:** Hardcoded bridge ID from prior context.
**Fix:** Always query `/api/bridge/machines` at runtime to find the first online bridge.
```python
def find_online_bridge():
    r = requests.get(f"{CAPY_BASE}/api/bridge/machines?userId={CAPY_USER}", ...)
    for m in r.json()["machines"]:
        if m["online"]: return m["bridgeId"]
    return None
```

---

## NOTEBOOKLM CLI

### ❌ Mistake 5: Wrong flag position for `source add`
**What happened:** `notebooklm -n NOTEBOOK_ID source add ...` → error "No such option: -n".
**Root cause:** Assumed global flag worked before subcommands.
**Fix:** The notebook flag goes AFTER the subcommand:
```bash
# WRONG:
notebooklm -n NOTEBOOK_ID source add --title "T" file.md

# CORRECT:
notebooklm source add --notebook NOTEBOOK_ID --title "T" file.md
```

### ❌ Mistake 6: Used `--new` flag for `ask` (doesn't exist)
**What happened:** `notebooklm ask --new "question"` → "No such option: --new". All 26 queries failed.
**Root cause:** Help text says "Use --new to start fresh" but the flag isn't implemented.
**Fix:** Just omit `--new`. Each call continues the current conversation, which is fine.
```bash
# CORRECT (no --new):
notebooklm ask --notebook ID "question"
```

### ❌ Mistake 7: Ran upload script twice → duplicate sources
**What happened:** Ran `upload_to_notebooklm.py` twice → 28 sources (14 + 14 duplicates). Required manual cleanup.
**Fix:** Check for existing sources before uploading. Exit if they already exist.
```python
existing = subprocess.run([NLM, "source", "list", "--notebook", NB_ID], ...)
if "00_summary" in existing.stdout:
    print("Sources already exist. Aborting to avoid duplicates.")
    return
```

### ❌ Mistake 8: Auth token expiry mid-run (tokens last ~25-30 min)
**What happened:** Long analysis runs (40+ min) caused auth to expire mid-session → all queries returned auth errors.
**Root cause:** Tokens not refreshed between runs. Each `notebooklm ask` call doesn't auto-refresh.
**Fix:** Auto-refresh in the NLM query wrapper when auth errors are detected. Also refresh at script start.
```python
if "expired" in error_text.lower() or "authentication" in error_text.lower():
    refresh_auth()
    time.sleep(3)
    continue  # retry
```

### ❌ Mistake 9: 90s timeout too short for complex NLM queries
**What happened:** "What was the biggest viral post each month for 12 months?" took >90s → TimeoutExpired crash.
**Root cause:** Queries that span 12+ monthly sources take 120-180s to answer.
**Fix:** Use 180s timeout. Add retry on timeout.
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
```

### ❌ Mistake 10: NLM source file size — quarterly chunks too large
**What happened:** Quarterly chunks were 6-7MB each. While they uploaded, they were slow and potentially risky.
**Fix:** Split into MONTHLY chunks (~1-2MB each). More sources, but each processes faster.

---

## AI GATEWAY / LLM CALLS

### ❌ Mistake 11: `urllib.request` gets HTTP 403 from AI Gateway
**What happened:** Direct Python `urllib.request.urlopen()` → HTTP Error 403.
**Root cause:** The AI Gateway API rejects urllib's User-Agent or headers.
**Fix:** Use `subprocess` + `curl`. Curl works reliably.
```python
result = subprocess.run([
    "curl", "-s", "-X", "POST",
    f"{AI_BASE}/api/v1/chat/completions",
    "-H", f"Authorization: Bearer {AI_KEY}",
    "-H", "Content-Type: application/json",
    "-H", "Accept-Encoding: identity",   # CRITICAL — prevents gzip decode errors
    "-d", f"@{tmpfile}",
], ...)
```

### ❌ Mistake 12: gzip decode errors from AI Gateway
**What happened:** `requests.ContentDecodingError: ('Received response with content-encoding: gzip, but failed to decode it.')`
**Root cause:** API returns gzip encoding but the response decompression fails.
**Fix:** Add `Accept-Encoding: identity` header to disable gzip compression.
```python
headers["Accept-Encoding"] = "identity"
```

### ❌ Mistake 13: Wrong model name format
**What happened:** `anthropic/claude-sonnet-4-6` (hyphen) → model_access_denied.
**Root cause:** Model names use a period before version number, not hyphen.
**Fix:** Use `anthropic/claude-sonnet-4.6` (PERIOD, not hyphen). Check allowed model list first.
```python
# WRONG: "anthropic/claude-sonnet-4-6"
# CORRECT: "anthropic/claude-sonnet-4.6"
```

### ❌ Mistake 14: model_access_denied — do NOT retry with different model
**What happened:** Attempted to swap models when one was denied, which violates gateway policy.
**Fix:** Per AI Gateway instructions: when error.code === "model_access_denied", STOP. Do not retry. Let the UI show the upgrade prompt.

---

## WORKFLOW DESIGN

### ❌ Mistake 15: Pre-defined query list instead of dynamic follow-ups
**What happened:** All 26 analysis questions were hardcoded upfront → many were redundant or missed important angles revealed by earlier answers.
**User feedback:** "do not write the pre-defined script questions to ask — instead decide on the go according to the previous answer!"
**Fix:** Round 1 = ~10 seed questions. Rounds 2-3 = questions generated by LLM based on what was surprising/important in each previous answer.

### ❌ Mistake 16: No resume capability in analysis script
**What happened:** If the analysis script crashed mid-run (timeout, auth error), all query results were lost.
**Fix:** Save each Q&A result to a JSON file immediately after receiving it. Load on startup to skip already-answered questions.

---

## CHECKLIST FOR EVERY NEW SUBREDDIT RUN

Before starting, verify:
- [ ] At least one Mac bridge is online (`/api/bridge/machines`)
- [ ] Chrome is open on that Mac
- [ ] NotebookLM tab is open in Chrome (needed for f.sid extraction)
- [ ] `notebooklm list` works (tokens are fresh)
- [ ] `tmp/` directory exists for intermediate files
- [ ] `outputs/` directory exists for final HTML report

Watch out for:
- [ ] Don't run `upload_to_notebooklm.py` twice (check sources first)
- [ ] Don't hardcode bridge IDs
- [ ] Don't use urllib for AI Gateway (use curl)
- [ ] Don't use `notebooklm -n ID source add` (wrong flag position)
- [ ] Don't use `notebooklm ask --new` (flag doesn't exist)
