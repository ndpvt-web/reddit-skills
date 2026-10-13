---
name: subreddit-analyst
description: Analyze one subreddit over a defined period, and optionally assess its fit for any named startup, product, service, brand, or idea. Use for community deep dives, rules and culture, audience needs, product-community fit, reputation, and ethical acquisition strategy. Not for writing or publishing Reddit posts.
---

# Subreddit Analyst

Analyze a subreddit as its own community. Keep evidence, interpretation, and recommendations distinct. A product or idea is optional; do not assume one exists.

## Scope and intake

Establish the subreddit, explicit start and end dates, audience/geography of interest, and the decision the user wants to make. Ask about missing facts that would materially change the conclusion. Do not invent product capabilities, market availability, past results, or community rules.

Choose one mode:

- Community intelligence: explain the community's topics, needs, culture, rules, sentiment, and changes over time without evaluating a product.
- Product or idea fit: additionally assess a named offering against the community. Record its stage, target users, actual capabilities versus hypotheses, market eligibility, constraints, alternatives, and the desired outcome. Use references/project-brief.md if a structured intake helps.

For multiple subreddits, run the evidence and analysis workflow separately for each. Cross-community synthesis can follow, with denominators and differences preserved. Never treat a merged corpus as if it describes each individual community.

## Evidence workflow

1. Check for an existing corpus and its provenance. Otherwise collect posts and relevant comments within the explicit window. scripts/fetch_arctic_shift.py is an optional collector; inspect its help and use explicit dates. Document query, endpoint, time bounds, pagination, retrieved counts, and any gaps. A failed page or rate limit is not proof that the archive is complete.
2. Read current subreddit rules and relevant pinned/moderator guidance from primary sources when recommending participation. Record the date checked. Do not infer rules from old posts alone.
3. Classify on-topic posts and comments. Distinguish independent discussion from brand-owned, paid, incentivized, referral, reposted, deleted, or ambiguous material. Note selection and search biases.
4. Analyze topics, questions, pain points, alternatives, credibility signals, objections, sentiment, and changes over the period. Use counts with clear denominators and examples linked to their source. A few highly voted posts are not a population estimate.
5. Run iterative questions driven by findings and contradictions. NotebookLM is optional; scripts/upload_to_notebooklm.py and scripts/dynamic_analysis.py can assist if authenticated. If unavailable, analyze the local corpus directly and say so. Do not stop solely because NotebookLM or an LLM service is unavailable.
6. Try to falsify the emerging interpretation: inspect contrary examples, quiet periods, moderation effects, duplicate conversations, and gaps in collection. Mark uncertainty rather than filling it with confident prose.

## Product or idea fit

Evaluate, with evidence, audience overlap; problem frequency and intensity; capability-to-problem match; geography, eligibility, and compliance; community permission and tone; existing alternatives; trust barriers; and a realistic conversion path. Separate verified product facts from assumptions. For an unlaunched idea, describe fit as a testable hypothesis, not demonstrated demand.

Conclude with go, conditional experiment, or no-go, and explain why. Avoid arbitrary numeric fit thresholds unless the rubric and evidence are stated. Recommend a contribution-first plan, including specific useful content or participation, measurement, decision checkpoints, and stop rules. Do not recommend fabricated identities, undisclosed affiliation, fake endorsements, spam, rule evasion, or prohibited referrals. Respect community rules and relevant advertising disclosure requirements.

## Deliverable

Provide a per-subreddit report with: scope and methodology; coverage and limitations; rules and participation constraints; evidence-backed themes and sentiment; changes over time; representative linked examples; counterevidence; and concrete conclusions. In fit mode, add the product brief, fit assessment, ethical acquisition experiments, KPIs with baselines where available, and stop criteria. Label facts, inferences, and proposals. Do not force a fixed output directory or edit project instruction files unless the user requests it.

## Supporting files

- references/lessons_learned.md: collection and analysis cautions.
- references/project-brief.md: optional structured intake for fit mode.
- scripts/fetch_arctic_shift.py: optional archive collector.
- scripts/upload_to_notebooklm.py: optional NotebookLM upload.
- scripts/dynamic_analysis.py: optional iterative NotebookLM analysis.
- scripts/build_report.py: optional HTML report builder.

Use scripts relative to this skill directory. Inspect their help and credentials requirements before use. These helpers are optional; the workflow is not dependent on one vendor or service.
