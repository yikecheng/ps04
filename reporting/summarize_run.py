#!/usr/bin/env python3
"""Produce an honest summary for complete or incomplete pipeline runs."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import pathlib
import sys
from typing import Any

from pipeline_common import (
    PipelineInputError,
    compact_json,
    load_json,
    read_jsonl,
    receipt,
    require_run_dir,
    utc_now,
)


def records(run_dir: pathlib.Path, name: str) -> list[dict[str, Any]] | None:
    path = run_dir / name
    if not path.is_file():
        return None
    return read_jsonl(path)


def count_value(rows: list[dict[str, Any]] | None) -> int | None:
    return None if rows is None else len(rows)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    invocation_started = utc_now()
    run_dir: pathlib.Path | None = None
    try:
        run_dir = require_run_dir(args.run_dir)
        run_meta = load_json(run_dir / "run.json")
        candidates = records(run_dir, "candidates.jsonl")
        items = records(run_dir, "items.jsonl")
        changes = records(run_dir, "changes.jsonl")
        eligible = records(run_dir, "eligible.jsonl")
        exclusions = records(run_dir, "exclusions.jsonl")
        decisions = records(run_dir, "decisions.jsonl")
        articles = records(run_dir, "articles.jsonl")
        scripts = records(run_dir, "video_scripts.jsonl")

        change_counts = Counter(row.get("change") for row in (changes or []))
        decision_counts = Counter(row.get("decision") for row in (decisions or []))
        counts = {
            "discovered": count_value(candidates),
            "extracted": count_value(items),
            "new": None if changes is None else change_counts["new"],
            "changed": None if changes is None else change_counts["changed"],
            "unchanged": None if changes is None else change_counts["unchanged"],
            "eligible": count_value(eligible),
            "excluded": count_value(exclusions),
            "accepted": None if decisions is None else decision_counts["accept"],
            "rejected": None if decisions is None else decision_counts["reject"],
            "deferred": None if decisions is None else decision_counts["defer"],
            "articles": count_value(articles),
            "video_scripts": count_value(scripts),
        }

        observations = candidates or []
        unique_observation_ids = {row.get("item_id") for row in observations if row.get("item_id") is not None}
        duplicate_observations = None if candidates is None else max(0, len(observations) - len(unique_observation_ids))
        corpus = eligible or items or []
        by_kind = Counter(str(row.get("kind")) for row in corpus)
        publishers = {str(row.get("publisher_id")) for row in corpus if row.get("publisher_id")}
        source_coverage = {
            "basis": "eligible" if eligible is not None else ("extracted" if items is not None else None),
            "distinct_underlying_items": len({row.get("item_id") for row in corpus if row.get("item_id")}) if corpus else 0,
            "by_kind": {kind: by_kind.get(kind, 0) for kind in ("feed", "youtube", "podcast")},
            "independent_publishers": len(publishers),
            "publisher_ids": sorted(publishers),
            "raw_observations": count_value(candidates),
            "duplicate_observations": duplicate_observations,
        }

        receipts: list[dict[str, Any]] = []
        for path in sorted((run_dir / "logs").glob("*.json")) if (run_dir / "logs").is_dir() else []:
            try:
                value = load_json(path)
            except PipelineInputError:
                continue
            if isinstance(value, dict) and "stage" in value:
                receipts.append(value)
        stage_outcomes = [
            {
                "stage": row.get("stage"),
                "status": row.get("status"),
                "input_count": row.get("input_count"),
                "output_count": row.get("output_count"),
                "errors": row.get("errors", []),
            }
            for row in receipts
        ]
        incomplete = [
            row for row in stage_outcomes
            if row.get("status") in {"failed", "incomplete"} or row.get("errors")
        ]
        tools_models = sorted(
            {
                str(tool)
                for row in receipts
                for tool in (row.get("tools_or_models") or [])
            }
        )
        known_costs = [float(row["cost_usd"]) for row in receipts if isinstance(row.get("cost_usd"), (int, float))]
        unknown_cost_count = sum(row.get("cost_usd") is None for row in receipts)
        costs = {
            "known_or_estimated_total_usd": round(sum(known_costs), 6),
            "known_receipt_count": len(known_costs),
            "unknown_receipt_count": unknown_cost_count,
            "contains_estimates": any(row.get("cost_estimate") is True for row in receipts),
        }
        token_usage = Counter()
        for row in receipts:
            usage = (row.get("details") or {}).get("usage") if isinstance(row.get("details"), dict) else None
            if isinstance(usage, dict):
                for key, value in usage.items():
                    if isinstance(value, (int, float)):
                        token_usage[str(key)] += int(value)
        # Immutable model event streams are authoritative. Prefer their total
        # when present so mixed old/new receipts cannot undercount or double-count.
        event_token_usage = Counter()
        if (run_dir / "logs").is_dir():
            for events_path in sorted((run_dir / "logs").glob("*.events.jsonl")):
                for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    usage = event.get("usage") if isinstance(event, dict) and event.get("type") == "turn.completed" else None
                    if isinstance(usage, dict):
                        for key, value in usage.items():
                            if isinstance(value, (int, float)):
                                event_token_usage[str(key)] += int(value)
        if event_token_usage:
            token_usage = event_token_usage

        review = load_json(run_dir / "review.json") if (run_dir / "review.json").is_file() else None
        package = load_json(run_dir / "package" / "manifest.json") if (run_dir / "package" / "manifest.json").is_file() else None
        links_path = run_dir / "package" / "publication_links.json"
        publication_links = load_json(links_path) if links_path.is_file() else None
        if package is not None:
            status = "ready_for_production"
        elif isinstance(review, dict) and review.get("passed") is True and counts["articles"] == 3 and counts["video_scripts"] == 3:
            status = "awaiting_review"
        else:
            status = "failed"

        remaining: list[str] = []
        if status == "failed":
            remaining.append("Repair failed or missing pipeline stages, then rerun the affected component checks.")
        elif status == "awaiting_review":
            remaining.extend(
                [
                    "Complete genuine human editorial review and create matching approval.json.",
                    f"Run `bash run.sh --package {run_dir.as_posix()}` after approval.",
                ]
            )
        else:
            remaining.extend(
                [
                    "Produce three audience videos in Google Vids or HeyGen.",
                    "Publish the three Substack articles and YouTube videos and record their links.",
                    "Record and publish the separate narrated technical demonstration.",
                ]
            )

        started = parse_time(run_meta.get("started_at"))
        finish_candidates = [parse_time(row.get("finished_at")) for row in receipts]
        finishes = [value for value in finish_candidates if value is not None]
        elapsed = None
        if started and finishes:
            elapsed = round((max(finishes) - started).total_seconds(), 3)

        summary = {
            "run_id": run_meta.get("run_id"),
            "status": status,
            "as_of_date": run_meta.get("as_of_date"),
            "mode": run_meta.get("mode"),
            "previous_run_id": run_meta.get("previous_run_id"),
            "counts": counts,
            "source_coverage": source_coverage,
            "failed_or_incomplete_stages": incomplete,
            "stage_outcomes": stage_outcomes,
            "elapsed_seconds": elapsed,
            "tools_and_models": tools_models,
            "costs": costs,
            "model_token_usage": dict(sorted(token_usage.items())),
            "review": None if review is None else {"review_id": review.get("review_id"), "passed": review.get("passed")},
            "production_package": None if package is None else package.get("manifest", package),
            "publication_links": publication_links,
            "remaining_manual_actions": remaining,
        }
        print(compact_json(summary))
        receipt(
            run_dir,
            stage="summarize_run",
            status="completed",
            started_at=invocation_started,
            input_count=len(receipts),
            output_count=1,
            tools_or_models=["python-stdlib"],
            details={"overall_status": status},
        )
        return 0
    except (PipelineInputError, OSError, json.JSONDecodeError) as exc:
        print(f"summarize_run: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="summarize_run",
                status="failed",
                started_at=invocation_started,
                input_count=None,
                output_count=None,
                tools_or_models=["python-stdlib"],
                errors=[str(exc)],
            )
        return 2 if isinstance(exc, PipelineInputError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
