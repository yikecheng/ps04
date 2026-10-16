#!/usr/bin/env python3
"""Auditable structured-output model invocation for editorial components."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any

from pipeline_common import PipelineInputError, compact_json, repo_relative, write_json


def invoke_structured(
    *,
    run_dir: pathlib.Path,
    stage: str,
    prompt: str,
    schema: dict[str, Any],
    timeout_seconds: int = 900,
) -> tuple[Any, dict[str, Any]]:
    provider = os.environ.get("PS04_MODEL_PROVIDER", "codex").strip().lower()
    if provider != "codex":
        raise PipelineInputError(
            f"unsupported PS04_MODEL_PROVIDER {provider!r}; live editorial stages require 'codex'"
        )
    executable = shutil.which("codex")
    if not executable:
        raise PipelineInputError("codex CLI is required for the configured model provider")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    nonce = uuid.uuid4().hex[:8]
    base = run_dir / "logs" / f"{stamp}-{stage}-model-{nonce}"
    request_path = base.parent / f"{base.name}.request.txt"
    response_path = base.parent / f"{base.name}.response.json"
    events_path = base.parent / f"{base.name}.events.jsonl"
    schema_path = base.parent / f"{base.name}.schema.json"
    request_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
    write_json(schema_path, schema)

    command = [
        executable,
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(response_path),
        "--json",
        "-",
    ]
    model = os.environ.get("PS04_MODEL")
    if model:
        command[2:2] = ["--model", model]
    try:
        result = subprocess.run(
            command,
            input=prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            cwd=run_dir.parent.parent,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineInputError(f"model invocation timed out after {timeout_seconds} seconds") from exc
    events_path.write_text(result.stdout, encoding="utf-8")
    if result.stderr:
        (base.parent / f"{base.name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        raise PipelineInputError(f"codex model invocation exited {result.returncode}: {message}")
    if not response_path.is_file():
        raise PipelineInputError("codex model invocation produced no final response")
    try:
        value = json.loads(response_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineInputError(f"model response was not valid JSON: {exc}") from exc
    usage: dict[str, int] = {}
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = {
                key: int(raw)
                for key, raw in event["usage"].items()
                if isinstance(raw, (int, float))
            }
    metadata = {
        "provider": "codex-cli",
        "model": model or "account-default",
        "request_path": repo_relative(request_path),
        "response_path": repo_relative(response_path),
        "events_path": repo_relative(events_path),
        "schema_path": repo_relative(schema_path),
        "cost_usd": None,
        "usage": usage,
    }
    return value, metadata
