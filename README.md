# Reddit Skills

**A research-first toolkit for understanding Reddit communities and building a credible, long-term presence in them.**

These skills help you move from brand listening and audience discovery to community-by-community research, timely conversation monitoring, and subreddit-aware content drafts. They are designed to keep evidence and interpretation visible, treat each subreddit as its own community, and support human-led, transparent participation.

> Reddit is not one audience. A strategy that works in one subreddit may be unwelcome or irrelevant in another. Start with evidence about the people and community—not a posting quota.

## The workflow

Use the skills as a connected research process. You can start at the step that matches your situation; a new product with no Reddit footprint can begin with ICP discovery.

```text
Brand narrative baseline ──┐
                            ├──► Study each subreddit individually
ICP community discovery ────┘                 │
                                              ▼
                                  Monitor current conversations
                                              │
                                              ▼
                                  Draft useful contributions
                                              │
                                              ▼
                                Re-audit the brand narrative
```

1. **Establish the baseline** with `reddit-brand-narrative` when a brand, product, or launch already has Reddit discussion. It identifies relevant communities and analyzes them separately before comparing themes. No mentions is a valid finding; it does not mean there is no potential audience.
2. **Find the audience** with `reddit-icp-discovery`. Search for communities where the intended customers and their problems actually appear, then screen candidates using fit, current activity, rules, and evidence-calibrated scale.
3. **Make a decision community by community** with `subreddit-analyst`. Run a separate study for each shortlisted subreddit before deciding whether and how to participate.
4. **Listen for live opportunities** with `reddit-scout` in communities you have already selected. Review the current thread and rules yourself; Scout finds conversations, not permission to promote.
5. **Prepare contributions** with `reddit-post-writer`. Treat its output as a draft. Verify factual and personal claims, disclose relevant affiliations, and adapt to the community before posting.
6. **Track change** by repeating `reddit-brand-narrative` over comparable periods. Keep narrative or sentiment changes separate from visits, signups, and attributed customers.

## Skills

| Skill | Use it to | Typical output |
| --- | --- | --- |
| [`reddit-brand-narrative`](reddit-brand-narrative/) | Audit how a brand, product, or launch is discussed across Reddit | Community-by-community narrative, sentiment, evidence, and change over time |
| [`reddit-icp-discovery`](reddit-icp-discovery/) | Find and prioritize communities where a defined customer profile and problem appear | Candidate subreddit inventory, evidence, scale context, uncertainties, and handoff for deeper analysis |
| [`subreddit-analyst`](subreddit-analyst/) | Understand one subreddit or assess its fit for a named product or idea | Individual community profile, audience needs, norms, risks, and decision recommendation |
| [`reddit-scout`](reddit-scout/) | Find recent relevant posts in subreddits you specify | Current conversation shortlist with relevance context |
| [`reddit-post-writer`](reddit-post-writer/) | Draft a post for a specified subreddit and goal | Editable subreddit-aware post drafts |
| [`reddit-daily-brief`](reddit-daily-brief/) | Run a configured daily monitoring and reporting pipeline | Daily Reddit digest and configured downstream reports |

Each skill has its own instructions and can be used independently. See its folder for scope, inputs, process, and limitations.

## Quick start

Clone the repository:

```bash
git clone https://github.com/ndpvt-web/reddit-skills.git
```

Install only the skill folders you need by copying them into your agent's skills directory:

```bash
# Claude Code
mkdir -p ~/.claude/skills
cp -R reddit-skills/reddit-icp-discovery ~/.claude/skills/

# Codex
mkdir -p ~/.codex/skills
cp -R reddit-skills/reddit-icp-discovery ~/.codex/skills/
```

Replace `reddit-icp-discovery` with another skill folder name to install a different skill. Start a fresh agent session if your environment needs one to discover newly added skills.

For example, ask your agent:

> I’m evaluating **[product or idea]** for **[customer profile]**, focused on **[market]**. Use `reddit-icp-discovery` to find candidate communities where these people discuss **[problem]**. Show evidence, current activity, size context, community rules, uncertainties, and what should be investigated next. Do not forecast customers from subscriber counts.

Then, for each promising community:

> Analyze **r/[subreddit]** on its own for **[date range]** using `subreddit-analyst`. Assess audience needs, culture, rules, activity, risks, and whether **[product or idea]** is a credible fit. Separate evidence from inference and recommendation.

## Scale is context, not a customer forecast

Community size matters because it constrains possible reach—but member count alone does not tell you how many people are active, match your customer profile, will see a contribution, or will convert. The discovery and analysis skills keep these questions separate and call out missing evidence rather than turning a large subscriber number into an acquisition promise.

For acquisition decisions, define the outcome first (for example, qualified visits, eligible signups, or paid customers), then measure the path with appropriate attribution. Treat any reach or conversion scenario as an assumption-based scenario, not a guarantee.

## Reported results

The maintainer reports that work using this framework generated **40M+ views across two months**, with one post reportedly reaching **12M+ views and 10K+ upvotes**. These are maintainer-reported figures; public post links or independent verification are not provided here. They describe a reported outcome, not a typical result or a promise that the framework will make every post trend.

## Principles for using the skills

- **Research before promotion.** Understand a community and its rules before choosing to participate.
- **Keep communities distinct.** Analyze each subreddit on its own; synthesize across them only after preserving the differences and evidence.
- **Be transparent.** Disclose relevant company, product, employment, or financial relationships. Do not invent personal experiences, identities, or customer stories.
- **Keep a human in the loop.** Research and writing outputs support decisions; they do not grant permission to post or replace a person’s review.
- **Use evidence proportionally.** Record the observation window, sources, sampling limits, and uncertainty. Search results and archives may be incomplete.
- **Measure outcomes honestly.** Sentiment, engagement, traffic, and acquisition are different measures; do not present one as proof of another.

## Scope and limitations

Reddit search, available archives, and sampled discussions may not reveal every post or comment. Findings describe the sources and period actually observed. Community rules and platform features can change, so check them directly before participating. The skills do not guarantee complete data, positive reception, reach, or conversion.

`reddit-daily-brief` is a separate configured automation workflow with external-service and local-environment requirements. Review its own `SKILL.md` before setup; it is not required to use the research skills above.

## Contributing

Improvements are welcome. Keep skills reusable across brands and industries, make inputs and assumptions explicit, distinguish evidence from inference, and document the limits of any data or automation. Avoid adding credentials, session data, or private run artifacts.
