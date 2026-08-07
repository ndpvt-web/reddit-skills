# Reddit Scout — Relevance Filtering Reference

## How Filtering Works

Posts are fetched first (fast, no LLM needed), then filtered by relevance using the AI Gateway.
This two-step approach keeps costs low — only one LLM call per batch of posts.

---

## Filtering Prompt Template

```
You are a relevance scorer for Reddit posts. Given a PRODUCT/CRITERIA and a list of posts, score each post's relevance.

PRODUCT/CRITERIA:
{criteria}

POSTS:
{for each post: [index] "title" — selftext_preview (score={score}, comments={comments}, age={age}min, r/{subreddit})}

SCORING RULES:
- 9-10: Post directly asks for or complains about something the product solves
- 7-8: Post discusses a topic where the product is genuinely relevant
- 4-6: Tangentially related, mentioning would feel forced
- 1-3: Unrelated

Return ONLY posts scoring 7+ as a JSON array:
[{"index": N, "score": N, "why": "one sentence connecting post to criteria"}]

Be STRICT. A post about "AI agents" is not automatically relevant to every AI product.
The "why" must name the specific connection, not just "relates to AI".
```

---

## Model Selection for Filtering

| Scenario | Model | Why |
|----------|-------|-----|
| Standard filtering (most cases) | `anthropic/claude-haiku-4.5` | Fast (~1s), cheap, good enough for relevance scoring |
| Filtering + draft comments | `anthropic/claude-sonnet-4.6` | Better at writing natural Reddit comments |
| Large batch (100+ posts) | `anthropic/claude-haiku-4.5` | Still fast, handles long context |
| High-stakes promotion | `anthropic/claude-sonnet-4.6` | More nuanced relevance judgments |

---

## Example: HappyCapy Filtering

**Criteria:**
```
HappyCapy — a cloud Linux VM (8GB RAM, root access) with an AI agent (Claude Code) inside, accessible from browser. Key features: always-on persistent compute, built-in AI model gateway, 5000+ skill marketplace, instant public URLs, connect your Mac in 10 seconds, Publish & Remix to share environments. No local setup required.

RELEVANT if someone is struggling with:
- Deploying AI agents to production
- Keeping agents running persistently (not dying between sessions)
- Complex multi-step AI automation
- Self-hosting AI tools
- Cloud dev environments
- Generating content at scale (video, image, music)
- Connecting local machines to cloud
```

**Post scores example:**
- "How do I keep my AI agent running 24/7?" → 10 (direct need for persistent compute)
- "Claude built my app, can't deploy it" → 9 (deployment pain, HappyCapy has instant URLs)
- "Best vector database for RAG?" → 3 (tangentially AI but not what HappyCapy solves)
- "My Python script runs slow" → 1 (unrelated)

---

## Engagement Scoring (Optional Second Pass)

After relevance filtering, optionally score posts by promotion potential:

```
ENGAGEMENT FORMULA:
potential = (score + 2 * num_comments) / (age_hours + 0.5)

HIGH potential: post is 30min-3h old, has 5+ upvotes, few comments (room to be seen)
MEDIUM potential: post is <30min (too new, may not get traction) or 3-6h (still visible)
LOW potential: post is >6h old or has 50+ comments (your comment will be buried)
```

This helps prioritize WHICH relevant posts to actually comment on.

---

## Keyword Pre-filter (Fallback if AI Gateway unavailable)

If the AI Gateway returns 403 (model_access_denied) or is down, fall back to keyword matching:

```python
KEYWORDS = {
    "happycapy": [
        "deploy", "deployment", "hosting", "self-host",
        "always-on", "persistent", "24/7", "keep running",
        "cloud", "vm", "vps", "server",
        "ai agent", "automation", "workflow",
        "no-code", "without coding", "non-technical",
        "public url", "expose", "share",
        "mac", "local machine", "connect",
    ]
}

def keyword_filter(post, keywords):
    text = (post["title"] + " " + (post["selftext"] or "")).lower()
    matches = [k for k in keywords if k in text]
    return len(matches) >= 2  # require at least 2 keyword matches
```

This is a rough filter (many false positives/negatives) but works as emergency fallback.
