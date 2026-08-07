#!/usr/bin/env python3
"""
dynamic_analysis.py — AI-Driven Dynamic Analysis Loop for Reddit subreddits.

Architecture:
  NotebookLM (grounded answers, source-scoped) <-> AI Gateway (generates next questions)
  Round 1 -> broad surface-level question -> answer
  Round 2 -> AI reads answer, generates 3 targeted follow-ups -> ask each
  Round 3 -> AI synthesizes all answers, identifies gaps -> asks 3 deeper probes
  Final   -> AI writes HappyCapy opportunity report

Usage:
  python3 dynamic_analysis.py                          # Run all subreddits
  python3 dynamic_analysis.py --subreddit REBubble     # Single subreddit
  python3 dynamic_analysis.py --subreddit realestate
  python3 dynamic_analysis.py --subreddit realestateinvesting
"""

import argparse, json, os, re, subprocess, sys
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

NOTEBOOK_ID = "a38b86b5-d4e2-4584-8a8a-84ccc750f01e"
NLM_PROFILE = "anjali"
NLM_BIN     = os.path.expanduser("~/.local/bin/notebooklm")
AI_MODEL    = "anthropic/claude-sonnet-4.6"
AI_URL      = "https://ai-gateway.happycapy.ai/api/v1/chat/completions"
OUT_DIR     = Path(__file__).parent.parent / "outputs"

SOURCE_MAP = {
    "REBubble": [
        "27f8e0c0-c140-448c-ab91-b876b9c83291", "4e084650-4d15-4114-bc19-1ddb4caa6794",
        "400d7c9b-2c3a-4c9b-9f54-388244e39a0d", "c6aa044b-f234-4027-bccb-ab74c27d1f26",
        "00f2c2ac-dc2f-4010-b464-bd683cfde73b", "b2723b5f-6803-452a-9a85-f73a5f72da57",
        "40f59045-fbe4-4373-8c85-681d2ba8b9b4", "9ce569d1-bc4e-429f-9b53-4e884b29728f",
        "cf5c7eee-ef4a-47b5-8e5a-b7eec459f34c",
    ],
    "realestate": [
        "dc7d19e9-602c-4ad7-903a-c752fb45fc8b", "61c701dd-f0fe-47ad-b3c2-deb9228c583d",
        "a8987572-a17d-4992-b807-0a169e0dfc4f", "8e06248e-0384-4492-88be-105815c09214",
        "1fc2e369-a705-47e8-9965-8d4efbabcec6", "1137eb3b-5115-4d26-b896-b2b1ef724561",
        "b258068b-d39c-48b9-bce6-8319e96774de", "582bdc04-bb13-4e32-8500-202a1c68e800",
        "4ab66c46-14a7-4723-87e5-1699c6f13b24", "431a27cd-146d-48af-b2fb-07a2064fa953",
        "509faf21-26e9-4e38-b3a1-842828f9e50b", "895a286c-5630-4927-afe7-08d832cff6a7",
        "8ced0e46-1b8e-4d81-8778-656b3f37f06d", "d0796a01-1ee1-48c4-a795-c57c6aabd93d",
        "3b7314a7-10e6-47b2-83bc-69146ef656ce", "6aa3d40b-4869-4872-8f1b-e21cdcb7be10",
    ],
    "realestateinvesting": [
        "cbc8c624-6fda-4967-816f-4e6841e09898", "90cc5639-dd12-417c-9a8f-99810bebf2b7",
        "73ad06ab-b1f5-47f9-ab46-b3804e441a52", "f86bf638-bc55-4718-8aee-d8a988cf9e08",
        "d210012d-ac15-4a6b-8edc-150191dddc50", "9c711bb4-968b-4b0c-9f3c-32c260419cf6",
        "3d9b86ce-52fa-46d1-96da-e15f717949b2", "c86a55eb-bc2c-4844-8eba-0687e05b87fc",
        "4cdb8820-c187-49e1-9820-5685e836f3af", "8fbc2742-6368-4686-ade2-2f8abba116b9",
        "3693bc95-5e7f-44f3-9750-cc019cbb197f", "f920a603-c093-481b-be26-ff40eaf3f896",
        "752a4d0f-6af6-4a00-85a2-723170a573cd", "0c8816d9-4e86-4b7d-8595-122991090e88",
        "a62b55fe-de81-4c5b-ae66-901501ec85b3", "99d9b7f5-4088-46f7-9647-cf5a3e939b36",
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def nlm_ask(question, source_ids):
    """Ask NotebookLM scoped to specific source IDs. Returns answer string."""
    cmd = [NLM_BIN, "--profile", NLM_PROFILE, "ask",
           "--notebook", NOTEBOOK_ID, question]
    for sid in source_ids:
        cmd += ["-s", sid]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if r.returncode == 0:
            return r.stdout.strip()
        print(f"  [NLM warn] {r.stderr[:200]}")
        return ""
    except subprocess.TimeoutExpired:
        print("  [NLM warn] timed out")
        return ""
    except Exception as e:
        print(f"  [NLM error] {e}")
        return ""


def ai_call(messages, max_tokens=1500):
    """Call AI Gateway. Returns response text."""
    api_key = os.environ.get("AI_GATEWAY_API_KEY", "")
    payload = json.dumps({"model": AI_MODEL, "max_tokens": max_tokens, "messages": messages})
    cmd = ["curl", "-s", "-X", "POST",
           "-H", "Content-Type: application/json",
           "-H", f"Authorization: Bearer {api_key}",
           "-H", "HTTP-Referer: https://happycapy.ai",
           "-d", payload, AI_URL]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        data = json.loads(r.stdout)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [AI error] {e}")
        return ""


def ai_generate_followups(subreddit, prior_qa_text, round_num):
    """Generate 3 follow-up questions based on prior answers."""
    if round_num == 2:
        instruction = ("Generate 3 targeted follow-up questions that drill into "
                       "specific problems, patterns, or gaps hinted at in the findings above.")
    else:
        instruction = ("Generate 3 deep-probe questions that surface root causes, "
                       "emotional intensity of frustrations, workarounds people try, "
                       "and unmet needs that nobody is solving yet.")

    prompt = f"""You are analyzing r/{subreddit} Reddit data (Jan 2024 – Apr 2026).

Previous research findings:
{prior_qa_text}

{instruction}

Rules:
- Each question must be directly answerable from Reddit posts/comments
- Focus on specific pain points, user behaviors, or recurring patterns
- Questions must be meaningfully different from each other and from prior questions
- Ask about things that will reveal actionable product insights

Output ONLY a JSON array of 3 question strings, no other text:
["question1", "question2", "question3"]"""

    response = ai_call([{"role": "user", "content": prompt}])
    try:
        match = re.search(r'\[.*?\]', response, re.DOTALL)
        if match:
            questions = json.loads(match.group())
            return [q for q in questions if q and '?' in q][:3]
    except Exception:
        pass
    # Fallback: extract lines with question marks
    lines = [l.strip().strip('"\'').lstrip("123.-) ")
             for l in response.split('\n') if l.strip() and '?' in l]
    return lines[:3]


def ai_synthesize(subreddit, all_qa_pairs):
    """Synthesize all Q&A into HappyCapy opportunity report."""
    qa_text = ""
    for i, (q, a) in enumerate(all_qa_pairs, 1):
        qa_text += f"\n\n--- Q{i}: {q}\nA{i}: {a[:1200]}"

    prompt = f"""You are a product strategist for HappyCapy — an AI automation platform for consumers and small businesses.

Below is deep grounded research from r/{subreddit} Reddit (Jan 2024 – Apr 2026), {len(all_qa_pairs)} rounds of dynamic Q&A against actual post/comment data:
{qa_text}

Write a concise HappyCapy Opportunity Report:

## r/{subreddit} — Top Problems (Ranked by Signal Strength)
| Rank | Problem | Evidence from Data | Frequency |
|------|---------|-------------------|-----------|
Include 5–8 problems. Evidence = specific quotes or examples from the Q&A. Frequency = rare/occasional/frequent/pervasive.

## Root Causes
What underlying factors drive these problems specific to this community?

## How Users Currently Cope
Specific DIY workarounds, tools, or behaviors they use today — with examples from the data.

## HappyCapy Automation Opportunities
For the top 3 problems: describe a specific AI workflow HappyCapy could offer. Be concrete.

## Highest-Value Target User
Demographics, situation, pain level — grounded in the data.

## Reddit Post Hook
One authentic post title that resonates with this community's #1 pain point. Write it like a real Reddit post, not marketing copy."""

    return ai_call([
        {"role": "system", "content": "You are a sharp product strategist. Be specific and evidence-based. No filler."},
        {"role": "user", "content": prompt}
    ], max_tokens=3000)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_subreddit(subreddit):
    print(f"\n{'='*60}")
    print(f"  r/{subreddit}  |  {len(SOURCE_MAP[subreddit])} sources")
    print(f"{'='*60}")

    source_ids = SOURCE_MAP[subreddit]
    all_qa = []
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # Round 1: broad discovery
    print("\n[Round 1] Broad discovery...")
    q1 = (f"What are the most common problems, frustrations, and recurring pain points "
          f"that r/{subreddit} users discuss across multiple posts? Focus on themes with "
          f"high engagement (many comments/upvotes) and give specific examples with context.")
    a1 = nlm_ask(q1, source_ids)
    all_qa.append((q1, a1))
    print(f"  Answer: {len(a1)} chars")

    # Round 2: AI-generated targeted follow-ups
    print("\n[Round 2] Generating targeted follow-ups from Round 1 answer...")
    prior_r1 = f"Q: {q1}\nA: {a1[:2000]}"
    r2_questions = ai_generate_followups(subreddit, prior_r1, round_num=2)
    print(f"  Generated: {r2_questions}")

    for q in r2_questions:
        if not q:
            continue
        print(f"\n  Asking: {q[:90]}...")
        a = nlm_ask(q, source_ids)
        all_qa.append((q, a))
        print(f"  Answer: {len(a)} chars")

    # Round 3: deep probes from all prior answers
    print("\n[Round 3] Generating deep probes from all prior answers...")
    prior_all = "\n\n".join(f"Q: {q}\nA: {a[:600]}" for q, a in all_qa)
    r3_questions = ai_generate_followups(subreddit, prior_all, round_num=3)
    print(f"  Generated: {r3_questions}")

    for q in r3_questions:
        if not q:
            continue
        print(f"\n  Asking: {q[:90]}...")
        a = nlm_ask(q, source_ids)
        all_qa.append((q, a))
        print(f"  Answer: {len(a)} chars")

    # Save raw Q&A log
    qa_path = OUT_DIR / f"{subreddit}_dynamic_qa_{ts}.md"
    with open(qa_path, "w") as f:
        f.write(f"# r/{subreddit} — Dynamic Analysis Q&A\n")
        f.write(f"*{datetime.now().isoformat()} | {len(all_qa)} pairs | {len(source_ids)} sources*\n\n")
        for i, (q, a) in enumerate(all_qa, 1):
            label = "Round 1" if i == 1 else ("Round 2" if i <= 4 else "Round 3")
            f.write(f"## [{label}] Q{i}: {q}\n\n{a}\n\n---\n\n")
    print(f"\n  Q&A log saved: {qa_path.name}")

    # Final synthesis
    print("\n[Final] Synthesizing opportunity report...")
    report = ai_synthesize(subreddit, all_qa)
    if not report:
        report = "Synthesis failed — see Q&A log above."

    report_path = OUT_DIR / f"{subreddit}_dynamic_report_{ts}.md"
    with open(report_path, "w") as f:
        f.write(f"# HappyCapy Opportunity Report — r/{subreddit}\n")
        f.write(f"*{len(all_qa)} Q&A rounds | {len(source_ids)} sources | {datetime.now().strftime('%Y-%m-%d')}*\n\n")
        f.write(report)
    print(f"  Report saved: {report_path.name}")

    return {
        "subreddit": subreddit,
        "qa_pairs": len(all_qa),
        "report": str(report_path),
        "qa_log": str(qa_path),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subreddit", choices=list(SOURCE_MAP.keys()))
    args = parser.parse_args()

    targets = [args.subreddit] if args.subreddit else list(SOURCE_MAP.keys())
    results = []
    for sub in targets:
        results.append(run_subreddit(sub))

    print(f"\n{'='*60}  DONE  {'='*60}")
    for r in results:
        print(f"  r/{r['subreddit']}: {r['qa_pairs']} Q&A pairs")
        print(f"    Report: {Path(r['report']).name}")


if __name__ == "__main__":
    main()
