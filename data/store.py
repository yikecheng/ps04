#!/usr/bin/env python3
"""Private implementation for data/store.sh.

The public interface is the Bash component.  SQLite keeps logical items,
immutable evidence versions, and the runs in which each version was observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = REPO_ROOT / "data" / "evidence"
DB_NAME = "evidence.sqlite3"
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
    """The invocation or a supplied record violates the component contract."""


class MissingRecord(Exception):
    """A requested item or version does not exist."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def evidence_dir() -> Path:
    override = os.environ.get("PS04_EVIDENCE_DIR")
    if not override:
        return DEFAULT_EVIDENCE_DIR
    path = Path(override).expanduser()
    if not path.is_absolute():
        raise InvalidInput("PS04_EVIDENCE_DIR must be an absolute path")
    return path


def database_path() -> Path:
    return evidence_dir() / DB_NAME


def connect(create: bool) -> sqlite3.Connection:
    store_dir = evidence_dir()
    db_path = store_dir / DB_NAME
    if create:
        store_dir.mkdir(parents=True, exist_ok=True)
    elif not db_path.is_file():
        raise MissingRecord(
            "evidence store is not initialized; run 'bash data/store.sh init' first"
        )

    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL UNIQUE,
            latest_version_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS versions (
            item_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            content_fingerprint TEXT NOT NULL,
            record_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            PRIMARY KEY (item_id, version_id),
            UNIQUE (item_id, content_fingerprint),
            FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS observations (
            run_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            PRIMARY KEY (run_id, item_id, version_id),
            FOREIGN KEY (item_id, version_id)
                REFERENCES versions(item_id, version_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS versions_item_idx ON versions(item_id);
        CREATE INDEX IF NOT EXISTS observations_item_idx
            ON observations(item_id, version_id);
        """
    )
    # Non-destructive forward migration for stores initialized by an earlier
    # implementation that recorded observations without source retrieval time.
    observation_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(observations)").fetchall()
    }
    if "retrieved_at" not in observation_columns:
        connection.execute("ALTER TABLE observations ADD COLUMN retrieved_at TEXT")
        connection.execute(
            "UPDATE observations SET retrieved_at = observed_at WHERE retrieved_at IS NULL"
        )


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
        validate_item(value, line_number)
        records.append(value)
    return records


def require_nonempty_string(record: dict[str, Any], field: str, line_number: int) -> None:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(
            f"stdin line {line_number} field '{field}' must be a nonempty string"
        )


def validate_nullable_string(
    record: dict[str, Any], field: str, line_number: int
) -> None:
    value = record.get(field)
    if value is not None and not isinstance(value, str):
        raise InvalidInput(
            f"stdin line {line_number} field '{field}' must be a string or null"
        )


def validate_item(record: dict[str, Any], line_number: int) -> None:
    missing = sorted(REQUIRED_ITEM_FIELDS.difference(record))
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
        require_nonempty_string(record, field, line_number)

    if not isinstance(record["kind"], str) or record["kind"] not in VALID_KINDS:
        raise InvalidInput(
            f"stdin line {line_number} field 'kind' must be feed, youtube, or podcast"
        )

    validate_nullable_string(record, "published_at", line_number)
    validate_nullable_string(record, "media_url", line_number)
    validate_nullable_string(record, "segments_path", line_number)

    if record["kind"] in {"youtube", "podcast"} and not record["segments_path"]:
        raise InvalidInput(
            f"stdin line {line_number} audiovisual items require a segments_path"
        )


def content_fingerprint(record: dict[str, Any]) -> str:
    """Fingerprint evidence-relevant record data.

    Retrieval and extraction times are observation metadata, and version_id is the
    supplied digest, so none participates.  The retained text/transcript bytes plus
    the metadata used by extract_content's version computation do participate.  This
    independently enforces that merely retrieving unchanged material again cannot
    create a new evidence version, even if an upstream digest is accidentally noisy.
    """

    evidence_record = {
        "title": record["title"],
        "url": record["url"],
        "published_at": record["published_at"],
        "text_sha256": asset_digest(record["text_path"]),
        "segments_sha256": (
            asset_digest(record["segments_path"])
            if record["segments_path"] is not None
            else None
        ),
    }
    return hashlib.sha256(compact_json(evidence_record).encode("utf-8")).hexdigest()


def asset_digest(repo_relative_path: str) -> str:
    path = Path(repo_relative_path)
    if path.is_absolute():
        raise InvalidInput(f"evidence asset path must be repository-relative: {path}")
    resolved = (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError as error:
        raise InvalidInput(f"evidence asset path leaves the repository: {path}") from error
    if not resolved.is_file():
        raise InvalidInput(f"evidence asset does not exist: {path}")
    try:
        return hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as error:
        raise InvalidInput(f"cannot read evidence asset {path}: {error}") from error


def load_run(run_dir_arg: str) -> tuple[Path, str]:
    run_dir = Path(run_dir_arg)
    run_file = run_dir / "run.json"
    if not run_dir.is_dir():
        raise InvalidInput(f"RUN_DIR is not a directory: {run_dir}")
    try:
        run_data = json.loads(run_file.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InvalidInput(f"missing run metadata: {run_file}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidInput(f"cannot read valid run metadata from {run_file}: {error}") from error
    if not isinstance(run_data, dict):
        raise InvalidInput(f"run metadata must be a JSON object: {run_file}")
    run_id = run_data.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise InvalidInput(f"run metadata has no nonempty run_id: {run_file}")
    return run_dir, run_id


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
        "stage": "store_upsert",
        "status": status,
        "input_count": input_count,
        "output_count": output_count,
        "started_at": started_at,
        "finished_at": finished_at,
        "tools_or_models": ["python-stdlib", "sqlite3"],
        "cost_usd": None,
        "cost_estimate": False,
        "errors": errors,
        "exit_code": exit_code,
    }
    stamp = finished_at.replace(":", "").replace("-", "").replace(".", "")
    target = logs_dir / f"store-upsert-{stamp}-{uuid.uuid4().hex[:8]}.json"
    atomic_write_json(target, receipt)


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


def command_init(arguments: list[str]) -> int:
    if arguments:
        raise InvalidInput("usage: bash data/store.sh init")
    with connect(create=True) as connection:
        initialize_schema(connection)
    return 0


def resolve_version(
    connection: sqlite3.Connection,
    record: dict[str, Any],
    fingerprint: str,
) -> tuple[str, bool]:
    """Return the canonical version ID and whether a version row was inserted."""

    item_id = record["item_id"]
    supplied_version_id = record["version_id"]

    same_id = connection.execute(
        """
        SELECT version_id, content_fingerprint
        FROM versions
        WHERE item_id = ? AND version_id = ?
        """,
        (item_id, supplied_version_id),
    ).fetchone()
    if same_id is not None:
        if same_id["content_fingerprint"] != fingerprint:
            raise InvalidInput(
                f"version_id collision for item '{item_id}' and version "
                f"'{supplied_version_id}'"
            )
        return supplied_version_id, False

    same_content = connection.execute(
        """
        SELECT version_id
        FROM versions
        WHERE item_id = ? AND content_fingerprint = ?
        """,
        (item_id, fingerprint),
    ).fetchone()
    if same_content is not None:
        return str(same_content["version_id"]), False

    connection.execute(
        """
        INSERT INTO versions (
            item_id, version_id, content_fingerprint, record_json, first_seen_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            item_id,
            supplied_version_id,
            fingerprint,
            compact_json(record),
            utc_now(),
        ),
    )
    return supplied_version_id, True


def ingest_records(
    connection: sqlite3.Connection, records: list[dict[str, Any]], run_id: str
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    now = utc_now()

    connection.execute("BEGIN IMMEDIATE")
    try:
        for record in records:
            item_id = record["item_id"]
            fingerprint = content_fingerprint(record)
            item = connection.execute(
                "SELECT latest_version_id FROM items WHERE item_id = ?", (item_id,)
            ).fetchone()

            if item is None:
                # The items row must exist before its version because of the FK.
                connection.execute(
                    """
                    INSERT INTO items (
                        item_id, latest_version_id, first_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (item_id, record["version_id"], now, now),
                )
                canonical_version, _ = resolve_version(
                    connection, record, fingerprint
                )
                if canonical_version != record["version_id"]:
                    raise InvalidInput(
                        f"cannot establish first version for item '{item_id}'"
                    )
                change = "new"
            else:
                canonical_version, _ = resolve_version(
                    connection, record, fingerprint
                )
                if canonical_version == item["latest_version_id"]:
                    change = "unchanged"
                else:
                    change = "changed"
                    connection.execute(
                        """
                        UPDATE items
                        SET latest_version_id = ?, updated_at = ?
                        WHERE item_id = ?
                        """,
                        (canonical_version, now, item_id),
                    )

            connection.execute(
                """
                INSERT INTO observations (
                    run_id, item_id, version_id, retrieved_at, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (run_id, item_id, version_id) DO UPDATE SET
                    retrieved_at = excluded.retrieved_at,
                    observed_at = excluded.observed_at
                """,
                (
                    run_id,
                    item_id,
                    canonical_version,
                    record["retrieved_at"],
                    now,
                ),
            )
            changes.append(
                {
                    "item_id": item_id,
                    "version_id": canonical_version,
                    "change": change,
                }
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return changes


def command_upsert(arguments: list[str]) -> int:
    if len(arguments) != 1:
        raise InvalidInput("usage: bash data/store.sh upsert RUN_DIR")
    started_at = utc_now()
    run_dir, run_id = load_run(arguments[0])
    input_count: int | None = None

    try:
        records = read_json_lines(sys.stdin)
        input_count = len(records)
        with connect(create=True) as connection:
            initialize_schema(connection)
            changes = ingest_records(connection, records, run_id)
        write_receipt(
            run_dir,
            status="completed",
            input_count=input_count,
            output_count=len(changes),
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
    except (OSError, sqlite3.Error) as error:
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

    for change in changes:
        print(compact_json(change))
    return 0


def command_list(arguments: list[str]) -> int:
    if arguments:
        raise InvalidInput("usage: bash data/store.sh list")
    with connect(create=False) as connection:
        initialize_schema(connection)
        rows = connection.execute(
            """
            SELECT versions.record_json
            FROM items
            JOIN versions
              ON versions.item_id = items.item_id
             AND versions.version_id = items.latest_version_id
            ORDER BY items.sequence
            """
        ).fetchall()
    for row in rows:
        print(row["record_json"])
    return 0


def command_get(arguments: list[str]) -> int:
    if len(arguments) not in {1, 2}:
        raise InvalidInput("usage: bash data/store.sh get ITEM_ID [VERSION_ID]")
    item_id = arguments[0]
    if not item_id:
        raise InvalidInput("ITEM_ID must be nonempty")

    with connect(create=False) as connection:
        initialize_schema(connection)
        if len(arguments) == 1:
            row = connection.execute(
                """
                SELECT versions.record_json
                FROM items
                JOIN versions
                  ON versions.item_id = items.item_id
                 AND versions.version_id = items.latest_version_id
                WHERE items.item_id = ?
                """,
                (item_id,),
            ).fetchone()
            requested = item_id
        else:
            version_id = arguments[1]
            if not version_id:
                raise InvalidInput("VERSION_ID must be nonempty")
            row = connection.execute(
                """
                SELECT record_json
                FROM versions
                WHERE item_id = ? AND version_id = ?
                """,
                (item_id, version_id),
            ).fetchone()
            requested = f"{item_id}@{version_id}"

    if row is None:
        raise MissingRecord(f"evidence record not found: {requested}")
    print(row["record_json"])
    return 0


def main(arguments: list[str]) -> int:
    if not arguments:
        raise InvalidInput("usage: bash data/store.sh {init|upsert|list|get} ...")
    command, command_arguments = arguments[0], arguments[1:]
    if command == "init":
        return command_init(command_arguments)
    if command == "upsert":
        return command_upsert(command_arguments)
    if command == "list":
        return command_list(command_arguments)
    if command == "get":
        return command_get(command_arguments)
    raise InvalidInput(f"unknown store command: {command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except InvalidInput as error:
        print(f"store: {error}", file=sys.stderr)
        raise SystemExit(2)
    except MissingRecord as error:
        print(f"store: {error}", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, sqlite3.Error) as error:
        print(f"store: operational failure: {error}", file=sys.stderr)
        raise SystemExit(1)
