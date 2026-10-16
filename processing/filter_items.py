#!/usr/bin/env python3
"""Private implementation for processing/filter_items.sh."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


ISO_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})$"
)
VALID_KINDS = {"feed", "youtube", "podcast"}
REQUIRED_ITEM_FIELDS = {
    "item_id",
    "source_id",
    "publisher_id",
    "kind",
    "title",
    "url",
    "published_at",
    "retrieved_at",
    "media_url",
    "version_id",
    "text_path",
    "segments_path",
}


class InvalidInput(Exception):
    """The invocation, run metadata, or JSONL stream is malformed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def atomic_write_json_lines(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(compact_json(record))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def read_run(run_dir_arg: str) -> tuple[Path, date]:
    run_dir = Path(run_dir_arg)
    if not run_dir.is_dir():
        raise InvalidInput(f"RUN_DIR is not a directory: {run_dir}")
    run_file = run_dir / "run.json"
    try:
        run_data = json.loads(run_file.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InvalidInput(f"missing run metadata: {run_file}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidInput(f"cannot read valid run metadata from {run_file}: {error}") from error
    if not isinstance(run_data, dict):
        raise InvalidInput(f"run metadata must be a JSON object: {run_file}")
    as_of_value = run_data.get("as_of_date")
    if not isinstance(as_of_value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", as_of_value
    ):
        raise InvalidInput("run.json as_of_date must use YYYY-MM-DD")
    try:
        as_of_date = date.fromisoformat(as_of_value)
    except ValueError as error:
        raise InvalidInput(f"run.json as_of_date is invalid: {as_of_value}") from error
    return run_dir, as_of_date


def read_json_lines(stream: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(stream, start=1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise InvalidInput(
                f"stdin line {line_number} is not valid JSON: {error.msg}"
            ) from error
        if not isinstance(value, dict):
            raise InvalidInput(f"stdin line {line_number} must be a JSON object")
        missing = sorted(REQUIRED_ITEM_FIELDS.difference(value))
        if missing:
            raise InvalidInput(
                f"stdin line {line_number} is missing required fields: {', '.join(missing)}"
            )
        for field in (
            "item_id",
            "source_id",
            "publisher_id",
            "title",
            "url",
            "retrieved_at",
            "version_id",
            "text_path",
        ):
            field_value = value.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise InvalidInput(
                    f"stdin line {line_number} field '{field}' must be a nonempty string"
                )
        if not isinstance(value["kind"], str) or value["kind"] not in VALID_KINDS:
            raise InvalidInput(
                f"stdin line {line_number} field 'kind' must be feed, youtube, or podcast"
            )
        for field in ("media_url", "segments_path"):
            if value[field] is not None and not isinstance(value[field], str):
                raise InvalidInput(
                    f"stdin line {line_number} field '{field}' must be a string or null"
                )
        if value["kind"] in {"youtube", "podcast"} and not value["segments_path"]:
            raise InvalidInput(
                f"stdin line {line_number} audiovisual items require a segments_path"
            )
        records.append(value)
    return records


def publication_date(value: Any) -> tuple[date | None, str | None]:
    if value is None:
        return None, "unknown_date"
    if not isinstance(value, str) or not ISO_TIMESTAMP.fullmatch(value):
        return None, "invalid_date"
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError:
        return None, "invalid_date"
    if timestamp.tzinfo is None:
        return None, "invalid_date"
    try:
        return timestamp.astimezone(timezone.utc).date(), None
    except (OverflowError, ValueError):
        return None, "invalid_date"


def exclusion_detail(
    reason: str,
    published_at: Any,
    parsed_date: date | None,
    window_start: date,
    window_end: date,
) -> str:
    if reason == "unknown_date":
        return "published_at is null"
    if reason == "invalid_date":
        return f"published_at is not a valid ISO 8601 timestamp: {published_at!r}"
    if reason == "future_date":
        return (
            f"publication date {parsed_date.isoformat()} is after as-of date "
            f"{window_end.isoformat()}"
        )
    return (
        f"publication date {parsed_date.isoformat()} is before inclusive window "
        f"{window_start.isoformat()} through {window_end.isoformat()}"
    )


def filter_records(
    records: list[dict[str, Any]], as_of_date: date
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    window_start = as_of_date - timedelta(days=29)
    eligible: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []

    for record in records:
        parsed_date, parse_reason = publication_date(record["published_at"])
        reason = parse_reason
        if reason is None and parsed_date is not None:
            if parsed_date > as_of_date:
                reason = "future_date"
            elif parsed_date < window_start:
                reason = "outside_window"

        if reason is None:
            eligible.append(record)
            continue

        exclusions.append(
            {
                "item_id": record["item_id"],
                "version_id": record["version_id"],
                "reason": reason,
                "detail": exclusion_detail(
                    reason,
                    record["published_at"],
                    parsed_date,
                    window_start,
                    as_of_date,
                ),
            }
        )

    return eligible, exclusions


def write_receipt(
    run_dir: Path,
    *,
    status: str,
    input_count: int | None,
    output_count: int,
    started_at: str,
    errors: list[str],
    exit_code: int,
) -> None:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    finished_at = utc_now()
    receipt = {
        "stage": "filter_items",
        "status": status,
        "input_count": input_count,
        "output_count": output_count,
        "started_at": started_at,
        "finished_at": finished_at,
        "tools_or_models": ["python-stdlib"],
        "cost_usd": None,
        "cost_estimate": False,
        "errors": errors,
        "exit_code": exit_code,
    }
    stamp = finished_at.replace(":", "").replace("-", "").replace(".", "")
    target = logs_dir / f"filter-items-{stamp}-{uuid.uuid4().hex[:8]}.json"
    atomic_write_json(target, receipt)


def run(arguments: list[str]) -> int:
    if len(arguments) != 1:
        raise InvalidInput("usage: bash processing/filter_items.sh RUN_DIR")

    started_at = utc_now()
    run_dir, as_of_date = read_run(arguments[0])
    input_count: int | None = None
    try:
        records = read_json_lines(sys.stdin)
        input_count = len(records)
        eligible, exclusions = filter_records(records, as_of_date)
        atomic_write_json_lines(run_dir / "exclusions.jsonl", exclusions)
        write_receipt(
            run_dir,
            status="completed",
            input_count=input_count,
            output_count=len(eligible),
            started_at=started_at,
            errors=[],
            exit_code=0,
        )
    except InvalidInput as error:
        write_receipt(
            run_dir,
            status="failed",
            input_count=input_count,
            output_count=0,
            started_at=started_at,
            errors=[str(error)],
            exit_code=2,
        )
        raise
    except OSError as error:
        write_receipt(
            run_dir,
            status="failed",
            input_count=input_count,
            output_count=0,
            started_at=started_at,
            errors=[str(error)],
            exit_code=1,
        )
        raise

    for record in eligible:
        print(compact_json(record))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:]))
    except InvalidInput as error:
        print(f"filter_items: {error}", file=sys.stderr)
        raise SystemExit(2)
    except OSError as error:
        print(f"filter_items: operational failure: {error}", file=sys.stderr)
        raise SystemExit(1)
