---
name: reddit-icp-discovery
description: Discover and screen subreddits where a defined ideal customer profile discusses its problems, then prioritize communities for separate subreddit-analyst studies. Use for Reddit community selection and evidence-calibrated audience or acquisition-capacity scenarios; not for brand-mention audits, live-post monitoring, or writing posts.
---

# Reddit ICP discovery

Find where the intended customer and problem actually appear, including communities that never mention the brand. This is a cross-community screening step, not a substitute for the separate deep study of each shortlisted subreddit.

## Establish the decision

Ask for a factual brief before ranking: product or idea and its current stage; observable ICP characteristics; problem, trigger, and alternatives; serviceable geography and eligibility; desired outcome (for example signup, qualified lead, paid customer); organic versus paid scope; decision horizon; and material constraints. Mark proposed capabilities as hypotheses. If the ICP or problem is undefined, ask rather than manufacture a persona. If other facts are missing, a candidate inventory may still be useful, but mark fit and acquisition conclusions provisional where those facts matter. Use [references/brief-and-handoff.md](references/brief-and-handoff.md) for the intake and downstream handoff fields.

Reason from the necessary conditions: the community must contain relevant people or problem discussions, have current activity, and permit a credible way to participate. Community size affects potential scale, but subscriber count alone establishes none of those conditions. A successful contribution still does not prove acquisition; the conversion event and measurement path matter.

## Discover a defensible candidate set

Search the brand (if it exists), problem language, use cases, alternatives, competitor discussions, audience roles, life events, and geographically relevant terms. Use Reddit search, Reddit Pro Trends, an available read-only archive, or other accessible search sources; record the queries, sources, dates, and coverage. Existing brand-narrative findings are one input, not the universe of possible communities. Follow links and recurring cross-posts to adjacent communities. Include plausible small and large subreddits. No search method proves every relevant subreddit was found.

## Screen each community separately

Use a stated recent observation window appropriate to the user's decision horizon. Sample across time and thread types rather than only top posts. Record the sampling method and count; a convenience search sample does not establish a community-wide frequency. Record linked evidence and counterexamples for:

- **ICP/problem match:** who is visibly participating, relevant needs and intent, and how many qualifying discussions were observed with a clear denominator. Do not infer the demographics or geography of silent readers from commenters alone.
- **Scale and activity:** member count as context; current weekly visitors and weekly contributions where available; post/comment cadence and unique observed contributors as narrower proxies. Distinguish a visit, a contribution, a view, and a unique person. See [references/sizing-and-capacity.md](references/sizing-and-capacity.md).
- **Access and feasibility:** current subreddit status, rules, moderator guidance, account restrictions, permissible participation, language/geography, trust barriers, and whether the product can actually serve the audience. Date the rule check.
- **Opportunity and uncertainty:** volume of relevant new threads, existing answers/competition, seasonality, sampling gaps, source reliability, and overlap with other candidate communities.

First exclude or defer communities that are inaccessible, materially out of market, or incompatible with the intended participation. Then compare the survivors on fit, current relevant activity, attainable participation, potential scale, and evidence quality. Compare rates and volumes only over compatible windows and sampling frames; if those are missing, make the shortlist provisional instead of ranking by incomparable percentages. Show the component evidence and trade-offs; do not use one universal score or weights chosen without the user's objective. A large subreddit can win when relevant current activity is large; a small one can win when its audience and opportunities are denser. Preserve uncertain ties rather than manufacture precision.

## Size the opportunity without inventing customers

Report three separate layers: community scale, potentially reachable relevant people, and observed or modeled conversions. Member count is not a forecast of people reached or users captured in one or two months. Do not derive a claim such as “2,000–3,000 users from 10,000 members” or “100,000 from one million members” without evidence for unique ICP reach and the downstream rates. Weekly visitors are more current than membership but still do not reveal ICP share, exposure to the team's content, or conversions. Do not sum weekly visitors as unique monthly users or add subreddit audiences without overlap evidence.

When actual reach and conversion data are unavailable, mark customer capacity **not estimable yet** and prescribe a small, rule-compliant pilot. If the user supplies explicit unique-reach and conversion assumptions or measured pilot rates, show low/base/high scenarios with provenance and label them scenarios, not promises. The optional [scripts/capacity_scenarios.py](scripts/capacity_scenarios.py) calculates the arithmetic without turning member counts into reach. Read its help and the sizing reference before use.

## Deliver and hand off

Return a search/coverage log, candidate inventory (including exclusions), and a ranked or tiered shortlist with per-community evidence, size/activity measures, rule status, confidence, unknowns, and reasons for selection. Clearly identify which estimates are observed, modeled, or unavailable. Do not merge raw community archives or double-count overlapping audiences.

For each shortlisted community, supply the exact subreddit, product brief, relevant links, observation window, decision question, and unresolved issues for a **separate** subreddit-analyst run. When the user asks for the full targeting workflow, run subreddit-analyst individually for each shortlisted community; do not treat the discovery screen as its go/no-go verdict. Pass selected subreddits and problem terms to Reddit Scout only after that qualification for recent-post monitoring. Brand narrative audits remain separate baseline/follow-up work.

Respect Reddit-wide and current community rules. Do not recommend fake identities, undisclosed affiliations, spam, or rule evasion as an acquisition method.
