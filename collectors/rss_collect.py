#!/usr/bin/env python3
"""Discover feed, YouTube Atom, and podcast RSS candidates.

The collectors intentionally share protocol parsing while retaining three
separate Bash entry points and independently filtered source configurations.
This file owns discovery only; substantive retrieval belongs to processing.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from pipeline_common import (
    PipelineInputError,
    compact_json,
    load_json,
    receipt,
    require_run_dir,
    utc_now,
)


USER_AGENT = "MIT-1.125-PS04-Intelligence-Pipeline/1.0 (+coursework; evidence collection)"


def tls_context() -> ssl.SSLContext:
    """Use the maintained CA bundle installed with the project environment.

    The system Python on some macOS installations does not inherit the OS
    keychain correctly.  Certifi keeps verification enabled while making live
    collection reproducible across those machines.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


TLS_CONTEXT = tls_context()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: set[str]) -> str | None:
    for child in list(node):
        if local_name(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_bytes(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
    )
    with urllib.request.urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
        return response.read()


def candidate_id(kind: str, publisher_id: str, native_id: str, url: str) -> str:
    if kind == "youtube":
        match = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/)([A-Za-z0-9_-]{6,})", url)
        video_id = match.group(1) if match else native_id
        safe = re.sub(r"[^A-Za-z0-9_-]", "", video_id)
        if safe:
            return f"youtube:{safe}"
    digest = hashlib.sha256(f"{publisher_id}\0{native_id or url}".encode("utf-8")).hexdigest()[:20]
    return f"{kind}:{publisher_id}:{digest}"


def atom_link(node: ET.Element) -> str | None:
    links = [child for child in list(node) if local_name(child.tag) == "link"]
    for link in links:
        if link.attrib.get("rel", "alternate") == "alternate" and link.attrib.get("href"):
            return link.attrib["href"].strip()
    for link in links:
        if link.attrib.get("href"):
            return link.attrib["href"].strip()
        if link.text and link.text.strip():
            return link.text.strip()
    return None


def enclosure(node: ET.Element) -> str | None:
    for child in node.iter():
        name = local_name(child.tag)
        if name == "enclosure" and child.attrib.get("url"):
            return child.attrib["url"].strip()
        if name == "content" and child.attrib.get("url") and child.attrib.get("type", "").startswith("audio/"):
            return child.attrib["url"].strip()
    return None


def transcript(node: ET.Element) -> tuple[str | None, str | None]:
    for child in node.iter():
        if local_name(child.tag) == "transcript" and child.attrib.get("url"):
            return child.attrib["url"].strip(), child.attrib.get("type")
    return None, None


def configured_transcript(source: dict[str, Any], title: str, url: str) -> dict[str, Any] | None:
    """Return a documented transcript override for a discovered feed item.

    Some long-running podcast feeds expose audio enclosures but keep their
    official transcript on the publisher's episode page rather than in the
    Podcasting 2.0 transcript element.  Matching remains discovery-driven:
    an override is applied only after the item appears in the live feed.
    """
    overrides = source.get("transcript_overrides")
    if not isinstance(overrides, list):
        return None
    for override in overrides:
        if not isinstance(override, dict):
            continue
        title_contains = str(override.get("title_contains") or "").casefold()
        url_contains = str(override.get("url_contains") or "").casefold()
        if title_contains and title_contains not in title.casefold():
            continue
        if url_contains and url_contains not in url.casefold():
            continue
        if title_contains or url_contains:
            return override
    return None


def direct_candidate(source: dict[str, Any], item: dict[str, Any], kind: str, retrieved_at: str) -> dict[str, Any]:
    url = str(item.get("url") or source["url"])
    native_id = str(item.get("native_id") or item.get("guid") or url)
    media_url = item.get("media_url")
    if kind == "youtube" and media_url is None:
        media_url = url
    return {
        "item_id": str(item.get("item_id") or candidate_id(kind, source["publisher_id"], native_id, url)),
        "source_id": source["source_id"],
        "publisher_id": source["publisher_id"],
        "kind": kind,
        "title": str(item.get("title") or source.get("title") or url),
        "url": url,
        "published_at": parse_date(item.get("published_at")),
        "retrieved_at": retrieved_at,
        "media_url": media_url,
        "native_id": native_id,
        "discovery_url": source["url"],
        "summary_html": item.get("summary_html"),
        "transcript_url": item.get("transcript_url"),
        "transcript_type": item.get("transcript_type"),
        "duration_seconds": item.get("duration_seconds"),
    }


def parse_source(source: dict[str, Any], kind: str, retrieved_at: str) -> list[dict[str, Any]]:
    if isinstance(source.get("items"), list):
        return [direct_candidate(source, item, kind, retrieved_at) for item in source["items"] if isinstance(item, dict)]
    if source.get("direct") is True:
        return [direct_candidate(source, source, kind, retrieved_at)]

    payload = fetch_bytes(source["url"], float(source.get("timeout_seconds", 30)))
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise PipelineInputError(f"invalid XML from {source['source_id']}: {exc}") from exc

    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    limit = int(source.get("max_items", 25))
    records: list[dict[str, Any]] = []
    for node in entries[: max(0, limit)]:
        title = child_text(node, {"title"}) or "Untitled"
        include_terms = [str(value).casefold() for value in source.get("include_title_contains", [])]
        exclude_terms = [str(value).casefold() for value in source.get("exclude_title_contains", [])]
        title_folded = title.casefold()
        if include_terms and not any(term in title_folded for term in include_terms):
            continue
        if exclude_terms and any(term in title_folded for term in exclude_terms):
            continue
        url = atom_link(node) or child_text(node, {"link"})
        native_id = child_text(node, {"videoid", "guid", "id"}) or url
        if not url:
            continue
        published = child_text(node, {"published", "pubdate", "date", "updated"})
        content = child_text(node, {"encoded", "description", "summary", "content"})
        media_url = enclosure(node)
        if kind == "youtube" and not media_url:
            media_url = url
        transcript_url, transcript_type = transcript(node)
        duration = child_text(node, {"duration"})
        override = configured_transcript(source, title, url)
        if override:
            transcript_url = override.get("url") or transcript_url
            transcript_type = override.get("type") or transcript_type
            duration = override.get("duration_seconds") or duration
            if override.get("canonical_url"):
                url = str(override["canonical_url"])
        record: dict[str, Any] = {
            "item_id": candidate_id(kind, source["publisher_id"], native_id or url, url),
            "source_id": source["source_id"],
            "publisher_id": source["publisher_id"],
            "kind": kind,
            "title": html.unescape(re.sub(r"<[^>]+>", " ", title)).strip(),
            "url": url,
            "published_at": parse_date(published),
            "retrieved_at": retrieved_at,
            "media_url": media_url,
            "native_id": native_id,
            "discovery_url": source["url"],
            "summary_html": content,
            "transcript_url": transcript_url,
            "transcript_type": transcript_type,
            "duration_seconds": duration,
        }
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("feed", "youtube", "podcast"))
    parser.add_argument("run_dir")
    args = parser.parse_args()
    started_at = utc_now()
    try:
        run_dir = require_run_dir(args.run_dir)
        config = load_json(run_dir / "config" / "sources.json")
        if not isinstance(config, list):
            raise PipelineInputError("snapshotted sources.json must be an array")
        sources = [row for row in config if isinstance(row, dict) and row.get("kind") == args.kind]
        errors: list[str] = []
        records: list[dict[str, Any]] = []
        retrieved_at = utc_now()
        for source in sources:
            try:
                records.extend(parse_source(source, args.kind, retrieved_at))
            except (PipelineInputError, OSError, urllib.error.URLError, ValueError) as exc:
                errors.append(f"{source.get('source_id', '<unknown>')}: {exc}")
        # Deterministic order and one observation per source/item combination.
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for record in sorted(records, key=lambda row: (row["source_id"], row["item_id"], row.get("published_at") or "")):
            key = (record["source_id"], record["item_id"])
            if key not in seen:
                seen.add(key)
                unique.append(record)
        for record in unique:
            print(compact_json(record))
        receipt(
            run_dir,
            stage=f"fetch_{args.kind}",
            status="incomplete" if errors else "completed",
            started_at=started_at,
            input_count=len(sources),
            output_count=len(unique),
            tools_or_models=["python-urllib", "python-elementtree"],
            errors=errors,
            details={"failed_source_count": len(errors)},
        )
        return 1 if errors else 0
    except PipelineInputError as exc:
        print(f"fetch_{args.kind}: {exc}", file=sys.stderr)
        # A malformed RUN_DIR may make a receipt impossible.
        try:
            run_dir = require_run_dir(args.run_dir)
            receipt(
                run_dir,
                stage=f"fetch_{args.kind}",
                status="failed",
                started_at=started_at,
                input_count=None,
                output_count=None,
                tools_or_models=["python-urllib", "python-elementtree"],
                errors=[str(exc)],
            )
        except PipelineInputError:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
