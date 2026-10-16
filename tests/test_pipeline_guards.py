from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))

from coverage_check import assess_coverage  # noqa: E402
from editorial.select_items import validate as validate_decisions  # noqa: E402
from markdown_metrics import spoken_word_count  # noqa: E402
from processing.extract_content import parse_vtt_srt, source_timestamped_sections  # noqa: E402


class CoverageGateTests(unittest.TestCase):
    def make_items(self) -> list[dict[str, str]]:
        kinds = ["feed"] * 8 + ["youtube"] * 2 + ["podcast"] * 2
        return [
            {"item_id": f"item-{index}", "kind": kind, "publisher_id": f"publisher-{index % 6}"}
            for index, kind in enumerate(kinds)
        ]

    def test_assignment_minimums_pass(self) -> None:
        result = assess_coverage(self.make_items())
        self.assertTrue(result["passed"])
        self.assertEqual(result["kind_counts"], {"feed": 8, "youtube": 2, "podcast": 2})

    def test_each_minimum_is_blocking(self) -> None:
        too_few = self.make_items()[:-1]
        result = assess_coverage(too_few)
        self.assertFalse(result["passed"])
        self.assertTrue(any("at least 12" in message for message in result["errors"]))
        self.assertTrue(any("podcast" in message for message in result["errors"]))


class TranscriptParserTests(unittest.TestCase):
    def test_html_comment_arrow_is_not_a_subtitle_cue(self) -> None:
        self.assertEqual(parse_vtt_srt("<html><!-- build marker -->text</html>"), [])

    def test_empty_arrow_line_is_ignored(self) -> None:
        self.assertEqual(parse_vtt_srt("WEBVTT\n\n --> \nnot a cue\n"), [])

    def test_publisher_section_timestamps_allow_bracket_spacing(self) -> None:
        transcript = """Transcript

        Opening [ 01:09 ]

        This first transcript paragraph contains enough words to be retained as evidence.

        Verification [09:29]

        This second transcript paragraph also contains enough words to become timestamped evidence.
        """
        segments = source_timestamped_sections(transcript, 700)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["start_seconds"], 69.0)
        self.assertEqual(segments[1]["start_seconds"], 569.0)
        self.assertTrue(all(segment["timestamp_method"] == "source_section_timestamp_interpolated" for segment in segments))


class MarkdownMetricTests(unittest.TestCase):
    def test_spoken_count_uses_only_labeled_narration(self) -> None:
        script = """# Title

**Narration**

These five words are actually spoken.

**Visual direction**

[VISUAL: These production notes are not spoken aloud.]

## Ready-to-paste description

This copy is metadata, not narration.
"""
        self.assertEqual(spoken_word_count(script), 6)


class SelectionIdentityTests(unittest.TestCase):
    def test_pipeline_reattaches_item_identity_from_slots(self) -> None:
        items = [
            {"item_id": "item-a", "version_id": "version-a"},
            {"item_id": "item-b", "version_id": "version-b"},
        ]
        model_rows = [
            {"decision_slot": "slot-0002", "decision": "reject", "reason": "duplicate", "piece_ids": []},
            {"decision_slot": "slot-0001", "decision": "accept", "reason": "useful", "piece_ids": ["02"]},
        ]
        rows = validate_decisions(items, model_rows)
        self.assertEqual(
            [(row["item_id"], row["version_id"], row["decision"]) for row in rows],
            [("item-a", "version-a", "accept"), ("item-b", "version-b", "reject")],
        )


if __name__ == "__main__":
    unittest.main()
