#!/usr/bin/env python3
"""Small CLI used by Bash coordinators to write their own receipts."""

from __future__ import annotations

import argparse
import sys

from pipeline_common import PipelineInputError, receipt, require_run_dir, utc_now


def nullable_count(value: str) -> int | None:
    if value == "null":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("count must be an integer or null") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("stage")
    parser.add_argument("status")
    parser.add_argument("started_at")
    parser.add_argument("input_count", type=nullable_count)
    parser.add_argument("output_count", type=nullable_count)
    parser.add_argument("--tool", action="append", default=[])
    parser.add_argument("--error", action="append", default=[])
    args = parser.parse_args()
    try:
        run_dir = require_run_dir(args.run_dir)
        receipt(
            run_dir,
            stage=args.stage,
            status=args.status,
            started_at=args.started_at,
            input_count=args.input_count,
            output_count=args.output_count,
            tools_or_models=args.tool,
            errors=args.error,
        )
        return 0
    except PipelineInputError as exc:
        print(f"receipt: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

