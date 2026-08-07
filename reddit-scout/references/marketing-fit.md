# Reddit Scout — Marketing Fit Analysis (Comment/Promotion Decision)

This extends basic relevance filtering (`filtering.md`) with the deeper judgment needed
before actually posting a comment: is this post safe and worthwhile to comment on, and
what should the comment say. Sourced from the `reddit-happycapy-promotion` workflow
(2026-07-23, workspace `1c1652df-9a12-4d96-9736-632fd043e5d3`).

## When to Use This vs. Plain Filtering

- **Plain filtering** (`filtering.md`): quick relevance score, good for a scan/report.
- **Marketing fit analysis** (this doc): use when the user wants an actual GO/NO-GO decision
  on commenting, or a drafted comment, not just "is this relevant".

## Two-Stage Judgment

### Stage 1 — FIT + RISK scoring (one agent call per post, or batched)

For each post, score:

1. **FIT SCORE (1-10)** — How directly does the product solve this person's SPECIFIC
   stated problem (not just topic overlap). 10 = perfect fit, 1 = tangential.
2. **PROMOTION RISK (low/medium/high)** — How spammy would a product mention look in
   this specific thread's context and tone?
3. **KEEP/DROP** — Keep only if `fitScore >= 7 AND promotionRisk in [low, medium]`.

Signals that push risk to HIGH (drop regardless of fit):
- Post is already well-answered / problem solved in top comments
- Subreddit has visible anti-self-promotion rules or mod warnings in sidebar
- Post is a rant/vent with no actual question — commenting reads as opportunistic
- Many top comments already mention competing tools — thread is "promo-saturated"

### Stage 2 — Comment drafting (only for posts that passed Stage 1)

Draft a comment that:
1. Leads with empathy or shared experience ("I ran into this too")
2. Gives a concrete, useful answer to the actual problem — not a redirect
3. Mentions the product naturally, as "what I ended up using" — never as a pitch
4. Matches Reddit's casual tone: no marketing language, no superlatives ("game-changer")
5. Passes the **upvote test**: the comment should be upvote-worthy even with the product
   mention deleted. If it wouldn't be, rewrite until it is.

## Product Context Template (fill in per product)

```
{PRODUCT} is {one-sentence what it is}. Key features: {feature list}.
It solves: {list of pain points it addresses}.
```

Example used for happycapy:
```
happycapy is a cloud Linux VM (8GB RAM, 4 vCPU, root access) with an AI agent
(Claude Code) inside it, accessible from browser. Key features: always-on 24/7
persistent state, built-in AI model gateway (all major LLMs + image/video/audio
models), 5000+ skill marketplace (ClawHub), instant public URLs for any server,
connect your Mac in 10 seconds via one terminal command, Publish & Remix to share
entire working environments. No local setup required. It's a full computer + AI
agent — not a chat interface.
```

## Multi-Agent Fan-Out Pattern

For N posts, spawn one sub-agent per post (via the Agent tool or `parallel()` in a
Workflow script) with this prompt shape:

```
You are a marketing strategist evaluating a Reddit post for organic product promotion.

PRODUCT CONTEXT: {product context}

POST:
- Title: {title}
- Subreddit: r/{subreddit}
- Full text: {full selftext, untruncated}
- Score/comments: {score} / {num_comments}
- Age: {age_minutes} min

Evaluate:
1. FIT SCORE (1-10)
2. PROMOTION RISK (low/medium/high)
3. KEEP/DROP verdict
4. If KEEP: draft a 3-5 sentence comment per the "Comment drafting" rules above
5. One-line rationale

Return structured JSON: {fitScore, promotionRisk, verdict, draftComment, rationale}
```

Batch results, keep only `verdict == "KEEP"`, sort by `fitScore` descending.

## Engagement Timing (secondary prioritization)

Even among KEEP posts, prioritize by comment visibility:

```
potential = (score + 2 * num_comments) / (age_hours + 0.5)
```

- **HIGH**: 30min–3h old, 5+ upvotes, few comments (room to be seen)
- **MEDIUM**: <30min (too new, unproven) or 3–6h (still visible)
- **LOW**: >6h old or 50+ comments (comment will be buried)

## Guardrails

- Never fabricate a personal anecdote framed as fact — keep drafts honest ("one option
  that worked for me" is fine; specific fake personal history is not).
- This skill only DRAFTS comments — it does not post them. Actually posting to Reddit
  requires explicit user approval and a real, logged-in Reddit account/session.
- Re-check promotion risk qualitatively even after automated KEEP — a human should review
  drafts before anything goes live given subreddit self-promo rules vary widely.
