#!/usr/bin/env python3
"""Create validated, immutable run snapshots for run.sh."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import uuid
from datetime import datetime, timezone

from pipeline_common import (
    REPO_ROOT,
    PipelineInputError,
    load_json,
    pretty_json,
    receipt,
    repo_relative,
    utc_now,
    write_json,
)


PROJECT_FIELDS = ("publication_name", "topic", "audience", "central_question")
SOURCE_FIELDS = ("source_id", "publisher_id", "kind", "url")
PROMPTS = (
    "select_items.md",
    "create_briefs.md",
    "write_articles.md",
    "write_video_scripts.md",
)


def validate_config() -> tuple[dict, list[dict]]:
    project = load_json(REPO_ROOT / "config" / "project.json")
    if not isinstance(project, dict):
        raise PipelineInputError("config/project.json must contain a JSON object")
    for field in PROJECT_FIELDS:
        if not isinstance(project.get(field), str) or not project[field].strip():
            raise PipelineInputError(f"config/project.json field {field!r} must be a nonempty string")

    sources = load_json(REPO_ROOT / "config" / "sources.json")
    if not isinstance(sources, list) or not sources:
        raise PipelineInputError("config/sources.json must contain a nonempty array")
    seen_source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise PipelineInputError(f"source definition {index} must be an object")
        for field in SOURCE_FIELDS:
            if not isinstance(source.get(field), str) or not source[field].strip():
                raise PipelineInputError(f"source definition {index} field {field!r} must be nonempty")
        if source["kind"] not in {"feed", "youtube", "podcast"}:
            raise PipelineInputError(f"source definition {index} has invalid kind {source['kind']!r}")
        if source["source_id"] in seen_source_ids:
            raise PipelineInputError(f"duplicate source_id: {source['source_id']}")
        seen_source_ids.add(source["source_id"])

    policy = REPO_ROOT / "config" / "editorial_policy.md"
    if not policy.is_file() or not policy.read_text(encoding="utf-8").strip():
        raise PipelineInputError("config/editorial_policy.md must be nonempty")
    for name in PROMPTS:
        path = REPO_ROOT / "prompts" / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise PipelineInputError(f"prompts/{name} must be nonempty")
    return project, sources


def previous_live_run_id() -> str | None:
    rows: list[tuple[str, str]] = []
    runs_root = REPO_ROOT / "runs"
    if not runs_root.is_dir():
        return None
    for metadata_path in runs_root.glob("*/run.json"):
        try:
            value = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("mode") == "live" and isinstance(value.get("run_id"), str):
            rows.append((str(value.get("started_at", "")), value["run_id"]))
    return max(rows)[1] if rows else None


def create_run() -> pathlib.Path:
    validate_config()
    started_at = utc_now()
    now = datetime.now(timezone.utc)
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = REPO_ROOT / "runs" / run_id
    for name in (
        "logs",
        "candidates",
        "articles",
        "video_scripts",
        "config",
        "prompts",
    ):
        (run_dir / name).mkdir(parents=True, exist_ok=False if name == "logs" else True)

    for source in (REPO_ROOT / "config").iterdir():
        if source.is_file():
            shutil.copy2(source, run_dir / "config" / source.name)
    for source in (REPO_ROOT / "prompts").iterdir():
        if source.is_file():
            shutil.copy2(source, run_dir / "prompts" / source.name)

    metadata = {
        "run_id": run_id,
        "started_at": started_at,
        "as_of_date": now.date().isoformat(),
        "mode": "live",
        "previous_run_id": previous_live_run_id(),
    }
    write_json(run_dir / "run.json", metadata)
    receipt(
        run_dir,
        stage="run_initialize",
        status="completed",
        started_at=started_at,
        input_count=None,
        output_count=1,
        tools_or_models=["python-stdlib"],
        details={"run_dir": repo_relative(run_dir)},
    )
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "create"))
    args = parser.parse_args()
    try:
        if args.command == "validate":
            validate_config()
            return 0
        run_dir = create_run()
        print(repo_relative(run_dir))
        return 0
    except PipelineInputError as exc:
        print(f"run manager: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

