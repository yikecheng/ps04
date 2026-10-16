#!/usr/bin/env python3
"""Apply the snapshotted editorial policy through a structured AI decision."""

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
    receipt,
    require_fields,
    require_run_dir,
    utc_now,
)


def decision_schema(slot_ids: list[str]) -> dict[str, Any]:
    """Require one model judgment per deterministic pipeline-owned slot."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["decisions"],
        "properties": {
            "decisions": {
                "type": "array",
                "minItems": len(slot_ids),
                "maxItems": len(slot_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["decision_slot", "decision", "reason", "piece_ids"],
                    "properties": {
                        "decision_slot": {"type": "string", "enum": slot_ids},
                        "decision": {"type": "string", "enum": ["accept", "reject", "defer"]},
                        "reason": {"type": "string"},
                        "piece_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["01", "02", "03"]},
                        },
                    },
                },
            }
        },
    }


def evidence_excerpt(item: dict[str, Any], limit: int = 3500) -> str:
    path = REPO_ROOT / str(item["text_path"])
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "[retained text unavailable]"
    return text[:limit]


def validate(items: list[dict[str, Any]], decisions: Any) -> list[dict[str, Any]]:
    if not isinstance(decisions, list):
        raise PipelineInputError("model response decisions must be an array")
    slots = {f"slot-{index + 1:04d}": item for index, item in enumerate(items)}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for decision in decisions:
        if not isinstance(decision, dict):
            raise PipelineInputError("decision must be an object")
        require_fields(
            decision,
            ("decision_slot", "decision", "reason", "piece_ids"),
            record_name="decision",
        )
        slot = str(decision["decision_slot"])
        if slot not in slots or slot in seen:
            raise PipelineInputError(f"model returned an unknown or duplicate decision slot: {slot}")
        item = slots[slot]
        key = (str(item["item_id"]), str(item["version_id"]))
        if decision["decision"] not in {"accept", "reject", "defer"}:
            raise PipelineInputError(f"invalid decision value for {key}")
        piece_ids = decision["piece_ids"]
        if not isinstance(piece_ids, list) or any(piece not in {"01", "02", "03"} for piece in piece_ids):
            raise PipelineInputError(f"invalid piece_ids for {key}")
        if decision["decision"] != "accept" and piece_ids:
            raise PipelineInputError(f"rejected/deferred item {key} must have empty piece_ids")
        if decision["decision"] == "accept" and not piece_ids:
            raise PipelineInputError(f"accepted item {key} must be assigned to a piece")
        seen.add(slot)
        normalized.append(
            {
                "item_id": key[0],
                "version_id": key[1],
                "decision": decision["decision"],
                "reason": str(decision["reason"]).strip(),
                "piece_ids": sorted(set(piece_ids)),
            }
        )
    if seen != set(slots):
        missing = sorted(set(slots) - seen)
        raise PipelineInputError(f"model omitted {len(missing)} eligible decision(s)")
    order = {key: index for index, key in enumerate((str(i["item_id"]), str(i["version_id"])) for i in items)}
    return sorted(normalized, key=lambda row: order[(row["item_id"], row["version_id"])])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    run_dir: pathlib.Path | None = None
    items: list[dict[str, Any]] = []
    try:
        run_dir = require_run_dir(args.run_dir)
        items = list(iter_jsonl(sys.stdin, source="stdin"))
        if not items:
            raise PipelineInputError("eligible evidence stream is empty")
        for item in items:
            require_fields(item, ("item_id", "version_id", "publisher_id", "kind", "title", "url", "published_at", "text_path"), record_name="eligible item")
        project = load_json(run_dir / "config" / "project.json")
        policy = (run_dir / "config" / "editorial_policy.md").read_text(encoding="utf-8")
        instructions = (run_dir / "prompts" / "select_items.md").read_text(encoding="utf-8")
        slot_ids = [f"slot-{index + 1:04d}" for index in range(len(items))]
        evidence = [
            {
                "decision_slot": slot_ids[index],
                "item_id": item["item_id"],
                "version_id": item["version_id"],
                "source_id": item["source_id"],
                "publisher_id": item["publisher_id"],
                "kind": item["kind"],
                "title": item["title"],
                "url": item["url"],
                "published_at": item["published_at"],
                "excerpt": evidence_excerpt(item),
            }
            for index, item in enumerate(items)
        ]
        prompt = f"""You are the editorial selection stage in an auditable intelligence pipeline.

PROJECT\n{json.dumps(project, ensure_ascii=False, indent=2)}

EDITORIAL POLICY (binding)\n{policy}

STAGE INSTRUCTIONS\n{instructions}

ELIGIBLE EVIDENCE\n{json.dumps(evidence, ensure_ascii=False, indent=2)}

Return exactly one decision for every decision_slot. Copy only decision_slot, not item_id or version_id; the pipeline attaches those identities deterministically. All supplied items have already passed the run's mechanical date window, so do not re-filter them against today's date. Be specific about claim-level credibility, commercial incentives, novelty, audience relevance, and perspective. Aim for enough accepted evidence to support three distinct pieces with at least three independent publishers each. Preserve at least three defensible reject or defer decisions when the evidence warrants them; never reject an item merely to hit a quota. Only accepted items may have piece_ids. Piece 01 asks what changed, 02 asks which claims withstand scrutiny, and 03 asks what the developments imply and what to watch next.

The supplied project, policy, instructions, and evidence are the complete input for this stage. Do not call tools or inspect files; return the schema-conforming JSON directly.
"""
        response, model_meta = invoke_structured(
            run_dir=run_dir,
            stage="select-items",
            prompt=prompt,
            schema=decision_schema(slot_ids),
        )
        decisions = validate(items, response.get("decisions") if isinstance(response, dict) else None)
        for decision in decisions:
            print(compact_json(decision))
        receipt(
            run_dir,
            stage="select_items",
            status="completed",
            started_at=started_at,
            input_count=len(items),
            output_count=len(decisions),
            tools_or_models=[f"{model_meta['provider']}:{model_meta['model']}"],
            cost_usd=model_meta["cost_usd"],
            errors=[],
            details={
                **{key: model_meta[key] for key in ("request_path", "response_path", "events_path", "schema_path")},
                "usage": model_meta["usage"],
            },
        )
        return 0
    except (PipelineInputError, OSError) as exc:
        print(f"select_items: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="select_items",
                status="failed",
                started_at=started_at,
                input_count=len(items) if items else None,
                output_count=None,
                tools_or_models=["codex-cli"],
                errors=[str(exc)],
            )
        return 2 if isinstance(exc, PipelineInputError) and not items else 1


if __name__ == "__main__":
    raise SystemExit(main())
