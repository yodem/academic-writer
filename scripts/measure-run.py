#!/usr/bin/env python3
"""Aggregate Claude Code JSONL usage for one session."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


FAMILIES = (("opus", 1.0), ("sonnet", 0.6), ("haiku", 0.2))


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def model_scale(model):
    lowered = model.lower()
    for family, scale in FAMILIES:
        if family in lowered:
            return scale
    return 1.0


def aggregate(path, since=None, until=None):
    bounds = [timestamp(since), timestamp(until)]
    messages = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = row.get("message", {})
        if row.get("type") != "assistant" or not isinstance(message, dict) or not message.get("id"):
            continue
        when = timestamp(row.get("timestamp"))
        if when is None or (bounds[0] and when < bounds[0]) or (bounds[1] and when > bounds[1]):
            continue
        usage = message.get("usage", {})
        if not isinstance(usage, dict):
            continue
        item = messages.setdefault(message["id"], {"model": message.get("model", ""), "usage": {}})
        if message.get("model"):
            item["model"] = message["model"]
        for field in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
            item["usage"][field] = max(item["usage"].get(field, 0), usage.get(field, 0) or 0)
    by_model = {}
    effective = 0.0
    total = 0
    for item in messages.values():
        model, usage = item["model"], item["usage"]
        counts = (usage.get("input_tokens", 0), usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0), usage.get("output_tokens", 0))
        subtotal = sum(counts)
        total += subtotal
        units = (counts[0] + 1.25 * counts[1] + 0.1 * counts[2] + 5 * counts[3]) * model_scale(model)
        effective += units
        entry = by_model.setdefault(model, {"total_tokens": 0, "effective_units": 0.0})
        entry["total_tokens"] += subtotal
        entry["effective_units"] += units
    return {"total_tokens": total, "effective_units": effective, "agents": len(messages), "by_model": by_model}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = aggregate(args.session, args.since, args.until)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
