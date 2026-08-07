#!/usr/bin/env python3
"""
Dynamic multi-round NotebookLM analysis harness.

Flow:
  Round 1: Ask seed questions
  Round 2: LLM reads each answer → generates follow-up questions
  Round 3: LLM reads round-2 answers → generates deep-dive questions
  Final:   Synthesize all Q&A into a comprehensive report

Usage:
  python3 dynamic_analysis.py --notebook NOTEBOOK_ID --subreddit personalfinance \
    --outdir tmp --results tmp/dynamic_results.json

Key lessons baked in:
  - Auth expires ~25-30 min; auto-refresh before every CLI call
  - `notebooklm ask --notebook ID "question"` — no --new flag (doesn't exist)
  - NLM queries for complex questions take 60-180s; use 180s timeout with retries
  - Use subprocess + curl for AI Gateway calls (urllib gets 403)
  - Set Accept-Encoding: identity to avoid gzip decode errors
  - Model anthropic/claude-sonnet-4.6 (with PERIOD not HYPHEN before version)
  - Save results incrementally after every answer (crash-safe)
  - Round 2/3 questions are GENERATED from answers, not hardcoded
"""
import argparse, subprocess, json, time, os, sys
from pathlib import Path

NLM         = str(Path.home() / ".local/bin/notebooklm")
AI_BASE     = os.environ.get("AI_GATEWAY_BASE_URL", "")
AI_KEY      = os.environ.get("AI_GATEWAY_API_KEY", "")
REFRESH_SCRIPT = Path(__file__).parent / "refresh_nlm_tokens.py"


# ─── AUTH REFRESH ─────────────────────────────────────────────────────────────
def refresh_auth():
    result = subprocess.run(
        ["python3", str(REFRESH_SCRIPT), "--force"],
        capture_output=True, text=True, timeout=60
    )
    print(f"  [auth] {result.stdout.strip()[-100:]}")
    return result.returncode == 0


# ─── NLM QUERY ────────────────────────────────────────────────────────────────
def ask_nlm(notebook_id: str, question: str) -> str:
    cmd = [NLM, "ask", "--notebook", notebook_id, question]
    for attempt in range(3):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            out = result.stdout.strip()
            err = (result.stderr or "").strip()
            if result.returncode != 0:
                combined = (err or out)[:300]
                if any(w in combined.lower() for w in ["expired", "authentication", "mismatch", "login"]):
                    print(f"  [auth] Attempt {attempt+1}: token expired, refreshing...")
                    refresh_auth()
                    time.sleep(3)
                    continue
                return f"ERROR: {combined}"
            text = out
            if text.startswith("Answer:"):
                text = text[7:].strip()
            lines = text.split("\n")
            while lines and (lines[-1].startswith("Conversation:") or lines[-1].startswith("Resumed")):
                lines.pop()
            return "\n".join(lines).strip()
        except subprocess.TimeoutExpired:
            if attempt < 2:
                print(f"  [nlm] Timeout (attempt {attempt+1}), retrying...")
                time.sleep(5)
            else:
                return "TIMEOUT"
    return "TIMEOUT_AFTER_RETRIES"


# ─── AI GATEWAY CALL (via curl) ───────────────────────────────────────────────
def llm_call(prompt: str, model: str = "anthropic/claude-sonnet-4.6", max_tokens: int = 600) -> str:
    """
    IMPORTANT: Use curl via subprocess, NOT urllib.request.
    urllib gets HTTP 403 from the AI Gateway.
    Set Accept-Encoding: identity to prevent gzip decode errors.
    Model format: anthropic/claude-sonnet-4.6 (period before version, not hyphen).
    """
    import tempfile
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.5,
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(body)
        tmpf = f.name

    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST",
            f"{AI_BASE}/api/v1/chat/completions",
            "-H", f"Authorization: Bearer {AI_KEY}",
            "-H", "Content-Type: application/json",
            "-H", "Accept-Encoding: identity",
            "-d", f"@{tmpf}",
        ], capture_output=True, text=True, timeout=60)
        data = json.loads(result.stdout)
        if "error" in data:
            code = data["error"].get("code","") if isinstance(data["error"], dict) else ""
            if code == "model_access_denied":
                # Per AI Gateway instructions: stop, do not retry with different model
                print(f"  [llm] model_access_denied for {model}. Stopping.")
                return ""
            print(f"  [llm] Error: {str(data['error'])[:200]}")
            return ""
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [llm] Exception: {e}")
        return ""
    finally:
        Path(tmpf).unlink(missing_ok=True)


# ─── DYNAMIC QUESTION GENERATOR ──────────────────────────────────────────────
def gen_followups(category: str, question: str, answer: str, already_asked: list) -> list:
    if not answer or answer.startswith(("ERROR", "TIMEOUT")):
        return []
    already_str = "\n".join(f"- {q}" for q in already_asked[-15:])
    prompt = f"""You are analyzing r/personalfinance Reddit data.

CATEGORY: {category}
QUESTION: {question}
ANSWER: {answer[:1200]}

ALREADY ASKED (do not repeat):
{already_str}

Generate exactly 2 sharp follow-up questions that drill deeper.
Rules:
- Build directly on SPECIFIC surprising findings in the answer
- Seek root causes and mechanisms, not more surface patterns
- Each question must be different from all already-asked questions
- Be concrete, not vague

Return ONLY a JSON array: ["Question 1?", "Question 2?"]"""

    raw = llm_call(prompt, max_tokens=300)
    if not raw:
        return []
    try:
        import re
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            qs = json.loads(match.group())
            return [q for q in qs if q not in already_asked][:2]
    except Exception:
        pass
    return []


# ─── SYNTHESIS ────────────────────────────────────────────────────────────────
def synthesize(subreddit: str, all_qa: list) -> str:
    good = [x for x in all_qa if not x["answer"].startswith(("ERROR", "TIMEOUT"))]
    qa_text = ""
    for item in good[:40]:
        qa_text += f"\n\n## {item['category'].upper()} (Round {item['round']})\n"
        qa_text += f"**Q:** {item['question']}\n\n**A:** {item['answer'][:700]}\n"

    prompt = f"""You have deep research data about r/{subreddit} (Reddit).

{qa_text}

Write a COMPREHENSIVE FIRST-PRINCIPLES ANALYSIS REPORT. Be extremely specific.
Use this structure:

# r/{subreddit} — Deep Analysis Report

## 1. WHAT GOES VIRAL
### 1.1 Title Formulas (with real examples)
### 1.2 Narrative Structures
### 1.3 Life Events That Always Perform
### 1.4 Numbers & Dollar Amounts That Resonate

## 2. WHAT FAILS (Root Causes)
### 2.1 Fatal Patterns
### 2.2 Why Posts Get Ignored (psychological reasons)

## 3. SUBREDDIT CULTURE
### 3.1 Core Values & Worldview
### 3.2 Heroes & Villains
### 3.3 Canon Wisdom (top 15 recurring pieces of advice)
### 3.4 Controversial Fault Lines

## 4. DEMOGRAPHICS & PSYCHOGRAPHICS
### 4.1 Who Is Here
### 4.2 Their Fears & Aspirations

## 5. TOPIC LANDSCAPE
### 5.1 Top 15 Topics (volume + engagement)
### 5.2 Seasonal Patterns

## 6. EMOTIONAL TRIGGERS
### 6.1 Emotion Hierarchy
### 6.2 Transformation & Crisis Posts

## 7. THE VIRAL FORMULA (Step-by-Step Recipe)

## 8. WHAT MAKES r/{subreddit} UNIQUE
### 8.1 The Social Contract
### 8.2 Blind Spots

Be SPECIFIC. Cite actual post titles, scores, examples from data. Use markdown."""

    return llm_call(prompt, model="anthropic/claude-sonnet-4.6", max_tokens=5000)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook",  required=True)
    ap.add_argument("--subreddit", required=True)
    ap.add_argument("--results",   default="tmp/dynamic_results.json")
    ap.add_argument("--synthesis", default="tmp/synthesis.md")
    args = ap.parse_args()

    results_path = Path(args.results)

    # Load existing (for resume)
    all_results  = []
    already_asked = []
    if results_path.exists():
        all_results   = json.loads(results_path.read_text())
        already_asked = [x["question"] for x in all_results]
        print(f"Resuming: {len(all_results)} Q&A pairs already saved")

    def save():
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(all_results, indent=2))

    # Initial auth check
    print("Checking NLM auth...")
    test = ask_nlm(args.notebook, f"How many total posts are in the r/{args.subreddit} notebook?")
    if test.startswith("ERROR"):
        print(f"Auth check failed: {test}")
        sys.exit(1)
    print(f"Auth OK: {test[:100]}")

    # ─── SEED QUESTIONS ───────────────────────────────────────────────────────
    SEEDS = [
        ("Viral Mechanics",    f"What EXACT title structures and narrative hooks appear in r/{args.subreddit} posts with 1000+ upvotes? Give specific real examples."),
        ("Content Failure",    f"What specific patterns make r/{args.subreddit} posts fail with low scores? Give concrete bad title examples and explain WHY they fail."),
        ("Subreddit Culture",  f"What are the core VALUES and unwritten rules of r/{args.subreddit}? What does this community believe about money and life?"),
        ("Emotional Triggers", f"What primary emotions drive the most viral posts on r/{args.subreddit} — fear, relief, pride, outrage, hope? Rank by impact with examples."),
        ("Topic Landscape",    f"What are the top 15 most common topics on r/{args.subreddit} and which get the highest average engagement vs. just high volume?"),
        ("Demographics",       f"Who posts on r/{args.subreddit}? Dominant age group, life stage, income, fears, aspirations?"),
        ("Viral Formula",      f"Based on the full year of data, give me a step-by-step formula for creating a top-performing post on r/{args.subreddit}."),
        ("Community Norms",    f"What gets removed or heavily downvoted on r/{args.subreddit}? What behaviors does the mod team and community punish?"),
        ("Monthly Highlights", f"What was the biggest viral post each month over the past year on r/{args.subreddit}? Month-by-month highlights."),
        ("Success Stories",    f"What types of financial milestone or success posts go viral on r/{args.subreddit}? What format do the best ones use?"),
    ]

    print(f"\n{'='*60}\nROUND 1: SEED QUESTIONS\n{'='*60}")
    r1_answers = {}
    for cat, q in SEEDS:
        if q in already_asked:
            existing = next((x for x in all_results if x["question"] == q), None)
            if existing and not existing["answer"].startswith(("ERROR","TIMEOUT")):
                print(f"  SKIP (done): {cat}")
                r1_answers[cat] = (q, existing["answer"])
                continue
        print(f"\n[R1/{cat}] {q[:70]}...")
        ans = ask_nlm(args.notebook, q)
        item = {"round": 1, "category": cat, "question": q, "answer": ans, "parent": None}
        all_results.append(item)
        already_asked.append(q)
        save()
        print(f"  → {ans[:180].replace(chr(10),' ')}...")
        if not ans.startswith(("ERROR","TIMEOUT")):
            r1_answers[cat] = (q, ans)
        time.sleep(2)

    # ─── ROUND 2: DYNAMIC FOLLOW-UPS ─────────────────────────────────────────
    print(f"\n{'='*60}\nROUND 2: DYNAMIC FOLLOW-UPS\n{'='*60}")
    r2_answers = []
    for cat, (pq, pa) in list(r1_answers.items()):
        fqs = gen_followups(cat, pq, pa, already_asked)
        print(f"  [{cat}] Generated {len(fqs)} follow-ups")
        for fq in fqs:
            print(f"\n[R2/{cat}] {fq[:70]}...")
            ans = ask_nlm(args.notebook, fq)
            item = {"round": 2, "category": cat, "question": fq, "answer": ans, "parent": pq}
            all_results.append(item)
            already_asked.append(fq)
            save()
            print(f"  → {ans[:150].replace(chr(10),' ')}...")
            if not ans.startswith(("ERROR","TIMEOUT")):
                r2_answers.append((cat, fq, ans))
            time.sleep(2)

    # ─── ROUND 3: DEEP DIVES ─────────────────────────────────────────────────
    print(f"\n{'='*60}\nROUND 3: DEEP DIVES\n{'='*60}")
    for cat, q, a in r2_answers[:8]:
        fqs = gen_followups(cat, q, a, already_asked)
        for fq in fqs[:1]:
            print(f"\n[R3/{cat}] {fq[:70]}...")
            ans = ask_nlm(args.notebook, fq)
            item = {"round": 3, "category": cat, "question": fq, "answer": ans, "parent": q}
            all_results.append(item)
            already_asked.append(fq)
            save()
            print(f"  → {ans[:150].replace(chr(10),' ')}...")
            time.sleep(2)

    # ─── SYNTHESIS ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}\nSYNTHESIZING REPORT\n{'='*60}")
    good = [x for x in all_results if not x["answer"].startswith(("ERROR","TIMEOUT"))]
    print(f"Synthesizing {len(good)} Q&A pairs...")
    synthesis = synthesize(args.subreddit, good)
    if synthesis:
        Path(args.synthesis).write_text(synthesis)
        print(f"Synthesis saved → {args.synthesis} ({len(synthesis):,} chars)")
    else:
        print("Synthesis failed — check AI Gateway availability.")

    print(f"\nDone. Total questions: {len(all_results)}, successful: {len(good)}")


if __name__ == "__main__":
    main()
