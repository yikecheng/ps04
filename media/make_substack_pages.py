#!/usr/bin/env python3
"""Create local rich-text import pages for the three reviewed Substack posts."""

from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "substack_import"

POSTS = (
    (
        "01",
        "The Agent Moved Past the Diff, Not Past the Gate",
        "Coding agents now reach across review, security, repository-scale change, and deployment. The control plane—not autonomous acceptance—is the mature layer.",
        "https://youtu.be/Z2KrAwjo1DY",
    ),
    (
        "02",
        "Production-Ready Is a Measurement Claim",
        "A tool is ready only for a bounded task, harness, acceptance test, and supervision regime.",
        "https://youtu.be/U6wtQDe2PJ8",
    ),
    (
        "03",
        "Earn the Next Rung",
        "A reversible adoption ladder for small teams that keeps acceptance outside the agent's control.",
        "https://youtu.be/5j9XWXjS47A",
    ),
)


def inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def markdown_body(path: Path, video_url: str, title: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[str] = []
    in_list = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("<!--"):
            if in_list:
                blocks.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            if in_list:
                blocks.append("</ul>")
                in_list = False
            blocks.append(f"<h2>{inline(line[3:])}</h2>")
            continue
        if line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{inline(line[2:])}</li>")
            continue
        if in_list:
            blocks.append("</ul>")
            in_list = False
        blocks.append(f"<p>{inline(line)}</p>")
        if "Disclosure:" in line:
            blocks.append(
                '<div class="video-link"><strong>Watch the companion video</strong><br>'
                f'<a href="{video_url}">{html.escape(title)} on YouTube</a></div>'
            )
    if in_list:
        blocks.append("</ul>")
    return "\n".join(blocks)


def page(piece: str, title: str, subtitle: str, video_url: str) -> str:
    source = ROOT / "outputs" / "production_package" / "articles" / f"{piece}.md"
    body = markdown_body(source, video_url, title)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ background:#f4f1e8; margin:0; font:20px/1.58 Georgia,serif; color:#18242d; }}
main {{ max-width:760px; margin:40px auto; background:white; padding:56px 72px; box-shadow:0 8px 30px #0002; }}
h2 {{ font:700 30px/1.2 Arial,sans-serif; margin-top:42px; }}
a {{ color:#167d73; }}
.video-link {{ border-left:5px solid #3dbdac; background:#edf9f6; padding:18px 22px; margin:28px 0; font-family:Arial,sans-serif; }}
.copy-note {{ font:14px Arial,sans-serif; color:#63717a; margin-bottom:30px; }}
</style></head><body><main>
<div class="copy-note">Click inside the article, press ⌘A, then ⌘C. Title and subtitle are entered separately.</div>
<article id="copy" contenteditable="true">{body}</article>
</main></body></html>"""


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for piece, title, subtitle, video_url in POSTS:
        target = OUTPUT / f"{piece}.html"
        target.write_text(page(piece, title, subtitle, video_url), encoding="utf-8")
        manifest.append(
            {"piece_id": piece, "title": title, "subtitle": subtitle, "video_url": video_url, "file": target.name}
        )
    import json

    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

