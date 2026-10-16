#!/usr/bin/env python3
"""Generate three source-linked 600–900 word articles from reviewed briefs."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from content_common import resolved_packet, word_count_without_sources
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
    "required": ["articles"],
    "properties": {
        "articles": {
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
            raise PipelineInputError("article generation requires exactly three briefs")
        packet = resolved_packet(run_dir, briefs)
        project = load_json(run_dir / "config" / "project.json")
        run_meta = load_json(run_dir / "run.json")
        instructions = (run_dir / "prompts" / "write_articles.md").read_text(encoding="utf-8")
        prompt = f"""Write the complete three-article series from the supplied, already validated briefs.

PROJECT\n{json.dumps(project, ensure_ascii=False, indent=2)}

AS-OF DATE\n{run_meta['as_of_date']}

STAGE INSTRUCTIONS\n{instructions}

BRIEFS AND RESOLVED SOURCES\n{json.dumps(packet, ensure_ascii=False, indent=2)}

For each piece, return publishable Markdown of 600–900 words excluding its Sources section. Do not add facts not present in the brief. Preserve distinctions among reported fact, attributed source claim, inference, and uncertainty. Address the limitation. Make the three openings and conclusions distinct while maintaining one publication voice. Place an inspectable HTML marker immediately before the prose realizing each claim, exactly `<!-- claim:CLAIM_ID -->`; every brief claim ID must appear once. Use descriptive inline Markdown links, not internal IDs, for audience-facing support. For media evidence, include a human-readable timestamp. End with `## Sources`, listing the referenced title, publisher, date, URL, and timestamp where applicable. Include a one-line as-of date near the beginning and a disclosure that AI assisted research and drafting. Do not say human review is complete; that status is added only after genuine student approval.

The supplied inputs are complete. Do not call tools or inspect files; return the schema-conforming JSON directly.
"""
        response, meta = invoke_structured(run_dir=run_dir, stage="write-articles", prompt=prompt, schema=SCHEMA)
        rows = response.get("articles") if isinstance(response, dict) else None
        if not isinstance(rows, list) or len(rows) != 3 or sorted(row.get("piece_id") for row in rows) != ["01", "02", "03"]:
            raise PipelineInputError("model did not return exactly one article for pieces 01, 02, and 03")
        manifests: list[dict[str, Any]] = []
        warnings: list[str] = []
        for row in sorted(rows, key=lambda value: value["piece_id"]):
            piece_id = row["piece_id"]
            markdown = str(row.get("markdown") or "").strip() + "\n"
            brief = next(value for value in briefs if value["piece_id"] == piece_id)
            claim_ids = [str(claim["claim_id"]) for claim in brief["claims"]]
            missing = [claim_id for claim_id in claim_ids if f"<!-- claim:{claim_id} -->" not in markdown]
            if missing:
                raise PipelineInputError(f"article {piece_id} is missing claim markers: {', '.join(missing)}")
            count = word_count_without_sources(markdown)
            if not 600 <= count <= 900:
                warnings.append(f"article {piece_id} has {count} words excluding sources")
            path = run_dir / "articles" / f"{piece_id}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(markdown, encoding="utf-8")
            manifests.append({"piece_id": piece_id, "path": repo_relative(path), "claim_ids": claim_ids})
        for manifest in manifests:
            print(compact_json(manifest))
        receipt(
            run_dir,
            stage="write_articles",
            status="completed",
            started_at=started_at,
            input_count=3,
            output_count=3,
            tools_or_models=[f"{meta['provider']}:{meta['model']}"],
            cost_usd=meta["cost_usd"],
            errors=[],
            details={
                **{key: meta[key] for key in ("request_path", "response_path", "events_path", "schema_path")},
                "usage": meta["usage"],
                "length_warnings": warnings,
            },
        )
        return 0
    except (PipelineInputError, OSError) as exc:
        print(f"write_articles: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="write_articles",
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
