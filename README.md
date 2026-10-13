# reddit-skills

A collection of Claude Code skills for Reddit research, content creation, and analysis.

## Skills

- **reddit-daily-brief** — Pulls a daily digest/brief from Reddit across tracked subreddits and topics.
- **reddit-post-writer** — Drafts Reddit posts tailored to a subreddit's tone and rules.
- **reddit-scout** — Finds recent, relevant posts in subreddits you have already selected.
- **reddit-icp-discovery** — Finds and screens communities where a defined ideal customer and problem appear, with evidence-calibrated audience sizing; hands selected communities to subreddit-analyst.
- **subreddit-analyst** — Analyzes one subreddit over a defined period; optionally evaluates fit for any startup, product, service, brand, or idea.
- **reddit-brand-narrative** — Audits how a brand or product is discussed across subreddits, studying each community separately before comparing narratives and sentiment.

## Recommended research workflow

1. Use **reddit-brand-narrative** to establish where an existing brand is discussed today. A new brand may have no mentions; that does not show where its potential customers are.
2. Use **reddit-icp-discovery** to find where the target customer discusses the problem, and shortlist communities using evidence of fit, current activity, size, rules, and uncertainty. Member counts are context—not a prediction of reach or customers.
3. Run **subreddit-analyst separately for each shortlisted subreddit** before making a participation strategy.
4. Use **reddit-scout** to find recent, relevant posts in the selected communities. Review current rules and contribute transparently; use **reddit-post-writer** for drafts only after checking every claim, personal detail, and brand affiliation for truthfulness.
5. Repeat **reddit-brand-narrative** over comparable periods to see whether discussion changed. Measure visits and acquisition separately; a change in sentiment is not proof of customer conversion.

## Usage

Each skill lives in its own directory with a `SKILL.md` describing its purpose and invocation.
Copy any skill folder into your agent's skills directory (for example, `~/.claude/skills/` for Claude Code or `~/.codex/skills/` for Codex).

## Notes

Generated run artifacts, caches, and any credential/session files have been excluded from this repo.
