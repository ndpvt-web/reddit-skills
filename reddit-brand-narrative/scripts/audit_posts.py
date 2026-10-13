#!/usr/bin/env python3
"""Filter one Reddit post archive for a brand in a fixed UTC interval.

Accepts Reddit Scout arrays or an Arctic Shift wrapper with a `posts` list.
Produces one per-subreddit JSON audit. This is a post filter, not a collector.
"""

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Date-time must include a timezone or Z suffix")
    return parsed.astimezone(timezone.utc).timestamp()


def load_posts(path):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("posts", "data"):
            if isinstance(obj.get(key), list):
                return obj[key]
    raise ValueError("Expected a JSON post array or an object with a 'posts' or 'data' array")


def text_of(post):
    return "\n".join(str(post.get(key) or "") for key in ("title", "selftext"))


def url_of(post):
    url = post.get("url")
    if url and "reddit.com" in url:
        return url
    permalink = post.get("permalink")
    return "https://www.reddit.com" + permalink if permalink else url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="One subreddit's JSON post archive")
    parser.add_argument("--output", required=True, help="One subreddit's JSON audit output")
    parser.add_argument("--subreddit", required=True)
    parser.add_argument("--start", required=True, help="Inclusive ISO-8601 instant with timezone")
    parser.add_argument("--end", required=True, help="Exclusive ISO-8601 instant with timezone")
    parser.add_argument("--alias", action="append", default=[], help="Distinctive literal brand/product alias; repeatable")
    parser.add_argument("--ambiguous-alias", action="append", default=[], help="Short alias accepted only with context; repeatable")
    parser.add_argument("--context", action="append", default=[], help="Literal context for ambiguous aliases; repeatable")
    parser.add_argument("--incentive-pattern", action="append", default=[], help="Regex for this brand's referral/incentive program; repeatable")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    if input_path == output_path:
        parser.error("--output must not overwrite --input (the raw archive)")

    start, end = instant(args.start), instant(args.end)
    if start >= end:
        parser.error("--start must precede --end")
    alias_labels = [a.strip() for a in args.alias if a.strip()]
    ambiguous_labels = [a.strip() for a in args.ambiguous_alias if a.strip()]
    aliases = [re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.I) for a in alias_labels]
    ambiguous = [re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.I) for a in ambiguous_labels]
    contexts = [re.compile(re.escape(c.strip()), re.I) for c in args.context if c.strip()]
    incentives = [re.compile(pattern, re.I) for pattern in args.incentive_pattern]
    if not aliases and not ambiguous:
        parser.error("At least one nonempty --alias or --ambiguous-alias is required")
    if ambiguous and not contexts:
        parser.error("--ambiguous-alias requires at least one --context")

    raw = load_posts(args.input)
    unique = {}
    skipped = []
    duplicate_identical = 0
    for row, post in enumerate(raw):
        if not isinstance(post, dict) or "created_utc" not in post:
            skipped.append({"row": row, "reason": "missing created_utc or not an object"})
            continue
        try:
            ts = float(post["created_utc"])
        except (TypeError, ValueError):
            skipped.append({"row": row, "reason": "invalid created_utc"})
            continue
        if not start <= ts < end:
            continue
        native_sub = str(post.get("subreddit") or "")
        if not native_sub:
            raise ValueError(f"Record {row} is missing subreddit; cannot verify single-community archive")
        if native_sub.casefold() != args.subreddit.casefold():
            raise ValueError(f"Input contains r/{native_sub}; expected only r/{args.subreddit}")
        key = str(post.get("id") or post.get("permalink") or post.get("url") or "")
        if not key:
            raise ValueError("Post is missing id, permalink, and url; cannot deduplicate")
        if key in unique:
            if unique[key] != post:
                raise ValueError(f"Conflicting duplicate post {key}; inspect archive before auditing")
            duplicate_identical += 1
            continue
        unique[key] = post

    matches = []
    for key, post in unique.items():
        body = text_of(post)
        exact_matches = [label for label, pattern in zip(alias_labels, aliases) if pattern.search(body)]
        ambiguous_matches = [label for label, pattern in zip(ambiguous_labels, ambiguous)
                             if pattern.search(body)]
        contextual_hit = bool(ambiguous_matches) and any(pattern.search(body) for pattern in contexts)
        exact_hit = bool(exact_matches)
        if not (exact_hit or contextual_hit):
            continue
        removed_markers = ("[removed]", "[deleted]", "[ removed by moderator ]")
        removed = (post.get("selftext") or "").strip().lower() in removed_markers or \
            (post.get("title") or "").strip().lower() in removed_markers or \
            bool(post.get("removed_by_category"))
        labels = []
        if removed:
            labels.append("removed_or_deleted")
        if not removed:
            labels.append("substantive_candidate")
        if any(pattern.search(body) for pattern in incentives):
            labels.append("incentive_candidate")
        matches.append({
            "id": key,
            "created_utc": float(post["created_utc"]),
            "title": post.get("title"),
            "url": url_of(post),
            "score": post.get("score"),
            "num_comments": post.get("num_comments"),
            "labels": labels,
            "matched_aliases": exact_matches,
            "contextual_aliases": ambiguous_matches if contextual_hit else [],
            "selftext": post.get("selftext"),
        })
    matches.sort(key=lambda post: (post["created_utc"], post["id"]))
    counts = {label: sum(label in post["labels"] for post in matches) for label in
              ("substantive_candidate", "incentive_candidate", "removed_or_deleted")}
    result = {
        "subreddit": args.subreddit,
        "window_start_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "window_end_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        "input": str(Path(args.input).resolve()),
        "criteria": {"aliases": args.alias, "ambiguous_aliases": args.ambiguous_alias,
                     "contexts": args.context, "incentive_patterns": args.incentive_pattern},
        "alias_risk_warnings": [f"Review short exact alias: {alias}" for alias in args.alias
                                if len(alias.strip()) <= 4],
        "input_records": len(raw),
        "skipped_records": skipped,
        "identical_duplicates": duplicate_identical,
        "posts_in_window": len(unique),
        "candidate_matches": len(matches),
        "candidate_label_counts": counts,
        "coverage_status": "unverified; inspect collector pagination and date boundaries",
        "comment_coverage": "not_collected_by_this_script",
        "classification_status": "candidates only; manually review relevance, origin, and sentiment",
        "matches": matches,
    }
    output = output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                     prefix=f".{output.name}.", delete=False) as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, output)
    print(json.dumps({key: result[key] for key in ("subreddit", "posts_in_window", "candidate_matches", "candidate_label_counts", "coverage_status")}))


if __name__ == "__main__":
    main()
