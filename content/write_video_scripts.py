#!/usr/bin/env python3
"""Generate three 3–5 minute audience-facing video scripts from the briefs."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from content_common import resolved_packet
from markdown_metrics import spoken_word_count
from model_provider import invoke_structured
from pipeline_common import (
    PipelineInputError,
    compact_json,
    iter_jsonl,
    load_json,
    receipt,
    repo_relative,
    require_run_dir,
    utc_now,
)


SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scripts"],
    "properties": {
        "scripts": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["piece_id", "title", "markdown"],
                "properties": {
                    "piece_id": {"type": "string", "enum": ["01", "02", "03"]},
                    "title": {"type": "string"},
                    "markdown": {"type": "string"},
                },
            },
        }
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    run_dir: pathlib.Path | None = None
    briefs: list[dict[str, Any]] = []
    try:
        run_dir = require_run_dir(args.run_dir)
        briefs = list(iter_jsonl(sys.stdin, source="stdin"))
        if len(briefs) != 3:
            raise PipelineInputError("video-script generation requires exactly three briefs")
        packet = resolved_packet(run_dir, briefs)
        project = load_json(run_dir / "config" / "project.json")
        run_meta = load_json(run_dir / "run.json")
        instructions = (run_dir / "prompts" / "write_video_scripts.md").read_text(encoding="utf-8")
        prompt = f"""Create three audience-facing video scripts from the same validated briefs used for the articles.

PROJECT\n{json.dumps(project, ensure_ascii=False, indent=2)}

AS-OF DATE\n{run_meta['as_of_date']}

STAGE INSTRUCTIONS\n{instructions}

BRIEFS AND RESOLVED SOURCES\n{json.dumps(packet, ensure_ascii=False, indent=2)}

For each piece, return production-ready Markdown for a 3–5 minute video, targeting roughly 475–700 spoken words. Keep every factual claim consistent with its brief; do not invent facts. Use concise `[VISUAL: ...]` directions that can be implemented in Google Vids or HeyGen, and label narration clearly. Place `<!-- claim:CLAIM_ID -->` immediately before the narration realizing each claim; every claim ID must appear once. Say where uncertainty remains and include the meaningful limitation. End with `## Sources` containing publisher, title, date, URL, and timestamp for media evidence. Include a short disclosure that research, drafting, and presentation used AI. Do not say human review is complete; that status is added only after genuine student approval.

The supplied inputs are complete. Do not call tools or inspect files; return the schema-conforming JSON directly.
"""
        response, meta = invoke_structured(run_dir=run_dir, stage="write-video-scripts", prompt=prompt, schema=SCHEMA)
        rows = response.get("scripts") if isinstance(response, dict) else None
        if not isinstance(rows, list) or len(rows) != 3 or sorted(row.get("piece_id") for row in rows) != ["01", "02", "03"]:
            raise PipelineInputError("model did not return exactly one script for pieces 01, 02, and 03")
        manifests: list[dict[str, Any]] = []
        warnings: list[str] = []
        for row in sorted(rows, key=lambda value: value["piece_id"]):
            piece_id = row["piece_id"]
            markdown = str(row.get("markdown") or "").strip() + "\n"
            brief = next(value for value in briefs if value["piece_id"] == piece_id)
            claim_ids = [str(claim["claim_id"]) for claim in brief["claims"]]
            missing = [claim_id for claim_id in claim_ids if f"<!-- claim:{claim_id} -->" not in markdown]
            if missing:
                raise PipelineInputError(f"video script {piece_id} is missing claim markers: {', '.join(missing)}")
            count = spoken_word_count(markdown)
            if not 425 <= count <= 750:
                warnings.append(f"video script {piece_id} has approximately {count} spoken words")
            path = run_dir / "video_scripts" / f"{piece_id}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown, encoding="utf-8")
            manifests.append({"piece_id": piece_id, "path": repo_relative(path), "claim_ids": claim_ids})
        for manifest in manifests:
            print(compact_json(manifest))
        receipt(
            run_dir,
            stage="write_video_scripts",
            status="completed",
            started_at=started_at,
            input_count=3,
            output_count=3,
            tools_or_models=[f"{meta['provider']}:{meta['model']}"],
            cost_usd=meta["cost_usd"],
            details={
                **{key: meta[key] for key in ("request_path", "response_path", "events_path", "schema_path")},
                "usage": meta["usage"],
                "length_warnings": warnings,
            },
        )
        return 0
    except (PipelineInputError, OSError) as exc:
        print(f"write_video_scripts: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="write_video_scripts",
                status="failed",
                started_at=started_at,
                input_count=len(briefs) if briefs else None,
                output_count=None,
                tools_or_models=["codex-cli"],
                errors=[str(exc)],
            )
        return 2 if not briefs else 1


if __name__ == "__main__":
    raise SystemExit(main())
