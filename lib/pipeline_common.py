#!/usr/bin/env python3
"""Shared, dependency-free utilities for the intelligence pipeline.

The module deliberately contains plumbing only: JSONL handling, timestamps,
atomic files, run-path validation, and stage receipts.  Editorial, collection,
storage, and rendering logic remain in their owning components.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class PipelineInputError(ValueError):
    """Raised for invalid arguments, configuration, or malformed records."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def repo_relative(path: pathlib.Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def resolve_repo_path(value: str | os.PathLike[str]) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def require_run_dir(value: str | os.PathLike[str], *, require_metadata: bool = True) -> pathlib.Path:
    path = resolve_repo_path(value)
    try:
        path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise PipelineInputError("RUN_DIR must be inside the repository") from exc
    if not path.is_dir():
        raise PipelineInputError(f"RUN_DIR does not exist: {value}")
    if require_metadata and not (path / "run.json").is_file():
        raise PipelineInputError(f"RUN_DIR is missing run.json: {value}")
    return path


def load_json(path: pathlib.Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise PipelineInputError(f"missing required JSON file: {repo_relative(path)}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineInputError(
            f"malformed JSON in {repo_relative(path)} at line {exc.lineno}, column {exc.colno}"
        ) from exc


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def atomic_write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def write_json(path: pathlib.Path, value: Any) -> None:
    atomic_write_text(path, pretty_json(value))


def iter_jsonl(handle: Iterable[str], *, source: str = "stdin") -> Iterator[dict[str, Any]]:
    for line_number, raw in enumerate(handle, 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PipelineInputError(f"malformed JSONL in {source} at line {line_number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise PipelineInputError(f"JSONL record in {source} at line {line_number} is not an object")
        yield value


def read_jsonl(path: pathlib.Path, *, absent_ok: bool = False) -> list[dict[str, Any]]:
    if absent_ok and not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            return list(iter_jsonl(handle, source=repo_relative(path)))
    except FileNotFoundError as exc:
        raise PipelineInputError(f"missing required JSONL file: {repo_relative(path)}") from exc


def write_jsonl(path: pathlib.Path, records: Iterable[dict[str, Any]]) -> int:
    materialized = list(records)
    text = "".join(compact_json(record) + "\n" for record in materialized)
    atomic_write_text(path, text)
    return len(materialized)


def emit_jsonl(records: Iterable[dict[str, Any]]) -> int:
    count = 0
    for record in records:
        sys.stdout.write(compact_json(record) + "\n")
        count += 1
    return count


def sha256_json(value: Any) -> str:
    return hashlib.sha256(compact_json(value).encode("utf-8")).hexdigest()


def sha256_files(paths: Iterable[pathlib.Path], *, extra: Any = None) -> str:
    digest = hashlib.sha256()
    for path in sorted((p.resolve() for p in paths), key=str):
        digest.update(repo_relative(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if extra is not None:
        digest.update(compact_json(extra).encode("utf-8"))
    return digest.hexdigest()


def receipt(
    run_dir: pathlib.Path,
    *,
    stage: str,
    status: str,
    started_at: str,
    input_count: int | None,
    output_count: int | None,
    tools_or_models: list[str] | None = None,
    cost_usd: float | None = None,
    cost_estimate: bool = False,
    errors: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> pathlib.Path:
    finished_at = utc_now()
    safe_stage = "".join(char if char.isalnum() or char in "-_" else "-" for char in stage)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = run_dir / "logs" / f"{stamp}-{safe_stage}-{uuid.uuid4().hex[:8]}.json"
    body: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "input_count": input_count,
        "output_count": output_count,
        "started_at": started_at,
        "finished_at": finished_at,
        "tools_or_models": tools_or_models or [],
        "cost_usd": cost_usd,
        "cost_estimate": bool(cost_estimate),
        "errors": errors or [],
    }
    if details:
        body["details"] = details
    write_json(path, body)
    return path


def require_fields(record: dict[str, Any], fields: Iterable[str], *, record_name: str) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        raise PipelineInputError(f"{record_name} missing required field(s): {', '.join(missing)}")


def stderr(message: str) -> None:
    print(message, file=sys.stderr)

