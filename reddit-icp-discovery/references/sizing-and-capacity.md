# Sizing and acquisition capacity

Use this reference when comparing community size or making a 1–2 month reach/acquisition claim. Verify current Reddit metric definitions at run time. Reddit's [weekly visitors guidance](https://support.reddithelp.com/hc/en-us/articles/41037560577684-Understanding-weekly-visitors-and-contributions-on-Reddit) says subscribers often reflect a community's age more than activity. Weekly visitors represent unique visitors in the past seven days as a 28-day rolling average; weekly contributions are posts plus comments, excluding removed contributions. The visitor metric excludes bots and anonymous browsing in the native apps. [Mod Insights](https://support.reddithelp.com/hc/en-us/articles/15484468824980-Mod-Insights) separately reports pageviews and daily unique visitors for moderators. Metric availability varies by surface and access.

## Keep denominators separate

| Quantity | What it can establish | What it cannot establish |
| --- | --- | --- |
| Members/subscribers | Historical scale and possible interest | Current visitors, ICP share, post exposure, or customers |
| Weekly visitors | Current community visitation (per Reddit's definition) | Serviceable ICP, unique 30/60-day visitors, or exposure to a specific contribution |
| Weekly contributions | Discussion activity | Number of people or readers; prolific users may contribute repeatedly |
| Distinct observed authors/commenters | Visible participating accounts in the collected sample | All active users or silent readers; incomplete archives undercount |
| Post views/impressions | Exposure events for content with accessible insights | Necessarily unique ICP people or incremental customers |
| Attributable visits/signups | Measured funnel events under a stated attribution method | Causal lift without a control or credible counterfactual |

Do not calculate an “active percentage” by dividing one metric by member count as if both measured the same population and window. Do not sum weekly visitor figures into unique monthly/60-day people; repeat visitors are counted across weeks. Across subreddits, overlapping people prevent naïve addition. A member total is not even a ceiling on readers because nonmembers can see public Reddit content.

## Funnel and evidence requirements

Define the exact outcome first: site visit, signup, qualified lead, paying customer, or another event. For a stated window and one subreddit, an illustrative scenario can use:

    captured_outcomes = deduplicated_unique_ICP_reach × P(attributable_visit | reached) × P(outcome | attributable_visit)

Each probability is conditional on the preceding denominator. Label whether the unique reach and each rate are observed in the same campaign, borrowed from a comparable pilot, or explicitly hypothetical. State the source, date, geography, channel (organic or paid), and event definition. If the values are absent, the customer count is not estimable—not zero. [scripts/capacity_scenarios.py](../scripts/capacity_scenarios.py) only multiplies user-supplied inputs and refuses to infer reach from members or weekly visitors.

For pre-pilot planning, present the community's observed scale/activity and the qualifying conversation count, then specify what a pilot must measure: permitted interventions, unique exposure if available, tagged visits, outcomes, post removals, and direct/assisted attribution. If only post views are available, label them exposure events, not unique ICP reach. Avoid claiming incremental customers from a simple before/after change during a launch or news cycle.

For multiple candidate communities, report each separately. Gross totals may be shown only as sums of events with the metric named; unique reach requires deduplication or an explicit unknown-overlap caveat. Never add scenario-customer counts across subreddits as a unique-customer forecast without checking cross-channel duplication.

## Ranking implications

Size matters when coupled with relevant active demand and an allowed route to contribute. Compare both absolute opportunity (for example qualifying discussions per week) and density (qualifying discussions / sampled discussions), with sample size and coverage. Counts and percentages from different observation windows or sampling frames are not directly comparable; obtain compatible samples or mark the ranking provisional. A 10,000-member community can outrank a one-million-member one if it has much more current, relevant, accessible activity; the larger one can outrank it when its relevant active opportunity is genuinely greater. Do not choose either by a fixed size cutoff.

Prefer a transparent evidence table and a shortlist or Pareto comparison over a single “ICP score.” If a score is useful for a specified business objective, disclose inputs, weights, missing-data handling, and how the ranking changes under plausible weights. Rules or serviceability failures are gates, not points to compensate with a large audience.
