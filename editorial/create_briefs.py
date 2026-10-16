#!/usr/bin/env python3
"""Create and validate three evidence-linked editorial briefs."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from model_provider import invoke_structured
from pipeline_common import (
    REPO_ROOT,
    PipelineInputError,
    compact_json,
    iter_jsonl,
    load_json,
    read_jsonl,
    receipt,
    require_fields,
    require_run_dir,
    utc_now,
)


LOCATOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "quote", "segment_id"],
    "properties": {
        "type": {"type": "string", "enum": ["text", "segment"]},
        "quote": {"type": ["string", "null"]},
        "segment_id": {"type": ["string", "null"]},
    },
}


def sampled_segments(rows: Any, limit: int = 48) -> list[dict[str, Any]] | None:
    """Keep a deterministic cross-section of a long timestamped transcript."""
    if not isinstance(rows, list):
        return None
    valid = [row for row in rows if isinstance(row, dict)]
    if len(valid) <= limit:
        return valid
    indexes = {round(index * (len(valid) - 1) / (limit - 1)) for index in range(limit)}
    return [valid[index] for index in sorted(indexes)]

BRIEFS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["briefs"],
    "properties": {
        "briefs": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["piece_id", "title", "question", "argument", "synthesis", "limitations", "claims"],
                "properties": {
                    "piece_id": {"type": "string", "enum": ["01", "02", "03"]},
                    "title": {"type": "string"},
                    "question": {"type": "string"},
                    "argument": {"type": "string"},
                    "synthesis": {"type": "string"},
                    "limitations": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "minItems": 4,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["claim_id", "statement", "type", "evidence"],
                            "properties": {
                                "claim_id": {"type": "string"},
                                "statement": {"type": "string"},
                                "type": {"type": "string", "enum": ["reported_fact", "source_claim", "inference"]},
                                "evidence": {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["item_id", "version_id", "locator"],
                                        "properties": {
                                            "item_id": {"type": "string"},
                                            "version_id": {"type": "string"},
                                            "locator": LOCATOR_SCHEMA,
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}


def evidence_payload(item: dict[str, Any]) -> dict[str, Any]:
    text_path = REPO_ROOT / str(item["text_path"])
    text = text_path.read_text(encoding="utf-8")
    segments = None
    if item.get("segments_path"):
        segments = sampled_segments(load_json(REPO_ROOT / str(item["segments_path"])))
    return {
        "item_id": item["item_id"],
        "version_id": item["version_id"],
        "publisher_id": item["publisher_id"],
        "kind": item["kind"],
        "title": item["title"],
        "url": item["url"],
        "published_at": item["published_at"],
        "text": text[:2500] if item.get("segments_path") else text[:12000],
        "segments": segments,
    }


def validate_briefs(
    raw: Any,
    accepted_by_piece: dict[str, set[tuple[str, str]]],
    items: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) != 3:
        raise PipelineInputError("model must return exactly three briefs")
    piece_ids = [row.get("piece_id") for row in raw if isinstance(row, dict)]
    if sorted(piece_ids) != ["01", "02", "03"]:
        raise PipelineInputError("brief piece IDs must be exactly 01, 02, and 03")
    claim_ids: set[str] = set()
    for brief in raw:
        require_fields(brief, ("piece_id", "title", "question", "argument", "synthesis", "limitations", "claims"), record_name="brief")
        piece_id = brief["piece_id"]
        if not all(isinstance(brief.get(field), str) and brief[field].strip() for field in ("title", "question", "argument", "synthesis", "limitations")):
            raise PipelineInputError(f"brief {piece_id} contains an empty prose field")
        claims = brief["claims"]
        if not isinstance(claims, list) or len(claims) < 4:
            raise PipelineInputError(f"brief {piece_id} must contain at least four claims")
        publishers: set[str] = set()
        inference_publishers: set[str] = set()
        for claim in claims:
            require_fields(claim, ("claim_id", "statement", "type", "evidence"), record_name="claim")
            claim_id = str(claim["claim_id"])
            if not claim_id.startswith(f"{piece_id}-c") or claim_id in claim_ids:
                raise PipelineInputError(f"invalid or duplicate claim ID: {claim_id}")
            claim_ids.add(claim_id)
            if claim["type"] not in {"reported_fact", "source_claim", "inference"}:
                raise PipelineInputError(f"claim {claim_id} has invalid type")
            if not isinstance(claim["evidence"], list) or not claim["evidence"]:
                raise PipelineInputError(f"claim {claim_id} has no evidence")
            claim_publishers: set[str] = set()
            for reference in claim["evidence"]:
                require_fields(reference, ("item_id", "version_id", "locator"), record_name="evidence reference")
                key = (str(reference["item_id"]), str(reference["version_id"]))
                if key not in accepted_by_piece[piece_id]:
                    raise PipelineInputError(f"claim {claim_id} cites evidence not accepted for piece {piece_id}: {key}")
                item = items.get(key)
                if item is None:
                    raise PipelineInputError(f"claim {claim_id} cites unknown evidence version: {key}")
                locator = reference["locator"]
                if not isinstance(locator, dict) or locator.get("type") not in {"text", "segment"}:
                    raise PipelineInputError(f"claim {claim_id} has an invalid locator")
                if locator["type"] == "text":
                    quote = locator.get("quote")
                    if not isinstance(quote, str) or not quote.strip():
                        raise PipelineInputError(f"claim {claim_id} text locator has no exact quote")
                    text = (REPO_ROOT / str(item["text_path"])).read_text(encoding="utf-8")
                    if quote not in text:
                        raise PipelineInputError(f"claim {claim_id} quote does not resolve exactly")
                    locator["segment_id"] = None
                else:
                    segment_id = locator.get("segment_id")
                    if not isinstance(segment_id, str) or not segment_id:
                        raise PipelineInputError(f"claim {claim_id} segment locator has no segment_id")
                    segment_path = item.get("segments_path")
                    rows = load_json(REPO_ROOT / str(segment_path)) if segment_path else []
                    if not any(isinstance(row, dict) and row.get("segment_id") == segment_id for row in rows):
                        raise PipelineInputError(f"claim {claim_id} segment_id does not resolve")
                    locator["quote"] = None
                publisher = str(item["publisher_id"])
                publishers.add(publisher)
                claim_publishers.add(publisher)
            if claim["type"] == "inference":
                inference_publishers.update(claim_publishers)
        if len(publishers) < 3:
            raise PipelineInputError(f"brief {piece_id} uses only {len(publishers)} independent publisher(s)")
        if len(inference_publishers) < 2:
            raise PipelineInputError(f"brief {piece_id} lacks a multi-source inference")
    return sorted(raw, key=lambda row: row["piece_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    run_dir: pathlib.Path | None = None
    decisions: list[dict[str, Any]] = []
    try:
        run_dir = require_run_dir(args.run_dir)
        decisions = list(iter_jsonl(sys.stdin, source="stdin"))
        eligible = read_jsonl(run_dir / "eligible.jsonl")
        items = {(str(item["item_id"]), str(item["version_id"])): item for item in eligible}
        accepted_by_piece = {piece: set() for piece in ("01", "02", "03")}
        for decision in decisions:
            require_fields(decision, ("item_id", "version_id", "decision", "reason", "piece_ids"), record_name="decision")
            if decision["decision"] == "accept":
                key = (str(decision["item_id"]), str(decision["version_id"]))
                for piece in decision["piece_ids"]:
                    if piece in accepted_by_piece:
                        accepted_by_piece[piece].add(key)
        for piece, keys in accepted_by_piece.items():
            publishers = {str(items[key]["publisher_id"]) for key in keys if key in items}
            if len(publishers) < 3:
                raise PipelineInputError(f"piece {piece} has fewer than three accepted independent publishers")

        used_keys = set().union(*accepted_by_piece.values())
        evidence = [evidence_payload(items[key]) for key in sorted(used_keys) if key in items]
        project = load_json(run_dir / "config" / "project.json")
        policy = (run_dir / "config" / "editorial_policy.md").read_text(encoding="utf-8")
        instructions = (run_dir / "prompts" / "create_briefs.md").read_text(encoding="utf-8")
        prompt = f"""You are the argument-development stage in an auditable publication pipeline.

PROJECT\n{json.dumps(project, ensure_ascii=False, indent=2)}

EDITORIAL POLICY\n{policy}

STAGE INSTRUCTIONS\n{instructions}

EDITORIAL DECISIONS\n{json.dumps(decisions, ensure_ascii=False, indent=2)}

ACCEPTED EVIDENCE CONTENT\n{json.dumps(evidence, ensure_ascii=False, indent=2)}

Create exactly three connected but intellectually distinct briefs. Piece 01 answers what changed and what matters. Piece 02 tests which claims withstand scrutiny and where evidence or interpretations are in tension. Piece 03 explains implications for the audience and what to watch next. Every claim needs at least one accepted exact-version reference. For written evidence, copy a short exact quote verbatim into locator.quote and set segment_id null. For media, use an existing segment_id and set quote null. Use at least three independent publishers per piece. Each piece needs a genuine inference connecting at least two publishers, an explicit reasoning chain in synthesis, and a meaningful limitation or counterargument. Distinguish reported facts, attributed source claims, and your own inference. Use claim IDs 01-c1, 01-c2, and so on.

The supplied inputs are complete. Do not call tools or inspect files; return the schema-conforming JSON directly.
"""
        response, model_meta = invoke_structured(
            run_dir=run_dir,
            stage="create-briefs",
            prompt=prompt,
            schema=BRIEFS_SCHEMA,
        )
        briefs = validate_briefs(
            response.get("briefs") if isinstance(response, dict) else None,
            accepted_by_piece,
            items,
        )
        for brief in briefs:
            print(compact_json(brief))
        receipt(
            run_dir,
            stage="create_briefs",
            status="completed",
            started_at=started_at,
            input_count=len(decisions),
            output_count=3,
            tools_or_models=[f"{model_meta['provider']}:{model_meta['model']}"],
            cost_usd=model_meta["cost_usd"],
            details={
                **{key: model_meta[key] for key in ("request_path", "response_path", "events_path", "schema_path")},
                "usage": model_meta["usage"],
            },
        )
        return 0
    except (PipelineInputError, OSError) as exc:
        print(f"create_briefs: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="create_briefs",
                status="failed",
                started_at=started_at,
                input_count=len(decisions) if decisions else None,
                output_count=None,
                tools_or_models=["codex-cli"],
                errors=[str(exc)],
            )
        return 2 if not decisions else 1


if __name__ == "__main__":
    raise SystemExit(main())
