#!/usr/bin/env python3
"""Calculate explicitly supplied, per-subreddit acquisition scenarios.

The calculator never derives reach from members, weekly visitors, or post views.
It does not estimate missing rates. Output is illustrative arithmetic, not a forecast.

Input JSON example:
{
  "subreddit": "example", "window_days": 60, "target_event": "new signups",
  "geography": "serviceable market", "channel": "organic",
  "members": 10000, "weekly_visitors": 2500,
  "scenarios": [{
    "name": "pilot-based",
    "unique_icp_reach": {"value": 1000, "basis": "assumed_unique", "source": "stated pilot plan"},
    "visit_rate": {"value": 0.05, "basis": "measured", "source": "tagged prior pilot"},
    "outcome_rate": {"value": 0.10, "basis": "measured", "source": "prior signup cohort"}
  }]
}
"""

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


def number(value, field, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field}: expected a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field}: invalid number") from exc
    if not result.is_finite() or result < 0 or (maximum is not None and result > maximum):
        raise ValueError(f"{field}: outside allowed range")
    return result


def metric(obj, field, bases, maximum=None):
    if not isinstance(obj, dict):
        raise ValueError(f"{field}: value, basis, and source are required")
    value = number(obj.get("value"), field, maximum)
    if obj.get("basis") not in bases:
        raise ValueError(f"{field}: basis must be one of {sorted(bases)}")
    if not isinstance(obj.get("source"), str) or not obj["source"].strip():
        raise ValueError(f"{field}: nonempty source is required")
    return value


def evaluate_case(case):
    if not isinstance(case, dict):
        raise ValueError("input must be a JSON object")
    subreddit = case.get("subreddit")
    if not isinstance(subreddit, str) or not re.fullmatch(r"[A-Za-z0-9_]{2,21}", subreddit):
        raise ValueError("subreddit must be a valid name without r/ prefix")
    days = case.get("window_days")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise ValueError("window_days must be a positive integer")
    event = case.get("target_event")
    if not isinstance(event, str) or not event.strip():
        raise ValueError("target_event must name the conversion being counted")
    geography = case.get("geography")
    if not isinstance(geography, str) or not geography.strip():
        raise ValueError("geography must state the serviceable audience")
    channel = case.get("channel")
    if channel not in ("organic", "paid"):
        raise ValueError("channel must be organic or paid; calculate them separately")

    for context_field in ("members", "weekly_visitors"):
        if context_field in case and case[context_field] is not None:
            number(case[context_field], context_field)

    scenarios = case.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise ValueError("scenarios must be a list")
    output = {
        "subreddit": subreddit,
        "window_days": days,
        "target_event": event,
        "geography": geography,
        "channel": channel,
        "members_context_only": case.get("members"),
        "weekly_visitors_context_only": case.get("weekly_visitors"),
        "status": "illustrative_scenarios" if scenarios else "not_estimable_without_reach_and_rates",
        "warning": "Member and visitor counts are never converted into unique ICP reach; scenarios are not forecasts or causal estimates.",
        "scenarios": [],
    }
    seen = set()
    for item in scenarios:
        if not isinstance(item, dict):
            raise ValueError("each scenario must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise ValueError("each scenario needs a distinct nonempty name")
        seen.add(name)
        reach = metric(item.get("unique_icp_reach"), "unique_icp_reach", {"measured_unique", "assumed_unique"})
        visit_rate = metric(item.get("visit_rate"), "visit_rate", {"measured", "assumed"}, Decimal(1))
        outcome_rate = metric(item.get("outcome_rate"), "outcome_rate", {"measured", "assumed"}, Decimal(1))
        visits = reach * visit_rate
        outcomes = visits * outcome_rate
        output["scenarios"].append({
            "name": name,
            "unique_icp_reach_input": str(reach),
            "attributable_visits_scenario": f"{visits:.2f}",
            "captured_outcomes_scenario": f"{outcomes:.2f}",
            "target_event": event,
            "provenance": {key: {"basis": item[key]["basis"], "source": item[key]["source"]}
                           for key in ("unique_icp_reach", "visit_rate", "outcome_rate")},
            "label": "illustrative_scenario_not_forecast",
        })
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="One subreddit JSON case; see module docstring")
    args = parser.parse_args()
    try:
        result = evaluate_case(json.loads(Path(args.input).read_text()))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
