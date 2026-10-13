# Reddit Skills

**Research Reddit communities. Find the right conversations. Draft posts that actually fit.**

Six skills for agents (Claude Code, Codex, and similar). Use them alone or as a pipeline: find where your audience hangs out → study each subreddit → watch live threads → draft posts that sound human.

> Reddit is not one audience. What works in one subreddit can flop in another. Research first. Post second.

## Skills at a glance

| Skill | What it actually does |
| --- | --- |
| [`subreddit-analyst`](subreddit-analyst/) | Pull **1–2 years** of posts from one subreddit (often **hundreds of thousands** of posts via Arctic Shift), then break down topics, norms, risks, and whether your product fits. One subreddit at a time — never mixed. |
| [`reddit-scout`](reddit-scout/) | Watch named subreddits on a short loop (**e.g. every hour**) for posts about you, your product, or topics you care about. Scores relevance and can draft reply comments — it does **not** post. |
| [`reddit-post-writer`](reddit-post-writer/) | Draft an AI post for **one** subreddit, then **stress-test it with digital-twin personas** (7 reviewers) before you see it. One subreddit = one post. Built to sound human, not like an ad. |
| [`reddit-icp-discovery`](reddit-icp-discovery/) | Find subreddits where your ideal customer and their problem already show up. Shortlist + evidence, then hand each one to `subreddit-analyst`. |
| [`reddit-brand-narrative`](reddit-brand-narrative/) | Audit how Reddit talks about your brand or product, community by community, over a fixed date range. |
| [`reddit-daily-brief`](reddit-daily-brief/) | Morning automation: harvest last-24h posts from configured subs, analyze, build a PDF brief, email it (default 7 AM HKT harvest). Needs local setup. |

Each folder has its own `SKILL.md` with inputs, steps, and limits.

## How to use these skills (in order)

1. **Audit your presence** — Use `reddit-brand-narrative` to see how Reddit already talks about your brand, product, or narrative (community by community).
2. **Find communities** — Use `reddit-icp-discovery` to find the subreddits where your customers actually live and discuss their problems.
3. **Deep dive each subreddit** — Use `subreddit-analyst` on one sub at a time. Pull ~**1–2 years** of past posts, learn how that community behaves, what they like / hate, and everything your agent needs to win that subreddit.
4. **Catch new posts fast** — Use `reddit-scout` to find relevant new posts as soon as they appear (about you, your product, or topics you care about). Typical loop: check across your target subs about **every 1 hour** so you can steer the narrative early.
5. **Write the viral post** — Use `reddit-post-writer` to draft a post that does **not** sound like AI, aimed at **one** specific subreddit. It **simulates the post with digital-twin personas before you post**.
6. **Daily pulse** — Use `reddit-daily-brief` for a morning digest of what customers are saying about your product, or what’s happening in the communities you care about.
7. **Track change** — Run `reddit-brand-narrative` again later on a comparable date range to see if the story on Reddit shifted.

Skip what you don’t need. Brand-new product with zero mentions? Start at step 2.

## Quick start

```bash
git clone https://github.com/ndpvt-web/reddit-skills.git
```

Copy only the skills you want into your agent skills folder:

```bash
# Claude Code
mkdir -p ~/.claude/skills
cp -R reddit-skills/subreddit-analyst ~/.claude/skills/

# Codex
mkdir -p ~/.codex/skills
cp -R reddit-skills/subreddit-analyst ~/.codex/skills/
```

Swap the folder name for any other skill. Start a new agent session if yours needs a restart to see new skills.

**Example prompts**

> Use `reddit-icp-discovery` for **[product]** aimed at **[customer]**. Find communities where they discuss **[problem]**. Show evidence, activity, rules, and what to study next. Do not turn member counts into customer forecasts.

> Use `subreddit-analyst` on **r/[subreddit]** for **[start date] → [end date]** (e.g. last 1–2 years). Analyze audience needs, culture, rules, and fit for **[product]**. Keep evidence separate from opinion.

> Use `reddit-scout` on **r/[subs]** with a **1h** lookback for posts about **[brand/topic]**. List relevant threads and draft replies only — do not post.

> Use `reddit-post-writer` for **r/[subreddit]**. Situation: **[…]**. Goal: **[…]**. Run the persona simulation, then give me the post plus what to change if anything fails review.

## Results

Using these skills we generated **50M+ views**.

- Highest single post: **12M+ views** and **10K+ upvotes**
- Every post was **written by AI**, aimed at **one specific subreddit**
- Always research that sub first (`subreddit-analyst`) — **never** reuse the same post across subs

This framework is built to get you the next viral post — research the sub, write for that community, simulate, then ship.

## Rules of thumb

- Research before you promote.
- Always go research-first **per subreddit** — write for that community, not “Reddit in general.”
- Treat each subreddit as its own community.
- Disclose affiliations. Do not invent personal stories.
- Human reviews before anything goes live. Skills draft and research — they do not post for you.
- Member count ≠ customers. Keep size, reach, and conversion as separate numbers.
- Say what window and sources you used. Archives are incomplete.

## Limits

Reddit search and archives miss posts. Rules change — check them on the sub before you participate. Skills do not guarantee full data, upvotes, reach, or sales.

`reddit-daily-brief` needs Mac bridge / cookies / PDF / email setup. Read its `SKILL.md` before installing. You can use the other skills without it.

## Contributing

PRs welcome. Keep skills reusable across brands, label assumptions, separate evidence from guesses, and document data limits. Do not commit credentials, cookies, tokens, or private run outputs.
