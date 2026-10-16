#!/usr/bin/env python3
"""Deterministic component tests for the evidence store and date filter."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def parse_jsonl(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line]


class ComponentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temporary_directory.name)
        self.run_dir = self.temp_root / "run"
        self.run_dir.mkdir()
        self.run_dir.joinpath("run.json").write_text(
            EXAMPLES.joinpath("run.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.environment = os.environ.copy()
        self.environment["PS04_EVIDENCE_DIR"] = str(self.temp_root / "evidence")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def command(
        self, arguments: list[str], *, input_text: str = "", check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            arguments,
            cwd=ROOT,
            env=self.environment,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"command failed ({result.returncode}): {' '.join(arguments)}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result


class EvidenceStoreTests(ComponentTestCase):
    STORE = ["bash", "data/store.sh"]

    def test_example_ingest_replay_history_and_semantic_deduplication(self) -> None:
        self.command(self.STORE + ["init"])

        initial = self.command(
            self.STORE + ["upsert", str(self.run_dir)],
            input_text=EXAMPLES.joinpath("items.jsonl").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            parse_jsonl(initial.stdout),
            read_jsonl(EXAMPLES / "initial_changes_expected.jsonl"),
        )

        # Even a bad upstream digest cannot turn a retrieval-only refresh into
        # a new version: the store maps it to the existing canonical version.
        refreshed = read_jsonl(EXAMPLES / "items.jsonl")[0]
        original_version = refreshed["version_id"]
        refreshed["retrieved_at"] = "2026-10-08T15:00:00Z"
        refreshed["version_id"] = "retrieval-time-must-not-create-a-version"
        refresh_result = self.command(
            self.STORE + ["upsert", str(self.run_dir)],
            input_text=json.dumps(refreshed) + "\n",
        )
        self.assertEqual(
            parse_jsonl(refresh_result.stdout),
            [
                {
                    "item_id": refreshed["item_id"],
                    "version_id": original_version,
                    "change": "unchanged",
                }
            ],
        )

        replay = self.command(
            self.STORE + ["upsert", str(self.run_dir)],
            input_text=EXAMPLES.joinpath("replay_items.jsonl").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            parse_jsonl(replay.stdout),
            read_jsonl(EXAMPLES / "replay_changes_expected.jsonl"),
        )

        listed = parse_jsonl(self.command(self.STORE + ["list"]).stdout)
        self.assertEqual(len(listed), 3)
        latest_by_id = {record["item_id"]: record for record in listed}
        changed_podcast = read_jsonl(EXAMPLES / "replay_items.jsonl")[-1]
        self.assertEqual(
            latest_by_id["podcast:fictional-episode"]["version_id"],
            changed_podcast["version_id"],
        )

        original_podcast = read_jsonl(EXAMPLES / "items.jsonl")[-1]
        historical = json.loads(
            self.command(
                self.STORE
                + [
                    "get",
                    original_podcast["item_id"],
                    original_podcast["version_id"],
                ]
            ).stdout
        )
        self.assertEqual(historical, original_podcast)

        missing = self.command(
            self.STORE
            + ["get", refreshed["item_id"], "retrieval-time-must-not-create-a-version"],
            check=False,
        )
        self.assertEqual(missing.returncode, 1)
        self.assertIn("not found", missing.stderr)

        receipts = list(self.run_dir.joinpath("logs").glob("store-upsert-*.json"))
        self.assertEqual(len(receipts), 3)
        for receipt_path in receipts:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["stage"], "store_upsert")
            self.assertEqual(receipt["status"], "completed")

    def test_invalid_version_collision_rolls_back_whole_ingest(self) -> None:
        self.command(self.STORE + ["init"])
        items = read_jsonl(EXAMPLES / "items.jsonl")
        self.command(
            self.STORE + ["upsert", str(self.run_dir)],
            input_text=json.dumps(items[0]) + "\n",
        )

        new_item = dict(items[0])
        new_item["item_id"] = "feed:must-roll-back"
        new_item["version_id"] = "rollback-version"
        collision = dict(items[0])
        collision["title"] = "Different content under the same version ID"
        attempt = self.command(
            self.STORE + ["upsert", str(self.run_dir)],
            input_text=json.dumps(new_item) + "\n" + json.dumps(collision) + "\n",
            check=False,
        )
        self.assertEqual(attempt.returncode, 2)
        self.assertIn("version_id collision", attempt.stderr)
        absent = self.command(
            self.STORE + ["get", "feed:must-roll-back"], check=False
        )
        self.assertEqual(absent.returncode, 1)


class FilterTests(ComponentTestCase):
    FILTER = ["bash", "processing/filter_items.sh"]

    def test_example_window_and_exclusion_reasons(self) -> None:
        result = self.command(
            self.FILTER + [str(self.run_dir)],
            input_text=EXAMPLES.joinpath("filter_input.jsonl").read_text(
                encoding="utf-8"
            ),
        )
        eligible = parse_jsonl(result.stdout)
        exclusions = read_jsonl(self.run_dir / "exclusions.jsonl")
        expected = json.loads(
            EXAMPLES.joinpath("filter_expected.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            [record["item_id"] for record in eligible], expected["eligible_item_ids"]
        )
        self.assertEqual(
            [
                {"item_id": record["item_id"], "reason": record["reason"]}
                for record in exclusions
            ],
            expected["exclusions"],
        )
        self.assertTrue(all(record["detail"] for record in exclusions))

        receipts = list(self.run_dir.joinpath("logs").glob("filter-items-*.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["input_count"], 9)
        self.assertEqual(receipt["output_count"], 5)
        self.assertEqual(receipt["status"], "completed")

    def test_dates_are_compared_as_utc_calendar_dates(self) -> None:
        base = read_jsonl(EXAMPLES / "items.jsonl")[0]
        utc_end = dict(base)
        utc_end.update(
            item_id="feed:offset-end",
            version_id="offset-end-version",
            published_at="2026-10-09T01:00:00+02:00",
        )
        before_start = dict(base)
        before_start.update(
            item_id="feed:offset-before-start",
            version_id="offset-before-version",
            published_at="2026-09-09T00:30:00+01:00",
        )
        result = self.command(
            self.FILTER + [str(self.run_dir)],
            input_text=json.dumps(utc_end) + "\n" + json.dumps(before_start) + "\n",
        )
        self.assertEqual(
            [record["item_id"] for record in parse_jsonl(result.stdout)],
            ["feed:offset-end"],
        )
        exclusions = read_jsonl(self.run_dir / "exclusions.jsonl")
        self.assertEqual(exclusions[0]["reason"], "outside_window")

    def test_malformed_stream_exits_two_without_replacing_exclusions(self) -> None:
        sentinel = '{"sentinel":true}\n'
        self.run_dir.joinpath("exclusions.jsonl").write_text(sentinel, encoding="utf-8")
        result = self.command(
            self.FILTER + [str(self.run_dir)],
            input_text='{"item_id":"missing-fields"}\n',
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("version_id", result.stderr)
        self.assertEqual(
            self.run_dir.joinpath("exclusions.jsonl").read_text(encoding="utf-8"),
            sentinel,
        )


if __name__ == "__main__":
    unittest.main()
