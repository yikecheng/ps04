#!/usr/bin/env python3
"""Mechanical and traceability checks for briefs, drafts, and scripts."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

from coverage_check import assess_coverage
from markdown_metrics import spoken_word_count, word_count
from pipeline_common import (
    REPO_ROOT,
    PipelineInputError,
    compact_json,
    load_json,
    read_jsonl,
    receipt,
    require_run_dir,
    sha256_files,
    utc_now,
)


def parse_published(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).date()
    except (ValueError, OverflowError):
        return None


def prose_words(markdown: str, *, script: bool = False) -> int:
    if script:
        return spoken_word_count(markdown)
    body = markdown.split("## Sources", 1)[0]
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return word_count(body)


def issue(issues: list[dict[str, Any]], artifact: str, severity: str, explanation: str, piece_id: str | None = None) -> None:
    row: dict[str, Any] = {"artifact": artifact, "severity": severity, "explanation": explanation}
    if piece_id is not None:
        row["piece_id"] = piece_id
    issues.append(row)


def assess(run_dir: pathlib.Path) -> tuple[dict[str, Any], list[pathlib.Path]]:
    issues: list[dict[str, Any]] = []
    run_meta = load_json(run_dir / "run.json")
    try:
        as_of = date.fromisoformat(str(run_meta["as_of_date"]))
    except (KeyError, ValueError) as exc:
        raise PipelineInputError("run.json has an invalid as_of_date") from exc
    window_start = as_of - timedelta(days=29)

    required_jsonl = ("briefs.jsonl", "articles.jsonl", "video_scripts.jsonl", "eligible.jsonl")
    for name in required_jsonl:
        if not (run_dir / name).is_file():
            issue(issues, name, "error", "Required artifact is missing.")
    if any(row["severity"] == "error" for row in issues):
        fingerprint_paths = [run_dir / "run.json"]
        review_id = "review-" + sha256_files(fingerprint_paths, extra={"missing": sorted(row["artifact"] for row in issues)})[:24]
        return {"review_id": review_id, "passed": False, "issues": issues, "assessed_at": utc_now()}, fingerprint_paths

    briefs = read_jsonl(run_dir / "briefs.jsonl")
    article_manifests = read_jsonl(run_dir / "articles.jsonl")
    script_manifests = read_jsonl(run_dir / "video_scripts.jsonl")
    eligible = read_jsonl(run_dir / "eligible.jsonl")
    coverage = assess_coverage(eligible)
    for explanation in coverage["errors"]:
        issue(issues, "eligible.jsonl", "error", explanation.capitalize() + ".")
    item_map = {(str(item.get("item_id")), str(item.get("version_id"))): item for item in eligible}
    expected_ids = {"01", "02", "03"}

    for label, rows in (("briefs", briefs), ("articles", article_manifests), ("video_scripts", script_manifests)):
        ids = [str(row.get("piece_id")) for row in rows]
        if len(rows) != 3 or set(ids) != expected_ids or len(ids) != len(set(ids)):
            issue(issues, f"{label}.jsonl", "error", "Must contain exactly one record for each piece ID 01, 02, and 03.")

    article_by_piece = {str(row.get("piece_id")): row for row in article_manifests}
    script_by_piece = {str(row.get("piece_id")): row for row in script_manifests}
    referenced_paths: list[pathlib.Path] = [
        run_dir / "run.json",
        run_dir / "briefs.jsonl",
        run_dir / "articles.jsonl",
        run_dir / "video_scripts.jsonl",
    ]
    series_kinds: set[str] = set()
    all_evidence_files: set[pathlib.Path] = set()

    for brief in briefs:
        piece_id = str(brief.get("piece_id"))
        claims = brief.get("claims")
        if not isinstance(claims, list) or not claims:
            issue(issues, "briefs.jsonl", "error", "Brief has no claims.", piece_id)
            continue
        publishers: set[str] = set()
        claim_ids: list[str] = []
        inference_publishers: set[str] = set()
        for claim in claims:
            claim_id = str(claim.get("claim_id", ""))
            claim_ids.append(claim_id)
            references = claim.get("evidence")
            if not isinstance(references, list) or not references:
                issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} has no evidence.", piece_id)
                continue
            claim_publishers: set[str] = set()
            for reference in references:
                key = (str(reference.get("item_id")), str(reference.get("version_id")))
                item = item_map.get(key)
                if item is None:
                    issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} cites unknown evidence {key}.", piece_id)
                    continue
                publisher = str(item.get("publisher_id"))
                publishers.add(publisher)
                claim_publishers.add(publisher)
                series_kinds.add(str(item.get("kind")))
                published = parse_published(item.get("published_at"))
                if published is None or not window_start <= published <= as_of:
                    issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} cites evidence outside or invalid for the run window.", piece_id)
                text_path = REPO_ROOT / str(item.get("text_path", ""))
                if not text_path.is_file():
                    issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} retained text does not resolve.", piece_id)
                else:
                    all_evidence_files.add(text_path)
                locator = reference.get("locator") or {}
                if locator.get("type") == "text":
                    quote = locator.get("quote")
                    if not isinstance(quote, str) or not text_path.is_file() or quote not in text_path.read_text(encoding="utf-8"):
                        issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} exact quote does not resolve.", piece_id)
                elif locator.get("type") == "segment":
                    segment_path = REPO_ROOT / str(item.get("segments_path", ""))
                    if not segment_path.is_file():
                        issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} transcript path does not resolve.", piece_id)
                    else:
                        all_evidence_files.add(segment_path)
                        rows = load_json(segment_path)
                        if not any(isinstance(row, dict) and row.get("segment_id") == locator.get("segment_id") for row in rows):
                            issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} segment does not resolve.", piece_id)
                else:
                    issue(issues, "briefs.jsonl", "error", f"Claim {claim_id} has an invalid locator.", piece_id)
            if claim.get("type") == "inference":
                inference_publishers.update(claim_publishers)
        if len(publishers) < 3:
            issue(issues, "briefs.jsonl", "error", f"Piece uses only {len(publishers)} independent publishers; at least three are required.", piece_id)
        if len(inference_publishers) < 2:
            issue(issues, "briefs.jsonl", "error", "Piece lacks a multi-publisher inference.", piece_id)
        if not str(brief.get("limitations", "")).strip():
            issue(issues, "briefs.jsonl", "error", "Piece lacks a limitation or counterargument.", piece_id)

        for label, manifest, is_script in (
            ("article", article_by_piece.get(piece_id), False),
            ("video script", script_by_piece.get(piece_id), True),
        ):
            if not manifest:
                issue(issues, f"{label} manifest", "error", "Manifest record is missing.", piece_id)
                continue
            raw_path = manifest.get("path")
            path = REPO_ROOT / str(raw_path or "")
            try:
                path.resolve().relative_to(REPO_ROOT)
            except ValueError:
                issue(issues, f"{label} manifest", "error", "Manifest path escapes the repository.", piece_id)
                continue
            if not path.is_file():
                issue(issues, f"{label} manifest", "error", f"Referenced file does not exist: {raw_path}", piece_id)
                continue
            referenced_paths.append(path)
            markdown = path.read_text(encoding="utf-8")
            manifest_claims = manifest.get("claim_ids")
            if manifest_claims != claim_ids:
                issue(issues, f"{label} manifest", "error", "Manifest claim IDs do not exactly match the brief.", piece_id)
            marker_counts = {
                claim_id: markdown.count(f"<!-- claim:{claim_id} -->")
                for claim_id in claim_ids
            }
            missing = [claim_id for claim_id, count_value in marker_counts.items() if count_value == 0]
            if missing:
                issue(issues, str(raw_path), "error", f"Missing claim markers: {', '.join(missing)}", piece_id)
            duplicates = [claim_id for claim_id, count_value in marker_counts.items() if count_value > 1]
            if duplicates:
                issue(issues, str(raw_path), "error", f"Duplicate claim markers: {', '.join(duplicates)}", piece_id)
            count = prose_words(markdown, script=is_script)
            low, high = ((425, 750) if is_script else (600, 900))
            if not low <= count <= high:
                issue(issues, str(raw_path), "warning", f"Approximate {'spoken ' if is_script else ''}word count is {count}; target is {low}–{high}.", piece_id)
            if "## Sources" not in markdown:
                issue(issues, str(raw_path), "error", "Audience-facing source section is missing.", piece_id)

    missing_kinds = {"feed", "youtube", "podcast"} - series_kinds
    if missing_kinds:
        issue(issues, "briefs.jsonl", "error", f"Series evidence does not use required input kind(s): {', '.join(sorted(missing_kinds))}.")
    arguments = [str(brief.get("argument", "")).strip().lower() for brief in briefs]
    if len(arguments) != len(set(arguments)):
        issue(issues, "briefs.jsonl", "error", "Two or more pieces repeat the same central argument.")
    issue(
        issues,
        "human_review",
        "warning",
        "A machine check cannot establish that interpretations are sound. Review claims, uncertainty, counterarguments, and source incentives before approval.",
    )
    referenced_paths.extend(sorted(all_evidence_files, key=str))
    review_id = "review-" + sha256_files(referenced_paths, extra={"as_of_date": as_of.isoformat()})[:24]
    return {
        "review_id": review_id,
        "passed": not any(row["severity"] == "error" for row in issues),
        "issues": issues,
        "assessed_at": utc_now(),
    }, referenced_paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    run_dir: pathlib.Path | None = None
    try:
        run_dir = require_run_dir(args.run_dir)
        result, _ = assess(run_dir)
        print(compact_json(result))
        receipt(
            run_dir,
            stage="check_content",
            status="completed",
            started_at=started_at,
            input_count=3,
            output_count=1,
            tools_or_models=["python-stdlib"],
            details={
                "passed": result["passed"],
                "error_count": sum(row["severity"] == "error" for row in result["issues"]),
                "warning_count": sum(row["severity"] == "warning" for row in result["issues"]),
            },
        )
        return 0
    except (PipelineInputError, OSError, json.JSONDecodeError) as exc:
        print(f"check_content: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="check_content",
                status="failed",
                started_at=started_at,
                input_count=None,
                output_count=None,
                tools_or_models=["python-stdlib"],
                errors=[str(exc)],
            )
        return 2 if isinstance(exc, PipelineInputError) else 1


if __name__ == "__main__":
    raise SystemExit(main())
