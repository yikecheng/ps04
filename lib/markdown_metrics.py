"""Markdown-aware length metrics shared by generators and review."""

from __future__ import annotations

import re


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", value))


def spoken_word_count(markdown: str) -> int:
    """Count only explicitly labeled narration blocks when they are present."""
    lines = markdown.splitlines()
    narration: list[str] = []
    active = False
    found_label = False
    for line in lines:
        stripped = line.strip()
        if stripped.casefold() == "**narration**":
            active = True
            found_label = True
            continue
        if active and (
            stripped.startswith("## ")
            or stripped.casefold().startswith("**visual direction")
            or stripped.casefold().startswith("**source notes")
        ):
            active = False
        if active:
            narration.append(line)
    if found_label:
        body = "\n".join(narration)
    else:
        body = markdown.split("## Sources", 1)[0]
        body = re.sub(r"^\s*\[[^\]]*(?:VISUAL|ON SCREEN|B-ROLL)[^\]]*\].*$", " ", body, flags=re.I | re.M)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return word_count(body)
