# Evidence and counting standard

## Collection ledger

Keep one ledger row per subreddit:

| Field | Meaning |
|---|---|
| `subreddit` | Exact community name, preserving capitalization for display |
| `window_start_utc`, `window_end_utc` | Fixed, half-open interval |
| `source`, `collected_at_utc` | Retrieval provenance and snapshot time |
| `status` | `complete`, `partial`, `failed`, or `indexed_only` |
| `posts_retrieved`, `pages_fetched` | Unique post count and request count |
| `oldest_utc`, `newest_utc` | Observed timestamps, not proof of coverage alone |
| `relevant_posts` | Manually verified entity matches |
| `comment_coverage` | `complete`, `sampled`, `unavailable`, or `failed` |
| `limitations` | Rate limits, removals, indexing gaps, missing comments, etc. |

Archive completion needs evidence that pagination reached the requested date boundary or a reliable source-specific end marker. A page shorter than the request limit may be an end marker only if the source guarantees it. A server error, HTTP 400/422, and a source's 100-post cap are not evidence of completion. Preserve partial output and its status.

## Matching and coding

1. Resolve entity ambiguity first. Use distinctive aliases for the first pass; inspect contextual matches before accepting short names. Save a few excluded false positives to explain disambiguation where it materially affects counts.
2. Deduplicate by native post/comment ID. Cross-posts in separate subreddits remain separate community observations; label them as the same shared source story in synthesis.
3. Assign multiple content labels if needed: first-hand experience, question/troubleshooting, technical evaluation, news repost, opinion/speculation, referral/incentive, self-promotion, removed/deleted, and uncertain. These labels need not sum to the number of relevant posts.
4. Use mutually exclusive sentiment labels only on substantive units: positive, negative, mixed, neutral/informational, or unclear. Exclude removed content without readable substance and pure referral codes from sentiment denominators. A high vote count shows engagement, not agreement with every claim.
5. A single author's repeated posts do not become independent support for a narrative. Note coordinated or repeated copy when observable, but do not allege astroturfing without account/network evidence.
6. Record a claim as “reported” or “alleged” until corroborated. A Reddit discussion about an article measures reaction to that article; it does not verify the article's technical claim.

## Per-subreddit case study

Use a compact, evidence-first structure:

1. Scope and coverage status: fixed period, post denominator, relevant posts, comment coverage, source and gaps.
2. Dominant narrative(s): concise statement, post/comment links, dates, score/comment context, and first-hand versus second-hand basis.
3. Time movement: what appeared first, what changed, and what did not; state when evidence is too thin.
4. Sentiment: coded unit and denominator, including excluded referrals and unknowns.
5. Community-specific conclusion and confidence.

For communities with a complete archive and zero relevant posts, report the zero and do not invent a narrative. For partial or indexed-only coverage, describe only the evidence actually observed.

## Cross-community conclusions

Calculate volume shares and rates with the denominator shown. For example, “11 relevant posts among 19,845 retrieved posts outside the brand community” is interpretable; “Reddit loves the launch” is not. When a brand-specific community dominates, report results with and without it. When incentives dominate, report organic discussion separately.

Do not add post counts from overlapping time windows, or compare rolling windows pulled on different days as if they were the same fixed period. Scores and comment counts are snapshots; record collection time. In a final report, put measured facts next to their interpretation and a confidence/coverage note. Prefer a small number of consequential conclusions over a long list of themes.
