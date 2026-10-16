#!/usr/bin/env python3
"""Retrieve substantive text and timestamped media transcripts."""

from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import os
import pathlib
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

from pipeline_common import (
    REPO_ROOT,
    PipelineInputError,
    compact_json,
    iter_jsonl,
    receipt,
    repo_relative,
    require_fields,
    require_run_dir,
    sha256_json,
    utc_now,
    write_json,
)


USER_AGENT = "MIT-1.125-PS04-Intelligence-Pipeline/1.0 (+coursework; evidence extraction)"
EXTRACTOR_VERSION = "2"
CANDIDATE_FIELDS = (
    "item_id",
    "source_id",
    "publisher_id",
    "kind",
    "title",
    "url",
    "published_at",
    "retrieved_at",
    "media_url",
)


def tls_context() -> ssl.SSLContext:
    """Build a verified TLS context that also works with macOS system Python."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


TLS_CONTEXT = tls_context()


class MainTextParser(HTMLParser):
    BLOCKED = {"script", "style", "svg", "noscript", "nav", "footer", "header", "form"}
    CONTENT = {"p", "li", "blockquote", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocked_depth = 0
        self.capture_depth = 0
        self.current: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED:
            self.blocked_depth += 1
        elif not self.blocked_depth and tag in self.CONTENT:
            self.capture_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.BLOCKED and self.blocked_depth:
            self.blocked_depth -= 1
        elif not self.blocked_depth and tag in self.CONTENT and self.capture_depth:
            self.capture_depth -= 1
            if self.capture_depth == 0:
                text = normalize_text(" ".join(self.current))
                if text:
                    self.blocks.append(text)
                self.current = []

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth and self.capture_depth:
            self.current.append(data)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch(url: str, *, accept: str = "*/*", timeout: int = 45) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
        return response.read(), response.headers.get_content_type()


def article_text(payload: bytes, content_type: str) -> str:
    decoded = payload.decode("utf-8", errors="replace")
    if content_type in {"text/plain", "text/markdown"}:
        return decoded.strip()
    parser = MainTextParser()
    parser.feed(decoded)
    # Remove exact adjacent duplicates common in responsive HTML.
    result: list[str] = []
    for block in parser.blocks:
        if len(block.split()) < 3:
            continue
        if not result or block != result[-1]:
            result.append(block)
    return "\n\n".join(result).strip()


TIMESTAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)")


def seconds(value: str) -> float:
    match = TIMESTAMP.search(value.replace(",", "."))
    if not match:
        raise ValueError(value)
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    secs = float(match.group(3))
    return round(hours * 3600 + minutes * 60 + secs, 3)


def parse_vtt_srt(text: str) -> list[dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        if "-->" not in lines[index]:
            index += 1
            continue
        start_raw, end_raw = [part.strip() for part in lines[index].split("-->", 1)]
        if not start_raw or not end_raw.split():
            index += 1
            continue
        end_raw = end_raw.split()[0]
        index += 1
        words: list[str] = []
        while index < len(lines) and lines[index].strip():
            cleaned = re.sub(r"<[^>]+>", "", lines[index])
            cleaned = re.sub(r"^\s*>>\s*", "", cleaned)
            words.append(cleaned)
            index += 1
        text_value = normalize_text(" ".join(words))
        if text_value:
            try:
                start_value, end_value = seconds(start_raw), seconds(end_raw)
            except ValueError:
                continue
            # Auto-captions often repeat the previous rolling line.
            if segments and text_value == segments[-1]["text"]:
                segments[-1]["end_seconds"] = end_value
            else:
                segments.append(
                    {
                        "segment_id": f"seg-{len(segments) + 1:04d}",
                        "start_seconds": start_value,
                        "end_seconds": end_value,
                        "text": text_value,
                        "timestamp_method": "source_caption",
                    }
                )
        index += 1
    return segments


def parse_json_transcript(payload: Any) -> list[dict[str, Any]]:
    rows: Any = payload
    if isinstance(payload, dict):
        for key in ("segments", "transcript", "items", "results"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    if not isinstance(rows, list):
        return []
    segments: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text_value = normalize_text(str(row.get("text") or row.get("body") or ""))
        start = row.get("start_seconds", row.get("start", row.get("offset", 0)))
        end = row.get("end_seconds", row.get("end"))
        duration = row.get("duration")
        try:
            start_float = float(start)
            end_float = float(end) if end is not None else start_float + float(duration or 0)
        except (TypeError, ValueError):
            continue
        if text_value:
            segments.append(
                {
                    "segment_id": str(row.get("segment_id") or f"seg-{len(segments) + 1:04d}"),
                    "start_seconds": round(start_float, 3),
                    "end_seconds": round(max(start_float, end_float), 3),
                    "text": text_value,
                    "timestamp_method": str(row.get("timestamp_method") or "source_transcript"),
                }
            )
    return segments


def duration_seconds(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        pass
    parts = str(raw).strip().split(":")
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None
    if len(values) == 3:
        return values[0] * 3600 + values[1] * 60 + values[2]
    if len(values) == 2:
        return values[0] * 60 + values[1]
    return values[0] if values else None


def estimate_segments(text: str, duration: float | None) -> list[dict[str, Any]]:
    words = normalize_text(text).split()
    if not words:
        return []
    if not duration or duration <= 0:
        duration = max(1.0, len(words) / 2.5)
    chunk_size = 45
    segments: list[dict[str, Any]] = []
    for offset in range(0, len(words), chunk_size):
        chunk = words[offset : offset + chunk_size]
        start = duration * offset / len(words)
        end = duration * min(len(words), offset + len(chunk)) / len(words)
        segments.append(
            {
                "segment_id": f"seg-{len(segments) + 1:04d}",
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "text": " ".join(chunk),
                "timestamp_method": "estimated_from_duration",
            }
        )
    return segments


def source_timestamped_sections(text: str, duration: float | None) -> list[dict[str, Any]]:
    """Turn publisher transcript sections such as ``Topic [09:29]`` into segments.

    Paragraph locations inside a timestamped section are interpolated and
    explicitly labeled; the section boundaries themselves come from the
    publisher rather than an invented model timestamp.
    """
    blocks = [normalize_text(block) for block in re.split(r"\n\s*\n", text) if normalize_text(block)]
    transcript_indexes = [index for index, block in enumerate(blocks) if block.casefold() == "transcript"]
    if transcript_indexes:
        blocks = blocks[transcript_indexes[-1] + 1 :]
    # Publisher pages commonly render spaces inside the brackets (``[ 09:29 ]``).
    marker = re.compile(r"\[\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*\]")
    sections: list[tuple[float, list[str]]] = [(0.0, [])]
    for block in blocks:
        match = marker.search(block)
        if match:
            hours = int(match.group(1) or 0)
            start = hours * 3600 + int(match.group(2)) * 60 + int(match.group(3))
            sections.append((float(start), []))
            remainder = normalize_text(marker.sub("", block))
            # Headings label the section but are not spoken transcript evidence.
            if remainder and len(remainder.split()) > 12:
                sections[-1][1].append(remainder)
        elif len(block.split()) >= 4:
            sections[-1][1].append(block)
    sections = [section for section in sections if section[1]]
    if len(sections) < 2:
        return []
    if not duration:
        duration = max(start + max(60.0, sum(len(block.split()) for block in values) / 2.5) for start, values in sections)
    result: list[dict[str, Any]] = []
    for index, (start, values) in enumerate(sections):
        end = sections[index + 1][0] if index + 1 < len(sections) else float(duration)
        if end <= start:
            end = start + max(1.0, sum(len(value.split()) for value in values) / 2.5)
        weights = [max(1, len(value.split())) for value in values]
        total_weight = sum(weights)
        elapsed_weight = 0
        for value, weight in zip(values, weights):
            seg_start = start + (end - start) * elapsed_weight / total_weight
            elapsed_weight += weight
            seg_end = start + (end - start) * elapsed_weight / total_weight
            result.append(
                {
                    "segment_id": f"seg-{len(result) + 1:04d}",
                    "start_seconds": round(seg_start, 3),
                    "end_seconds": round(seg_end, 3),
                    "text": value,
                    "timestamp_method": "source_section_timestamp_interpolated",
                }
            )
    return result


def transcript_from_url(url: str, transcript_type: str | None, duration: float | None) -> list[dict[str, Any]]:
    payload, content_type = fetch(url, accept="application/json,text/vtt,text/plain,text/html,*/*")
    text = payload.decode("utf-8", errors="replace")
    hint = (transcript_type or content_type or "").lower()
    if "json" in hint or url.lower().endswith(".json"):
        try:
            return parse_json_transcript(json.loads(text))
        except json.JSONDecodeError:
            return []
    cue_line = re.search(
        r"(?m)^\s*(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d+)?\s*-->\s*(?:\d+:)?\d{1,2}:\d{2}(?:[.,]\d+)?",
        text,
    )
    if "vtt" in hint or "srt" in hint or url.lower().endswith((".vtt", ".srt")) or cue_line:
        return parse_vtt_srt(text)
    plain = article_text(payload, content_type)
    timestamped = source_timestamped_sections(plain, duration)
    if timestamped:
        return timestamped
    return estimate_segments(plain, duration)


def youtube_transcript(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    # Preferred optional library path.
    match = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/)([A-Za-z0-9_-]{6,})", candidate["url"])
    video_id = match.group(1) if match else str(candidate.get("native_id") or "").split(":")[-1]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        rows = fetched.to_raw_data()
        return parse_json_transcript(rows)
    except Exception:
        pass

    executable = shutil.which("yt-dlp")
    if not executable:
        return []
    with tempfile.TemporaryDirectory(prefix="ps04-youtube-") as temp_dir:
        template = str(pathlib.Path(temp_dir) / "caption.%(ext)s")
        command = [
            executable,
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "en.*,en",
            "--sub-format",
            "vtt",
            "-o",
            template,
            candidate["url"],
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        if result.returncode != 0:
            return []
        files = sorted(pathlib.Path(temp_dir).glob("*.vtt"))
        return parse_vtt_srt(files[0].read_text(encoding="utf-8", errors="replace")) if files else []


def stored_latest(item_id: str) -> dict[str, Any] | None:
    command = ["bash", str(REPO_ROOT / "data" / "store.sh"), "get", item_id]
    result = subprocess.run(command, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def can_reuse(candidate: dict[str, Any], stored: dict[str, Any]) -> bool:
    if candidate.get("force_refresh") is True:
        return False
    return stored.get("extraction", {}).get("extractor_version") == EXTRACTOR_VERSION \
        and all(candidate.get(field) == stored.get(field) for field in ("item_id", "title", "url", "published_at")) \
        and pathlib.Path(REPO_ROOT / str(stored.get("text_path", ""))).is_file() \
        and (stored.get("segments_path") is None or pathlib.Path(REPO_ROOT / str(stored["segments_path"])).is_file())


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return (cleaned or hashlib.sha256(value.encode()).hexdigest()[:16])[:100]


def extract(candidate: dict[str, Any]) -> tuple[dict[str, Any], str]:
    require_fields(candidate, CANDIDATE_FIELDS, record_name="candidate")
    if candidate["kind"] not in {"feed", "youtube", "podcast"}:
        raise PipelineInputError(f"candidate {candidate['item_id']} has invalid kind")

    prior = stored_latest(str(candidate["item_id"]))
    if prior and can_reuse(candidate, prior):
        reused = dict(prior)
        reused["retrieved_at"] = candidate["retrieved_at"]
        reused["source_id"] = candidate["source_id"]
        return reused, "store-cache"

    text_value = ""
    segments: list[dict[str, Any]] | None = None
    if candidate["kind"] == "feed":
        try:
            payload, content_type = fetch(candidate["url"], accept="text/html,text/plain,text/markdown,*/*")
            text_value = article_text(payload, content_type)
        except (OSError, urllib.error.URLError):
            summary = candidate.get("summary_html")
            if summary:
                text_value = article_text(str(summary).encode("utf-8"), "text/html")
        if len(text_value.split()) < int(candidate.get("minimum_words", 100)):
            raise PipelineInputError(f"written item {candidate['item_id']} has no substantive retrievable text")
    else:
        transcript_url = candidate.get("transcript_url")
        if transcript_url:
            segments = transcript_from_url(
                str(transcript_url),
                candidate.get("transcript_type"),
                duration_seconds(candidate.get("duration_seconds")),
            )
        elif isinstance(candidate.get("segments"), list):
            segments = parse_json_transcript(candidate["segments"])
        elif candidate["kind"] == "youtube":
            segments = youtube_transcript(candidate)
        else:
            segments = []
        if not segments:
            raise PipelineInputError(f"media item {candidate['item_id']} has no timestamped transcript")
        text_value = "\n".join(segment["text"] for segment in segments)

    material = {
        "title": candidate["title"],
        "url": candidate["url"],
        "published_at": candidate["published_at"],
        "extracted_text": text_value,
        "segments": segments,
    }
    version_id = "v-" + sha256_json(material)[:24]
    item_root = REPO_ROOT / "data" / "assets" / safe_name(str(candidate["item_id"]))
    item_root.mkdir(parents=True, exist_ok=True)
    text_path = item_root / f"{version_id}.txt"
    if not text_path.exists():
        text_path.write_text(text_value.rstrip() + "\n", encoding="utf-8")
    segments_path: pathlib.Path | None = None
    if segments is not None:
        segments_path = item_root / f"{version_id}.segments.json"
        if not segments_path.exists():
            write_json(segments_path, segments)

    item = dict(candidate)
    item.update(
        {
            "version_id": version_id,
            "text_path": repo_relative(text_path),
            "segments_path": repo_relative(segments_path) if segments_path else None,
            "extraction": {
                "extractor_version": EXTRACTOR_VERSION,
                "extracted_at": utc_now(),
                "text_word_count": len(text_value.split()),
                "segment_count": len(segments or []),
            },
        }
    )
    return item, "network-or-inline"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    try:
        run_dir = require_run_dir(args.run_dir)
        candidates = list(iter_jsonl(sys.stdin, source="stdin"))
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        cache_hits = 0
        for candidate in candidates:
            try:
                item, method = extract(candidate)
                cache_hits += int(method == "store-cache")
                items.append(item)
            except (PipelineInputError, OSError, urllib.error.URLError, subprocess.SubprocessError) as exc:
                errors.append(f"{candidate.get('item_id', '<unknown>')}: {exc}")
        for item in items:
            print(compact_json(item))
        receipt(
            run_dir,
            stage="extract_content",
            status="incomplete" if errors else "completed",
            started_at=started_at,
            input_count=len(candidates),
            output_count=len(items),
            tools_or_models=["python-urllib", "html-parser", "youtube-transcript-api-or-yt-dlp"],
            errors=errors,
            details={"cache_hits": cache_hits, "failed_item_count": len(errors)},
        )
        for error in errors:
            print(f"extract_content: {error}", file=sys.stderr)
        return 1 if errors else 0
    except PipelineInputError as exc:
        print(f"extract_content: {exc}", file=sys.stderr)
        try:
            run_dir = require_run_dir(args.run_dir)
            receipt(
                run_dir,
                stage="extract_content",
                status="failed",
                started_at=started_at,
                input_count=None,
                output_count=None,
                tools_or_models=["python-urllib", "html-parser"],
                errors=[str(exc)],
            )
        except PipelineInputError:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
