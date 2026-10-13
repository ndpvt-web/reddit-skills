#!/usr/bin/env python3
"""
Dynamic multi-round NotebookLM analysis harness.

Flow:
  Round 1: Ask seed questions
  Round 2: LLM reads each answer → generates follow-up questions
  Round 3: LLM reads round-2 answers → generates deep-dive questions
  Final:   Synthesize all Q&A into a comprehensive report

Usage:
  python3 dynamic_analysis.py --notebook NOTEBOOK_ID --subreddit example \
    --results tmp/dynamic_results.json

Key lessons baked in:
  - Use the user's normal NotebookLM authentication; do not extract browser tokens
  - `notebooklm ask --notebook ID "question"` — no --new flag (doesn't exist)
  - NLM queries for complex questions take 60-180s; use 180s timeout with retries
  - Optional configured chat-completions service generates follow-up questions
  - Save results incrementally after every answer (crash-safe)
  - Round 2/3 questions are GENERATED from answers, not hardcoded
"""
import argparse, subprocess, json, time, os, sys, shutil
from pathlib import Path

NLM         = os.environ.get("NOTEBOOKLM_CLI") or shutil.which("notebooklm")
AI_URL      = os.environ.get("ANALYST_LLM_URL", "")
AI_KEY      = os.environ.get("ANALYST_LLM_API_KEY", "")
AI_MODEL    = os.environ.get("ANALYST_LLM_MODEL", "")


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
                    return f"ERROR: NotebookLM authentication required: {combined}"
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


# ─── OPTIONAL CHAT-COMPLETIONS CALL ──────────────────────────────────────────
def llm_call(prompt: str, model: str = "", max_tokens: int = 600) -> str:
    """
    Optional OpenAI-compatible service; no provider or model is assumed.
    """
    model = model or AI_MODEL
    if not (AI_URL and AI_KEY and model):
        return ""
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
            AI_URL,
            "-H", f"Authorization: Bearer {AI_KEY}",
            "-H", "Content-Type: application/json",
            "-H", "Accept-Encoding: identity",
            "-d", f"@{tmpf}",
        ], capture_output=True, text=True, timeout=60)
        data = json.loads(result.stdout)
        if "error" in data:
            code = data["error"].get("code","") if isinstance(data["error"], dict) else ""
            if code == "model_access_denied":
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
def gen_followups(subreddit: str, category: str, question: str, answer: str, already_asked: list) -> list:
    if not answer or answer.startswith(("ERROR", "TIMEOUT")):
        return []
    already_str = "\n".join(f"- {q}" for q in already_asked[-15:])
    prompt = f"""You are analyzing r/{subreddit} Reddit data.

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

    prompt = f"""You have research answers about r/{subreddit} (Reddit). The answers may be incomplete or wrong; do not present unsupported claims as facts.

{qa_text}

Write a specific evidence-calibrated community analysis. Cite source links only if present in the answers. Separate observations from inferences and recommendations. If counts lack denominators, say so. Use this structure:

# r/{subreddit} — Deep Analysis Report

## Scope and limitations
## Recurring topics and unmet needs
## Participation norms and trust signals
## Sentiment and disagreement
## Changes over time
## Representative examples and counterexamples
## Conclusions and open questions

Do not invent demographics, moderation rules, post titles, scores, or time trends. Use markdown."""

    return llm_call(prompt, max_tokens=5000)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook",  required=True)
    ap.add_argument("--subreddit", required=True)
    ap.add_argument("--results",   default="tmp/dynamic_results.json")
    ap.add_argument("--synthesis", default="tmp/synthesis.md")
    args = ap.parse_args()
    if not NLM:
        ap.error("NotebookLM CLI not found; set NOTEBOOKLM_CLI or install it on PATH")
    if not (AI_URL and AI_KEY and AI_MODEL):
        print("No optional LLM configured: only seed questions will run; use the skill workflow for manual follow-ups.")

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
    if test.startswith(("ERROR", "TIMEOUT")):
        print(f"Auth check failed: {test}")
        sys.exit(1)
    print(f"Auth OK: {test[:100]}")

    # ─── SEED QUESTIONS ───────────────────────────────────────────────────────
    SEEDS = [
        ("Coverage", f"What dates and types of r/{args.subreddit} material are in this notebook, and what important coverage limitations exist?"),
        ("Topics", f"What recurring discussion topics and questions appear in r/{args.subreddit}? Give counts with denominators if available and source examples."),
        ("Needs", f"What concrete unmet needs, frustrations, or decisions do people describe in r/{args.subreddit}? Distinguish common from memorable anecdotes."),
        ("Culture", f"What participation norms and trust signals are visible in r/{args.subreddit}? Separate observed behavior from formal rules not in the sources."),
        ("Sentiment", f"Where do r/{args.subreddit} participants agree or disagree? What positive, negative, and mixed views have evidence?"),
        ("Change", f"How did discussions in r/{args.subreddit} change across the notebook's actual date range? Identify possible collection gaps."),
        ("Counterevidence", f"What examples in r/{args.subreddit} contradict the main patterns, and what claims cannot be supported by this notebook?"),
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
        fqs = gen_followups(args.subreddit, cat, pq, pa, already_asked)
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
        fqs = gen_followups(args.subreddit, cat, q, a, already_asked)
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
        Path(args.synthesis).parent.mkdir(parents=True, exist_ok=True)
        Path(args.synthesis).write_text(synthesis)
        print(f"Synthesis saved → {args.synthesis} ({len(synthesis):,} chars)")
    else:
        print("Synthesis unavailable — configure ANALYST_LLM_URL, ANALYST_LLM_API_KEY, and ANALYST_LLM_MODEL, or synthesize manually.")

    print(f"\nDone. Total questions: {len(all_results)}, successful: {len(good)}")


if __name__ == "__main__":
    main()
