# Reddit Scout

Real-time Reddit post discovery filtered by product/criteria relevance.

## When to Use

Invoke this skill when the user wants to:
- Find recent Reddit posts relevant to a product or topic
- Discover promotion opportunities on specific subreddits
- Monitor subreddits for conversations matching specific criteria
- Get a filtered list of posts with relevance explanations

## Input Format

The user provides (in any order/format):
- **Subreddit(s)**: One or more subreddit names (without r/ prefix)
- **Timeframe**: How far back to look (1h, 2h, 6h, 12h, 24h)
- **Product/Criteria**: Description of what to filter for (product features, pain points, topics)

Examples:
```
/reddit-scout AI_Agents 2h "cloud AI platform with persistent compute"
/reddit-scout ClaudeAI,SideProject,selfhosted 6h "people struggling with deployment or wanting always-on AI agents"
/reddit-scout AI_Agents 1h happycapy
```

If the user just says "reddit scout" without arguments, ask for subreddit, timeframe, and criteria.

## Execution Steps

### Step 1: Fetch Posts

Run the fetch script:
```bash
python3 ~/.claude/skills/reddit-scout/scripts/reddit_scout.py SUBREDDIT HOURS LIMIT
```

- For multiple subreddits: comma-separate them (no spaces)
- Default limit: 50 (increase for wider timeframes)
- Script outputs JSON to stdout

### Step 2: Filter by Relevance

Take the fetched posts and filter them using the AI Gateway (Haiku for speed):

```bash
curl -s "$AI_GATEWAY_BASE_URL/api/v1/chat/completions" \
  -H "Authorization: Bearer $AI_GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-haiku-4.5",
    "messages": [{"role": "user", "content": "FILTERING_PROMPT_HERE"}]
  }'
```

The filtering prompt should be:
```
Given these Reddit posts and the following product/criteria, identify which posts are RELEVANT.

PRODUCT/CRITERIA: {user's product description}

POSTS:
{list of post titles + selftext snippets}

For each RELEVANT post (relevance score >= 7/10), return:
- title
- why_relevant (one sentence connecting the post to the product/criteria)
- relevance_score (1-10)

Skip posts that are only tangentially related. Be strict — only include posts where someone reading the comment section would genuinely benefit from hearing about this product/criteria.

Return JSON array.
```

### Step 3: Output Results

Present results as a clean table:
```
## Reddit Scout Results
**Subreddit(s):** r/AI_Agents | **Timeframe:** last 2h | **Criteria:** [brief]
**Found:** X posts total, Y relevant

| # | Post | Relevance | Link |
|---|------|-----------|------|
| 1 | Title... | One-liner why it's relevant | URL |
| 2 | ... | ... | ... |
```

## Configuration

### Primary Method: Arctic Shift API
- Endpoint: `https://arctic-shift.photon-reddit.com/api/posts/search`
- Parameters: `subreddit=X&sort=desc&limit=N&after=UNIX_TIMESTAMP`
- CRITICAL: Use `sort=desc` — `sort=new` returns HTTP 400
- Rate limit: ~1000 req/window (extremely generous)
- Freshness: 5-12 minutes for popular subreddits
- Returns: title, author, score, num_comments, selftext, permalink, flair

### Fallback Method: Reddit RSS
- Endpoint: `https://www.reddit.com/r/SUBREDDIT/new.rss?limit=100`
- User-Agent: Must mimic browser (Chrome on Mac)
- Rate limit: 2-3 requests then 429 for 30s. Safe: 1 req per 40s.
- Multi-sub trick: `r/sub1+sub2+sub3/new.rss` (one rate-limit slot)
- Missing data: no score, no num_comments
- Strip `/u/` prefix from author field

### Dead Methods (DO NOT USE)
- Reddit JSON API (`.json`): Permanent 403 from datacenter/sandbox IPs
- old.reddit.com: Same 403 block
- PullPush (api.pullpush.io): 430-day data lag, useless for real-time
- Reddit search.json: Same 403 as JSON API

### AI Gateway for Filtering
- Model: `anthropic/claude-haiku-4.5` (fast, cheap, good enough for relevance scoring)
- Upgrade to `anthropic/claude-sonnet-4.6` if user wants draft comments too
- Env vars: `$AI_GATEWAY_BASE_URL`, `$AI_GATEWAY_API_KEY`

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| Arctic Shift timeout/5xx | Service down | Auto-fallback to RSS |
| Arctic Shift 400 | Wrong sort param | Check: must be `sort=desc` |
| RSS 429 | Rate limited | Wait 35s + retry (max 3) |
| No posts returned | Quiet subreddit or wrong timeframe | Try wider timeframe or larger subreddit |
| AI Gateway 403 | Model access denied | Fall back to keyword matching |

## Full Post Content (for deep analysis, not just scanning)

`reddit_scout.py` truncates `selftext` to 500 chars by default (fast scanning). To load
FULL untruncated post content (e.g. before a marketing-fit judgment), pass `0` as the
4th arg:

```bash
python3 ~/.claude/skills/reddit-scout/scripts/reddit_scout.py SUBREDDIT HOURS LIMIT 0
```

## Marketing Fit Analysis (GO/NO-GO on commenting, not just relevance)

For a stricter judgment than relevance filtering — "should we actually comment here,
and what should it say" — use the FIT SCORE / PROMOTION RISK methodology and fan out
one sub-agent per post. See `references/marketing-fit.md` for the full prompt template,
scoring rubric, and comment-drafting rules. This is the right tool when the user is
evaluating specific posts for a comment/promotion decision, not just scanning for topics.

## References

- `references/methods.md` — Full documentation of all methods tested, what works, what fails
- `references/filtering.md` — How relevance filtering works, prompt templates
- `references/marketing-fit.md` — FIT/RISK scoring + comment drafting for GO/NO-GO promotion decisions
- `scripts/reddit_scout.py` — Production fetch script (Arctic Shift + RSS fallback, supports full-text mode)
