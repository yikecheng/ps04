#!/usr/bin/env python3
"""JSONL validation and combination for workflow coordinators."""

from __future__ import annotations

import argparse
import pathlib
import sys

from pipeline_common import PipelineInputError, compact_json, iter_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    try:
        if not args.paths:
            records = iter_jsonl(sys.stdin, source="stdin")
            for record in records:
                print(compact_json(record))
            return 0
        for raw_path in args.paths:
            path = pathlib.Path(raw_path)
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for record in iter_jsonl(handle, source=raw_path):
                    print(compact_json(record))
        return 0
    except (OSError, PipelineInputError) as exc:
        print(f"jsonl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

