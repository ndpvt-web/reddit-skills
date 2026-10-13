---
name: reddit-brand-narrative
description: Audit how a brand, product, or launch is discussed across Reddit communities over a defined period. Discover relevant subreddits, analyze each one separately, distinguish organic discussion from incentives and reposts, and report evidence-backed narrative and sentiment changes. Use for multi-community Reddit brand intelligence, not for writing or publishing Reddit posts.
---

# Reddit brand narrative audit

Produce decision-ready research about a named brand or product. Keep each subreddit as an independent case study until its collection, classification, and interpretation are complete. Cross-community synthesis comes afterward.

## Establish the study

Confirm the entity's identity from a primary source or ask if multiple entities could match. Record:

- Brand/product, official URL, launch or event being studied, and distinct aliases.
- A brand map: parent company, product names, regional subsidiaries, ticker symbols, and unrelated namesakes. Analyze those layers separately before attributing a product complaint or ticker opinion to the parent.
- Fixed start and end instants with a timezone. Use a half-open UTC interval `[start, end)` in all collection and calculations. If the user says “September 8–23,” convert that to September 8 00:00 through September 24 00:00 in the stated timezone.
- Whether the objective is launch reaction, ongoing reputation, a specific incident, competitive narrative, or another question.
- Any user-specified communities, geographies, and output format.

If the user asks for “all relevant subreddits,” discover a defensible candidate set through Reddit-wide search, named-community search, links to relevant news, and adjacent topics. Expand the set when posts reveal another active community. Define and report the searched universe; no method can prove that every Reddit post was discovered.

## Collect one subreddit at a time

Use an available read-only Reddit source, including Reddit Scout when installed. For a fixed UTC interval, [scripts/collect_arctic.py](scripts/collect_arctic.py) is a reusable Arctic Shift collector:

```bash
python3 scripts/collect_arctic.py --subreddit SUBREDDIT --after YYYY-MM-DD --before YYYY-MM-DD --outdir CASE_DIRECTORY
```

It writes `posts.json` and `ledger.json` for **one subreddit**. Use `--page-size 25` if 100-row requests time out. Omit `--query` for a full-community archive; with `--query`, the ledger explicitly says `search_only`, and its post count is not a community denominator. It continues until an empty page, rather than stopping at a short page; any API error or page cap leaves status partial. Large communities may require contiguous weekly or daily partitions. Keep those partitions separate until their windows and ledgers have been checked, then merge only that one subreddit's records by native ID. Arctic Shift is a third-party archive, not a guarantee that every Reddit item was captured. The collector needs Python `requests` and read-only network access.

For each candidate subreddit:

1. Save its own raw post archive. Paginate through the fixed interval until the date boundary or a verified end-of-data condition is reached. A per-request cap, default limit, timeout, or rate limit is not an end-of-data condition.
2. Record retrieval status, source, start/end, post count, pages fetched, oldest/newest timestamps, and gaps or errors. Mark failed or partial retrieval explicitly. A zero product-match count is valid only after a complete retrieval.
3. Match brand aliases in titles and full post bodies. Short or ambiguous aliases require contextual confirmation. Deduplicate by post ID and exclude unrelated namesakes.
   Treat the helper's output as *candidates*, not verified brand discussion. Review every short-alias hit and posts that mention the brand only incidentally, negatively, or as a comparison. Check the `alias_risk_warnings`, `matched_aliases`, and `contextual_aliases` fields. Literal context words anywhere in a post can still validate the wrong sense of an ambiguous alias.
4. Read the comments on relevant threads. Search for brand mentions in comments under broader news or comparison posts where the chosen source permits it. Record comment coverage separately: complete, sampled, unavailable, or failed. Reddit Scout's post script reports comment counts but does not fetch comment text.
5. Keep the raw archive and case-study evidence separate from every other subreddit. Shared rollups may contain derived counts and links, not a merged raw archive unless the user requests one.
6. Attribute source type before sentiment coding: official account, disclosed sponsorship, referral/reward incentive, independent customer, investor, news repost, or unknown. Do not treat a brand-operated subreddit or incentivized creator content as a representative sample of public opinion. A documented creator program is a risk indicator, not proof that any specific post was paid.

The helper [scripts/audit_posts.py](scripts/audit_posts.py) filters and counts a retrieved post archive; it does not collect posts or comments. Read [references/evidence-standard.md](references/evidence-standard.md) before deciding that a community has been exhaustively audited.

The helper requires each post to carry a `subreddit` and `created_utc` field and refuses an output path equal to its input path. It reports malformed rows, conflicting duplicates, and exact-match criteria so a run can be checked. It never establishes collection completeness; pair its output with the collector's page/date/error ledger. HTTP errors—including 422 timeouts—are not evidence of zero posts or end-of-data. If a large community cannot be fully paginated, partition the interval into contiguous smaller ranges; if it still fails, label that community partial or indexed-only.

## Interpret each community

For every subreddit with evidence, report:

- The denominator (posts retrieved in the interval), relevant posts, distinct discussion threads, and comment coverage.
- Counts of substantive discussion, referrals/incentives, promotions, news reposts, removed/deleted posts, and uncertain cases. A referral attached to a real question can have both labels; do not erase the underlying discussion.
- Ranked narratives, each supported by dated post or comment links and engagement context. Distinguish first-hand use from speculation, press amplification, and the company's own claims.
- Direction and change over time, using bins suitable to the period and activity level. A change requires dated evidence from both periods; otherwise say “insufficient evidence for a trend.”
- Sentiment toward the product, its maker, and its broader category separately when they differ. State the coding unit and denominator. Do not infer a population-wide sentiment percentage from a nonrepresentative Reddit sample.
- What the evidence supports, what it contradicts, and what remains unknown.

Use [references/evidence-standard.md](references/evidence-standard.md) for counting rules and the per-subreddit case-study structure.

## Synthesize after case studies

Compare narratives by topic such as agents, personal use, coding, privacy, marketing, commerce, finance, devices, and policy only when the discovered communities support those topics. Show which narratives are concentrated in one community and which recur independently. Separate mention volume, engagement, and sentiment; they answer different questions.

Lead the final deliverable with data and conclusions. Include a coverage table for every investigated subreddit, a time-series or phase comparison where supported, the strongest evidence links, and explicit retrieval limits. If asked for HTML, make the analysis readable and auditable before styling it. Never call a partial archive exhaustive or a missing search result proof of no discussion.
