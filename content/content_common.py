"""Evidence resolution shared by the two audience-content generators."""

from __future__ import annotations

from typing import Any

from pipeline_common import REPO_ROOT, PipelineInputError, load_json, read_jsonl


def timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def resolved_packet(run_dir, briefs: list[dict[str, Any]]) -> dict[str, Any]:
    items = {
        (str(item["item_id"]), str(item["version_id"])): item
        for item in read_jsonl(run_dir / "eligible.jsonl")
    }
    packet: dict[str, Any] = {"briefs": briefs, "sources": []}
    references: dict[tuple[str, str], dict[str, Any]] = {}
    for brief in briefs:
        for claim in brief.get("claims", []):
            for evidence in claim.get("evidence", []):
                key = (str(evidence["item_id"]), str(evidence["version_id"]))
                item = items.get(key)
                if item is None:
                    raise PipelineInputError(f"content input references unknown evidence: {key}")
                entry = references.setdefault(
                    key,
                    {
                        "item_id": key[0],
                        "version_id": key[1],
                        "publisher_id": item["publisher_id"],
                        "kind": item["kind"],
                        "title": item["title"],
                        "url": item["url"],
                        "published_at": item["published_at"],
                        "locators": [],
                    },
                )
                locator = evidence["locator"]
                resolved = dict(locator)
                if locator.get("type") == "segment":
                    rows = load_json(REPO_ROOT / str(item["segments_path"]))
                    row = next((value for value in rows if value.get("segment_id") == locator.get("segment_id")), None)
                    if row is None:
                        raise PipelineInputError(f"unresolvable segment in content input: {key}")
                    resolved.update(
                        {
                            "start_seconds": row["start_seconds"],
                            "end_seconds": row["end_seconds"],
                            "timestamp": timestamp(float(row["start_seconds"])),
                            "passage": row["text"],
                        }
                    )
                entry["locators"].append(resolved)
    packet["sources"] = list(references.values())
    return packet


def word_count_without_sources(markdown: str) -> int:
    marker = "## Sources"
    body = markdown.split(marker, 1)[0]
    import re
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"[`*_>#\[\]()!-]", " ", body)
    return len(re.findall(r"\b[\w’'-]+\b", body))

