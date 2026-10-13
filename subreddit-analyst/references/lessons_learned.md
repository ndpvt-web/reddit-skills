# Collection and analysis cautions

- Use an explicit subreddit and time window. Keep one collection directory per subreddit and window; never resume a checkpoint for a different request.
- Archive search is not guaranteed complete. HTTP failures, rate limits, timeouts, missing comments, removed posts, and search indexing gaps must be recorded. Only a verified terminal page supports a claim that pagination reached the end; even then, describe archive coverage rather than all Reddit activity.
- Validate sample records, date bounds, duplicates, and unique IDs. Report the count retrieved and the denominator for every percentage.
- Separate post volume, engagement, and sentiment. A high-score example is not evidence that most users share its view. Distinguish posts from comments, and account for moderation and survivorship bias.
- Check current rules and pinned moderator guidance before proposing participation. Rules may have changed after the historical corpus.
- NotebookLM is optional. Authenticate through its supported user flow. Do not extract browser cookies or tokens, and do not require a remote-machine bridge.
- Ask short, source-grounded questions. Long or multi-part queries may time out. Save answers incrementally and inspect citation quality; NotebookLM can hallucinate or omit source context.
- Avoid fixed topic assumptions. Questions about finance, marketing, AI, demographics, or virality belong only when the community data and user objective make them relevant.
- For product fit, obtain a real project brief. An idea's proposed features are hypotheses, not existing capabilities. Be explicit about geographic eligibility and legal or financial constraints where relevant.
- Acquisition recommendations should preserve user trust: no fake neutral persona, undisclosed affiliation, sockpuppets, spam, or rule evasion.
