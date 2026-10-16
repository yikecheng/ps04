#!/usr/bin/env python3
"""Create the production handoff only after current checks and human approval."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

from pipeline_common import (
    REPO_ROOT,
    PipelineInputError,
    compact_json,
    load_json,
    read_jsonl,
    receipt,
    repo_relative,
    require_fields,
    require_run_dir,
    utc_now,
    write_json,
)


def current_assessment(run_dir: pathlib.Path) -> dict[str, Any]:
    command = ["bash", str(REPO_ROOT / "review" / "check_content.sh"), repo_relative(run_dir)]
    result = subprocess.run(command, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "assessment failed"
        raise PipelineInputError(f"current content assessment could not run: {detail}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineInputError("current content assessment returned malformed JSON") from exc
    return value


def source_notes(piece_id: str, brief: dict[str, Any], item_map: dict[tuple[str, str], dict[str, Any]]) -> str:
    lines = [f"# Piece {piece_id} Source Notes", ""]
    seen: set[tuple[str, str]] = set()
    for claim in brief.get("claims", []):
        lines.extend([f"## {claim['claim_id']}: {claim['statement']}", ""])
        for evidence in claim.get("evidence", []):
            key = (str(evidence["item_id"]), str(evidence["version_id"]))
            item = item_map[key]
            locator = evidence["locator"]
            location = ""
            if locator.get("type") == "text":
                location = f" — exact retained quote: “{locator['quote']}”"
            else:
                segments = load_json(REPO_ROOT / str(item["segments_path"]))
                row = next(value for value in segments if value.get("segment_id") == locator.get("segment_id"))
                total = int(float(row["start_seconds"]))
                location = f" — {total // 60}:{total % 60:02d}, segment `{row['segment_id']}`: “{row['text']}”"
            lines.append(
                f"- **{item['publisher_id']}**, [{item['title']}]({item['url']}) "
                f"({item['published_at']}); version `{item['version_id']}`{location}"
            )
            seen.add(key)
        lines.append("")
    lines.extend(["## Coverage", "", f"Distinct evidence items: {len(seen)}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    run_dir: pathlib.Path | None = None
    try:
        run_dir = require_run_dir(args.run_dir)
        saved_review = load_json(run_dir / "review.json")
        current = current_assessment(run_dir)
        if current.get("passed") is not True:
            raise PipelineInputError("current review has blocking errors")
        if saved_review.get("review_id") != current.get("review_id"):
            raise PipelineInputError("saved review is stale because assessed inputs changed")

        approval = load_json(run_dir / "approval.json")
        require_fields(approval, ("review_id", "decision", "reviewer", "reviewed_at", "notes"), record_name="approval")
        if approval["review_id"] != current["review_id"]:
            raise PipelineInputError("human approval does not match the current review_id")
        if approval["decision"] != "approve":
            raise PipelineInputError("human approval decision is not 'approve'")
        if not isinstance(approval["reviewer"], str) or not approval["reviewer"].strip():
            raise PipelineInputError("human approval must name the reviewer")

        briefs = read_jsonl(run_dir / "briefs.jsonl")
        articles = read_jsonl(run_dir / "articles.jsonl")
        scripts = read_jsonl(run_dir / "video_scripts.jsonl")
        eligible = read_jsonl(run_dir / "eligible.jsonl")
        item_map = {(str(item["item_id"]), str(item["version_id"])): item for item in eligible}
        package_dir = run_dir / "package"
        article_dir = package_dir / "articles"
        script_dir = package_dir / "video_scripts"
        notes_dir = package_dir / "source_notes"
        for directory in (article_dir, script_dir, notes_dir):
            directory.mkdir(parents=True, exist_ok=True)

        assets: list[dict[str, Any]] = []
        for piece_id in ("01", "02", "03"):
            article = next((row for row in articles if row.get("piece_id") == piece_id), None)
            script = next((row for row in scripts if row.get("piece_id") == piece_id), None)
            brief = next((row for row in briefs if row.get("piece_id") == piece_id), None)
            if not article or not script or not brief:
                raise PipelineInputError(f"piece {piece_id} is missing an article, script, or brief")
            article_source = REPO_ROOT / str(article["path"])
            script_source = REPO_ROOT / str(script["path"])
            article_target = article_dir / f"{piece_id}.md"
            script_target = script_dir / f"{piece_id}.md"
            notes_target = notes_dir / f"{piece_id}.md"
            shutil.copy2(article_source, article_target)
            shutil.copy2(script_source, script_target)
            notes_target.write_text(source_notes(piece_id, brief, item_map), encoding="utf-8")
            assets.append(
                {
                    "piece_id": piece_id,
                    "article": repo_relative(article_target),
                    "video_script": repo_relative(script_target),
                    "source_notes": repo_relative(notes_target),
                }
            )

        links_path = package_dir / "publication_links.json"
        if not links_path.exists():
            write_json(
                links_path,
                [
                    {"piece_id": piece_id, "substack_url": None, "youtube_url": None}
                    for piece_id in ("01", "02", "03")
                ],
            )
        else:
            links = load_json(links_path)
            if not isinstance(links, list) or {row.get("piece_id") for row in links if isinstance(row, dict)} != {"01", "02", "03"}:
                raise PipelineInputError("existing package/publication_links.json has an invalid shape")

        manual_steps = """# Remaining Manual Production and Publication Steps

1. Review the packaged article and matching video script side by side.
2. Produce each audience video in Google Vids or HeyGen, preserving the AI-use disclosure.
3. Publish each article on Substack without a paid-access requirement and link its video.
4. Upload each video to YouTube (public or unlisted), then add the article and source links to its description.
5. Verify all six links while signed out and enter them in `publication_links.json`.
6. Record and upload the separate narrated 4–6 minute technical demonstration.

Package readiness does not assert that any of these external steps has occurred.
"""
        (package_dir / "MANUAL_STEPS.md").write_text(manual_steps, encoding="utf-8")
        manifest = {
            "run_id": load_json(run_dir / "run.json")["run_id"],
            "review_id": current["review_id"],
            "approved_by": approval["reviewer"],
            "prepared_at": utc_now(),
            "assets": assets,
            "publication_links": repo_relative(links_path),
            "manual_steps": repo_relative(package_dir / "MANUAL_STEPS.md"),
        }
        write_json(package_dir / "manifest.json", manifest)
        print(compact_json(manifest))
        receipt(
            run_dir,
            stage="prepare_package",
            status="completed",
            started_at=started_at,
            input_count=6,
            output_count=len(assets) * 3 + 3,
            tools_or_models=["python-stdlib"],
            details={"review_id": current["review_id"]},
        )
        return 0
    except (PipelineInputError, OSError, json.JSONDecodeError) as exc:
        print(f"prepare_package: {exc}", file=sys.stderr)
        if run_dir:
            receipt(
                run_dir,
                stage="prepare_package",
                status="failed",
                started_at=started_at,
                input_count=None,
                output_count=None,
                tools_or_models=["python-stdlib"],
                errors=[str(exc)],
            )
        return 2 if isinstance(exc, PipelineInputError) and "RUN_DIR" in str(exc) else 1


if __name__ == "__main__":
    raise SystemExit(main())

