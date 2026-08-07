#!/usr/bin/env python3
"""
Reddit Scout — Relevance Filter
Takes fetched posts (JSON from stdin or file) + criteria, returns relevant ones.

Usage:
    python3 reddit_scout.py AI_Agents 2 | python3 filter_posts.py "product description"
    python3 filter_posts.py "criteria" < posts.json
    python3 filter_posts.py "criteria" posts.json
"""

import json
import subprocess
import sys
import os


def filter_by_relevance(posts, criteria, model="anthropic/claude-haiku-4.5"):
    posts_summary = "\n".join([
        f'[{i}] "{p["title"]}" — {(p.get("selftext") or "")[:100]} '
        f'(score={p.get("score", "?")}, comments={p.get("num_comments", "?")}, age={p["age_minutes"]}min)'
        for i, p in enumerate(posts)
    ])

    prompt = f"""Score these Reddit posts for relevance to the product/criteria. Return ONLY posts scoring 7+.

PRODUCT/CRITERIA: {criteria}

POSTS:
{posts_summary}

SCORING:
- 9-10: Post directly asks for or complains about something the product solves
- 7-8: Post discusses a topic where the product is genuinely relevant
- Below 7: Skip (tangential or unrelated)

Return ONLY a JSON array (no markdown, no explanation):
[{{"index": N, "score": N, "why": "one sentence connecting post to product"}}]

Be STRICT. Only include genuinely relevant posts."""

    gateway_url = os.environ.get("AI_GATEWAY_BASE_URL", "")
    gateway_key = os.environ.get("AI_GATEWAY_API_KEY", "")

    if not gateway_url or not gateway_key:
        sys.stderr.write("[ERROR] AI_GATEWAY_BASE_URL or AI_GATEWAY_API_KEY not set\n")
        return keyword_fallback(posts, criteria)

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    })

    result = subprocess.run(
        ["curl", "-s",
         f"{gateway_url}/api/v1/chat/completions",
         "-H", f"Authorization: Bearer {gateway_key}",
         "-H", "Content-Type: application/json",
         "-d", payload],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        sys.stderr.write(f"[ERROR] curl failed: {result.stderr}\n")
        return keyword_fallback(posts, criteria)

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"[ERROR] Invalid JSON from gateway: {result.stdout[:200]}\n")
        return keyword_fallback(posts, criteria)

    if "error" in response:
        sys.stderr.write(f"[ERROR] Gateway error: {response['error']}\n")
        return keyword_fallback(posts, criteria)

    content = response["choices"][0]["message"]["content"]

    if "```" in content:
        content = content.split("```")[1].strip()
        if content.startswith("json"):
            content = content[4:].strip()

    try:
        relevant = json.loads(content)
    except json.JSONDecodeError:
        sys.stderr.write(f"[ERROR] Could not parse LLM response as JSON\n")
        return keyword_fallback(posts, criteria)

    results = []
    for r in relevant:
        idx = r.get("index", -1)
        if 0 <= idx < len(posts):
            post = posts[idx].copy()
            post["relevance_score"] = r.get("score", 7)
            post["why_relevant"] = r.get("why", "")
            results.append(post)

    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return results


def keyword_fallback(posts, criteria):
    """Emergency fallback if AI Gateway is unavailable."""
    sys.stderr.write("[FALLBACK] Using keyword matching (less accurate)\n")
    keywords = [w.lower().strip() for w in criteria.split() if len(w) > 3]
    results = []
    for p in posts:
        text = (p["title"] + " " + (p.get("selftext") or "")).lower()
        matches = sum(1 for k in keywords if k in text)
        if matches >= 3:
            post = p.copy()
            post["relevance_score"] = min(10, 5 + matches)
            post["why_relevant"] = f"Keyword match ({matches} terms)"
            results.append(post)
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: filter_posts.py <criteria> [posts.json]", file=sys.stderr)
        print('  echo posts | python3 filter_posts.py "cloud AI platform"', file=sys.stderr)
        sys.exit(1)

    criteria = sys.argv[1]

    if len(sys.argv) > 2:
        posts = json.load(open(sys.argv[2]))
    else:
        posts = json.load(sys.stdin)

    results = filter_by_relevance(posts, criteria)

    json.dump(results, sys.stdout, indent=2)
