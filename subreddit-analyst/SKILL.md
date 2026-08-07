---
name: subreddit-analyst
description: >
  End-to-end subreddit intelligence pipeline: Arctic Shift fetch → NotebookLM notebook
  → dynamic 3-round NLM analysis → HappyCapy fit-check → acquisition strategy → ops directory.
  Trigger when user asks to: analyse a subreddit, deep dive r/X, research a subreddit,
  check if r/X is good for HappyCapy, do a fit check, run the subreddit pipeline,
  get user acquisition strategy for r/X, understand a Reddit community, or collect
  subreddit data. Also trigger for "what works on r/X", "what goes viral on r/X",
  or any Reddit community analysis even without saying "subreddit-analyst" explicitly.
---

# Subreddit Analyst — Full Pipeline

One command, one subreddit name → complete analysis + HappyCapy acquisition strategy + structured ops directory.

---

## Pipeline Overview

```
User gives: subreddit name (+ optional timeframe)
           ↓
Phase 1: DATA COLLECTION
  → Arctic Shift fetch (checkpoint-based, crash-safe)
  → Create NotebookLM notebook
  → Upload monthly chunks
           ↓
Phase 2: GENERAL ANALYSIS
  → 10 seed queries (viral mechanics, culture, topics, emotions, etc.)
  → Dynamic follow-ups (AI generates questions based on each answer)
  → Synthesis → HTML report
           ↓
Phase 3: HAPPYCAPY FIT-CHECK
  → Read HappyCapy platform overview + outcome marketing playbook
  → 10 acquisition-focused seed queries
  → Deep dynamic follow-ups (20-40+ total questions)
  → Fit assessment matrix + Go/No-Go scoring
  → Full acquisition strategy
           ↓
Phase 4: OPS DIRECTORY
  → Create ops/{subreddit}/ with all context files
  → README, notebook-info, community-rules, fit-check, strategy
  → Update workspace CLAUDE.md
  → HTML report in outputs/
```

---

## Before Starting: Pre-Flight Checklist

```bash
# 1. Check Mac bridge is online (needed for NLM auth refresh)
curl -s -H "Authorization: Bearer $CAPY_SECRET" \
  "$CAPY_BASE_URL/api/bridge/machines?userId=$CAPY_USER_ID" | \
  python3 -c "import sys,json; [print(m['bridgeId'],m['online']) for m in json.load(sys.stdin)['machines']]"

# 2. Verify NLM auth works
~/.local/bin/notebooklm list 2>&1 | head -3

# 3. If auth fails, refresh:
python3 ~/.claude/skills/subreddit-analyst/scripts/refresh_nlm_tokens.py --force

# 4. Ensure workspace dirs exist
mkdir -p tmp outputs ops
```

If the Mac bridge is offline AND NLM auth fails: stop and tell the user. You cannot proceed without NotebookLM access.

---

## Phase 1: Data Collection

### Step 1.1 — Fetch via Arctic Shift

```bash
python3 ~/.claude/skills/subreddit-analyst/scripts/fetch_arctic_shift.py \
  --subreddit SUBREDDIT_NAME \
  --after YYYY-MM-DD \
  --before YYYY-MM-DD \
  --outdir tmp/SUBREDDIT_NAME
```

Default timeframe: last 1 year from current date.

The script is **crash-safe and resumable** — it checkpoints after every 100-post page. If interrupted, rerun the same command.

**Expect:** ~100-200 posts/minute. Large subs (5M+ members) take 20-30 min. Small subs (<500K) take 2-5 min.

### Step 1.2 — Create NotebookLM Notebook

```bash
~/.local/bin/notebooklm create "r/SUBREDDIT — 1 Year Archive (YYYY–YYYY)" --json
```

Save the returned notebook ID — you'll need it for everything that follows.

### Step 1.3 — Upload Monthly Chunks

```bash
python3 ~/.claude/skills/subreddit-analyst/scripts/upload_to_notebooklm.py \
  --json tmp/SUBREDDIT_NAME/reddit_raw_full.json \
  --notebook NOTEBOOK_ID \
  --outdir tmp/SUBREDDIT_NAME/nlm_chunks
```

The script auto-splits into monthly files (~1-2MB each) and checks for existing sources to prevent duplicates.

---

## Phase 2: General Subreddit Analysis

```bash
python3 ~/.claude/skills/subreddit-analyst/scripts/dynamic_analysis.py \
  --notebook NOTEBOOK_ID \
  --subreddit SUBREDDIT_NAME \
  --results tmp/SUBREDDIT_NAME/dynamic_results.json \
  --synthesis tmp/SUBREDDIT_NAME/synthesis.md
```

This runs 3 rounds automatically:
- Round 1: 10 seed questions (viral mechanics, failure patterns, culture, emotions, topics, demographics, formula, norms, monthly highlights, success stories)
- Round 2: AI-generated follow-ups based on surprising findings in each Round 1 answer
- Round 3: Deep dives into the most interesting Round 2 findings

**If synthesis fails** (known issue — the AI Gateway call for large synthesis prompts can timeout): run synthesis manually with `curl --max-time 200` via the pattern in `references/lessons_learned.md`.

### Build General HTML Report

```bash
python3 ~/.claude/skills/subreddit-analyst/scripts/build_report.py \
  --synthesis tmp/SUBREDDIT_NAME/synthesis.md \
  --subreddit SUBREDDIT_NAME \
  --stats tmp/SUBREDDIT_NAME/reddit_raw_full.json \
  --output outputs/SUBREDDIT_NAME_analysis.html
```

---

## Phase 3: HappyCapy Fit-Check

This is where the pipeline becomes HappyCapy-specific. The general analysis tells you WHAT the community is. The fit-check tells you WHETHER and HOW HappyCapy can acquire users there.

### Step 3.0 — Read HappyCapy Context (MANDATORY)

Before running ANY acquisition query, read these two files completely:

1. **`~/.claude/happycapy-platform-overview.md`** — What HappyCapy IS: full cloud computer + AI agent, root access, always-on, model gateway, skill store, Publish/Remix, Mac bridge. The agent needs to understand HappyCapy's actual capabilities to assess fit.

2. **`~/.claude/happycapy-outcome-marketing.md`** — How HappyCapy MARKETS itself: the 5 primal outcomes (Money, Time, Freedom, Status, Peace of Mind), the 6 transformation themes, 25 sector breakdowns, before/after stories, positioning cheat-sheet. The agent needs this to craft positioning specific to the subreddit.

Without these files, the agent cannot assess fit or write strategy. They provide the "what can we offer?" half of the equation.

### Step 3.1 — Acquisition-Focused Seed Queries

Run these 10 queries against the SAME NotebookLM notebook (it already has the sub's data):

| # | Category | Query |
|---|----------|-------|
| 1 | Builder Pain Points | "What are the most common pain points, frustrations, and complaints expressed in this community? Rank the top 12 recurring struggles with specific examples." |
| 2 | Technical Skill Mix | "What is the technical skill level of people here? How many are non-technical vs experienced? What do non-coders struggle with and wish they could do?" |
| 3 | AI/Tool Sentiment | "How does this community react to AI tools, AI agents, no-code builders, automation platforms? Are they welcomed or do they get backlash? Give specific examples." |
| 4 | What Gets Adopted | "When someone shares a tool here, what makes the community actually TRY it? What types of tools get 'I'll use this' responses vs ignored?" |
| 5 | Self-Promo Norms | "What are the rules and unwritten norms around self-promotion? What kind of promotional posts are accepted vs downvoted/removed as spam?" |
| 6 | Launch Success Patterns | "What do the most successful product/tool launch posts have in common? Format, story, demo, transparency?" |
| 7 | Removal & Backlash Triggers | "What gets posts removed, downvoted, or attacked? What behaviors or framings trigger backlash?" |
| 8 | Unmet Needs / Wishlist | "What tools, services, or capabilities do people WISH existed or ask for help with? Where do they say 'how do I…' or 'is there a tool that…'?" |
| 9 | Competitor Landscape | "What tools, platforms, and services are mentioned most? Which are loved, which are complained about, and why? Where are the gaps?" |
| 10 | Audience Identity | "Who is the typical member as a person — their identity, aspirations, what success looks like, and what emotional rewards they seek?" |

### Step 3.2 — Dynamic Follow-Ups (THE CRITICAL PART)

The 10 seeds are just the starting point. The real depth comes from chasing each answer.

**After every answer, ask yourself:**
- What's surprising here that I didn't expect?
- What claims need evidence? ("they hate AI" → which AI projects SUCCEEDED and why?)
- What contradictions exist? ("they love tools" + "they hate promo" → how do winners thread the needle?)
- What would I need to know to predict their reaction to a HappyCapy post?

**Generate 2-3 follow-up questions per answer. Keep going deeper until you can confidently say:**
- I understand WHY they behave this way (root causes, not patterns)
- I can predict how they'd react to a HappyCapy-related post
- I have enough specific examples to build concrete strategy

Expect **20-40+ total questions** across all rounds. Do NOT stop at 10.

**Types of dynamic questions:**
- Exceptions: "Despite X, what cases went the other way? Why?"
- Mechanisms: "What specifically causes Y — mods, voting, or comment culture?"
- Comparisons: "How do posts about A perform vs posts about B?"
- Deep zooms: "Tell me everything about [specific example mentioned]"
- Hypotheticals: "If someone posted [description], how would they react?"
- Cross-cutting: "How does [finding from Q3] interact with [finding from Q7]?"

### Step 3.3 — Fit Assessment Matrix

After collecting all answers, build this matrix:

**Pain-to-Capability Match:** For each top pain point, answer:
- Does HappyCapy solve this? (Yes / Partially / No)
- Is it a UNIQUE solve or a me-too solve?
- Can it be demonstrated without requiring signup?

**ICP Overlap:** Cross-reference audience identity against HappyCapy's 25 sectors and 5 primal outcomes. Which transformation theme resonates most?

**Channel Risk:** How hostile to AI/automation? How strict on self-promo? What words/framings are banned?

**Competitive Wedge:** What lane are competitors fighting over? Where is the GAP only HappyCapy can fill?

### Step 3.4 — Go/No-Go Scoring

Score 5 dimensions (1-10):

| Dimension | Score |
|-----------|-------|
| ICP overlap | ? |
| Pain-capability fit | ? |
| Channel receptivity | ? |
| Competitive whitespace | ? |
| Structural virality potential | ? |

- **40+** → GREEN (strong channel, invest heavily)
- **25-39** → YELLOW (viable but careful strategy needed)
- **<25** → RED (poor fit, don't invest)

### Step 3.5 — Write Strategy

If Green or Yellow, write the full acquisition strategy:
- Positioning statement (internal line for this sub specifically)
- Ranked acquisition vectors (5-7, each with: what to do, how to frame, risk, speed, measurement)
- Hard rules (5-8 "never do this" rules)
- Honest assessment (timeline, max addressable audience, risk if wrong)

---

## Phase 4: Ops Directory & Output

### Step 4.1 — Create the ops directory

```
ops/SUBREDDIT_NAME/
├── README.md           — Quick context for any agent (positioning, vectors, scores)
├── notebook-info.json  — Notebook ID, post counts, file paths, fit score
├── community-rules.md  — Hard rules, soft rules, authenticity tax, AI guidance
├── fit-check.md        — All NLM query answers (raw acquisition data)
└── strategy.md         — Full acquisition strategy + ranked vectors
```

### Step 4.2 — File Formats

**README.md** should contain:
- Subreddit name, member count, notebook ID, post count
- Fit score (GREEN/YELLOW/RED + number)
- 3-line summary of who's here
- Their #1 pain that HappyCapy solves
- The landmine (what kills you here)
- What works (3-5 bullet points)
- HappyCapy positioning for this sub specifically
- Ranked acquisition vectors (one-liner each)
- How to query the notebook

**notebook-info.json:**
```json
{
  "subreddit": "...",
  "notebook_id": "...",
  "posts_count": ...,
  "unique_authors": ...,
  "period": "YYYY-MM-DD to YYYY-MM-DD",
  "max_score": ...,
  "category": "...",
  "fit_score": "GREEN (42/50)",
  "fit_check_status": "COMPLETE",
  "data_files": { ... }
}
```

**community-rules.md:** Hard rules (violating = removed), soft rules (violating = downvoted), the authenticity tax, what gets maximum engagement, AI-specific guidance.

### Step 4.3 — Update CLAUDE.md

Add the new subreddit to the ops status table in the workspace CLAUDE.md file so future agents can discover it.

### Step 4.4 — Final HTML Report

Build the strategy as an HTML report:
```bash
python3 ~/.claude/skills/subreddit-analyst/scripts/build_report.py \
  --synthesis ops/SUBREDDIT_NAME/strategy.md \
  --subreddit "SUBREDDIT_NAME — HappyCapy Acquisition" \
  --stats tmp/SUBREDDIT_NAME/reddit_raw_full.json \
  --output outputs/happycapy_SUBREDDIT_NAME_strategy.html
```

---

## Lessons Learned (Read Before Every Run)

Full details in `references/lessons_learned.md`. The critical ones:

| Mistake | Fix |
|---------|-----|
| `sort=desc&order=desc` → API error | Use `sort=asc` only. No `order` param exists. |
| No checkpointing → 96K posts lost on crash | Script checkpoints every page (already built in). |
| HTTP 422 crash | Treat as "end of data" — stop and save gracefully. |
| Hardcoded bridge ID | Always query `/api/bridge/machines` at runtime. |
| `notebooklm -n ID source add` → wrong flag position | Use `source add --notebook ID --title T file.md` |
| `notebooklm ask --new` → flag doesn't exist | Just omit it. |
| Ran upload twice → duplicates | Script checks existing sources first. |
| Auth expires every ~25 min | Scripts auto-refresh on auth error. |
| 90s timeout for NLM queries → crash | Use 180s timeout + retry. |
| Quarterly chunks (7MB) → slow | Monthly chunks (~1-2MB each). |
| `urllib.request` → 403 from AI Gateway | Use `subprocess + curl` with `Accept-Encoding: identity`. |
| Synthesis curl times out at 120s | Use `--max-time 200`. |
| Model name `4-6` (hyphen) → access denied | Use `4.6` (period). Format: `anthropic/claude-sonnet-4.6` |

---

## Handling Errors

**NLM auth expired:**
```bash
python3 ~/.claude/skills/subreddit-analyst/scripts/refresh_nlm_tokens.py --force
```
Requires: Mac bridge online + Chrome open + NotebookLM tab open in Chrome.

**Synthesis step fails (known issue):**
The `dynamic_analysis.py` synthesis call often timeouts because the prompt is large. Fix: run synthesis manually with curl and a 200s timeout. See the pattern used in this session (search for `--max-time 200` in the working examples).

**Arctic Shift 422 error:**
Normal — means you hit the edge of available data. The script stops and saves what it has.

**Mac bridge offline:**
Cannot refresh NLM tokens. Ask the user to bring a Mac online or check if cached tokens still work.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/lessons_learned.md` | Before every run — 16 documented mistakes |
| `scripts/fetch_arctic_shift.py` | Runs automatically — checkpoint-based fetcher |
| `scripts/refresh_nlm_tokens.py` | Auto-detects online Mac bridge |
| `scripts/upload_to_notebooklm.py` | Formats + uploads monthly chunks |
| `scripts/dynamic_analysis.py` | 3-round dynamic query harness |
| `scripts/build_report.py` | Synthesis → dark-mode HTML report |
| `~/.claude/happycapy-platform-overview.md` | Phase 3 — what HappyCapy is |
| `~/.claude/happycapy-outcome-marketing.md` | Phase 3 — how HappyCapy markets |

---

## Example: Full Run for r/SomeSubreddit

```bash
SUB="SomeSubreddit"

# Phase 1
python3 scripts/fetch_arctic_shift.py --subreddit "$SUB" --after 2025-06-17 --before 2026-06-17 --outdir "tmp/$SUB"
NB_ID=$(~/.local/bin/notebooklm create "r/$SUB — 1 Year Archive" --json | python3 -c "import sys,json; print(json.load(sys.stdin)['notebook']['id'])")
python3 scripts/upload_to_notebooklm.py --json "tmp/$SUB/reddit_raw_full.json" --notebook "$NB_ID"

# Phase 2
python3 scripts/dynamic_analysis.py --notebook "$NB_ID" --subreddit "$SUB" --results "tmp/$SUB/dynamic_results.json" --synthesis "tmp/$SUB/synthesis.md"
python3 scripts/build_report.py --synthesis "tmp/$SUB/synthesis.md" --subreddit "$SUB" --stats "tmp/$SUB/reddit_raw_full.json" --output "outputs/${SUB}_analysis.html"

# Phase 3 — agent reads HappyCapy files, runs acquisition queries manually (dynamic, not scripted)

# Phase 4 — agent creates ops/$SUB/ directory with all files
```

Phase 3 is intentionally NOT fully automated — the dynamic questioning requires the agent to think, read each answer, and decide what to ask next. This cannot be reduced to a script.
