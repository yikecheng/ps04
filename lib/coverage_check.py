#!/usr/bin/env python3
"""Mechanical assignment-level evidence coverage gate."""

from __future__ import annotations

import argparse
from collections import Counter
import pathlib
from typing import Any

from pipeline_common import compact_json, read_jsonl


REQUIRED_TOTAL = 12
REQUIRED_PUBLISHERS = 6
REQUIRED_PER_KIND = 2
REQUIRED_KINDS = ("feed", "youtube", "podcast")


def assess_coverage(items: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = Counter(str(item.get("kind")) for item in items)
    publishers = {str(item.get("publisher_id")) for item in items if item.get("publisher_id")}
    errors: list[str] = []
    if len(items) < REQUIRED_TOTAL:
        errors.append(f"eligible corpus has {len(items)} items; at least {REQUIRED_TOTAL} are required")
    if len(publishers) < REQUIRED_PUBLISHERS:
        errors.append(
            f"eligible corpus has {len(publishers)} independent publishers; at least {REQUIRED_PUBLISHERS} are required"
        )
    for kind in REQUIRED_KINDS:
        if kinds[kind] < REQUIRED_PER_KIND:
            errors.append(f"eligible corpus has {kinds[kind]} {kind} items; at least {REQUIRED_PER_KIND} are required")
    return {
        "passed": not errors,
        "eligible_item_count": len(items),
        "independent_publisher_count": len(publishers),
        "publisher_ids": sorted(publishers),
        "kind_counts": {kind: kinds[kind] for kind in REQUIRED_KINDS},
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("eligible_jsonl")
    args = parser.parse_args()
    result = assess_coverage(read_jsonl(pathlib.Path(args.eligible_jsonl)))
    print(compact_json(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
