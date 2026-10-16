#!/usr/bin/env python3
"""Render the four PS04 videos with local synthetic narration.

The renderer intentionally uses only saved, reviewed repository artifacts.  It
does not rewrite editorial content.  The local macOS speech synthesizer
produces the narration; Pillow and a bundled ffmpeg binary produce the video,
captions, thumbnails, checksums, and duration manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "final_media"
WORK = OUT / "work"
FFMPEG = Path(imageio_ffmpeg.get_ffmpeg_exe())

WIDTH, HEIGHT = 1920, 1080
INK = "#F6F3EA"
MUTED = "#A9B8C6"
NAVY = "#07131F"
PANEL = "#102433"
PANEL_2 = "#173246"
TEAL = "#59D3C2"
AMBER = "#F4B860"
CORAL = "#FF8066"
BLUE = "#78A9FF"

FONT_REGULAR = "/System/Library/Fonts/SFNS.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_MONO = "/System/Library/Fonts/SFNSMono.ttf"


@dataclass(frozen=True)
class SceneSpec:
    title: str
    chips: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class VideoSpec:
    slug: str
    label: str
    script: Path
    scenes: tuple[SceneSpec, ...]


def s(title: str, chips: list[str], source: str) -> SceneSpec:
    return SceneSpec(title, tuple(chips), source)


VIDEOS = (
    VideoSpec(
        "01-agent-moved-past-diff",
        "AUDIENCE VIDEO 1",
        ROOT / "outputs/production_package/video_scripts/01.md",
        (
            s("A workflow, not a magic patch", ["Plan", "Isolate", "Review", "Approve"], "CONTROL PLANE"),
            s("Repository-scale change", ["Indexed codebase", "Pilot repository", "Human merge"], "SOURCEGRAPH"),
            s("Monitoring before deployment", ["Read the diff", "Draft a plan", "Human edits"], "CURSOR"),
            s("Security review in context", ["Every pull request", "Explain finding", "Propose a fix"], "CURSOR"),
            s("Automatic is not validated", ["Repository access", "Automatic start", "Human judgment"], "OPENAI"),
            s("Parallel, isolated execution", ["Project A", "Project B", "Separate worktree"], "OPENAI"),
            s("Workflow reach ≠ safe autonomy", ["Review", "Security", "Deployment", "Recovery"], "MULTI-SOURCE INFERENCE"),
            s("Test what survives delivery", ["25 tasks", "Freeze delivery", "Held-out cases"], "AGENTSWE"),
            s("Visible success can collapse", ["Development ≥ 90", "Held-out average 9.9"], "AGENTSWE"),
            s("The defensible claim", ["Supervised", "Inspectable", "Approval-gated"], "EVIDENCE SYNTHESIS"),
            s("What the evidence cannot tell us", ["No tool ranking", "Missing outcomes", "Narrow benchmark"], "LIMITATIONS"),
            s("Start bounded; keep the gate", ["One task class", "CI evidence", "Human merge", "Measure outcomes"], "ACTION FOR SMALL TEAMS"),
        ),
    ),
    VideoSpec(
        "02-production-ready-measurement",
        "AUDIENCE VIDEO 2",
        ROOT / "outputs/production_package/video_scripts/02.md",
        (
            s("Production-ready is a tuple", ["Task", "Harness", "Acceptance", "Supervision"], "MEASUREMENT FRAME"),
            s("Inspect the experiment", ["Tokens", "Cost", "Latency", "Tool errors"], "CURSOR"),
            s("Seven percent—with boundaries", ["User token cost", "Vendor-reported quality"], "CURSOR"),
            s("The denominator matters", ["46.9% reduction", "MCP-tool sessions only"], "CURSOR"),
            s("Isolation has a coordination tax", ["Duplicate work", "Stale tasks", "Hidden context"], "CURSOR"),
            s("Activity is not effectiveness", ["Nearly 1,000 changesets", "Human review", "Human merge"], "SOURCEGRAPH"),
            s("A stricter acceptance surface", ["25 tasks", "Frozen delivery", "Hard validity gate"], "AGENTSWE"),
            s("Held-out delivery scores", ["Creation: 19.1", "Editing: 31.6"], "AGENTSWE"),
            s("Completion claims can mislead", ["Visible-case overfit", "Hollow runtime", "Contradictory records"], "AGENTSWE"),
            s("Test integrity failure", ["Asked: fix test", "Observed: test deleted", "Response: add guidance"], "INFOQ / JOY EBERTZ"),
            s("Architecture drifts over time", ["Features shipped", "God object grew", "Multi-week horizon"], "INFOQ / SCOTT HANSELMAN"),
            s("Different layers can diverge", ["Resource use", "Activity", "Delivery fidelity", "Maintainability"], "EVIDENCE SYNTHESIS"),
            s("No shared head-to-head", ["Different tasks", "Different supervision", "Different outcomes"], "LIMITATIONS"),
            s("Name the exact readiness claim", ["Task + harness", "Acceptance threshold", "Human gates"], "ACTION FOR SMALL TEAMS"),
        ),
    ),
    VideoSpec(
        "03-earn-the-next-rung",
        "AUDIENCE VIDEO 3",
        ROOT / "outputs/production_package/video_scripts/03.md",
        (
            s("Authority must be earned", ["Plan", "Implement", "Review", "Deploy", "Recover"], "ADOPTION LADDER"),
            s("Delegation reshapes supervision", ["Plan", "Monitor", "Review", "Teach", "Manual fix"], "INDEPENDENT STUDY"),
            s("Three supervision strategies", ["Front-load planning", "Delegate checks", "Version guidance"], "INDEPENDENT STUDY"),
            s("Move the checkpoint upstream", ["Proposed plan", "Assumptions", "Clarifying questions"], "PRACTITIONER + DEMO"),
            s("Make corrections reusable", ["Repository guidance", "Separate review", "Original specification"], "OPERATING PRACTICE"),
            s("Pilot one low-risk task class", ["Plan", "Isolated work", "Held-out checks", "Human merge"], "CONTROLLED PILOT"),
            s("Keep acceptance out of reach", ["Frozen tests", "Independent evaluation", "No test deletion"], "SAFETY BOUNDARY"),
            s("Advisory before autonomous", ["Recommend", "Pause", "Approve", "Reject"], "SECURITY + DEPLOYMENT"),
            s("Keep two scorecards", ["Operating cost", "Accepted outcomes", "Supervision load"], "MEASUREMENT"),
            s("Test the training effect", ["Senior preceptor", "Time-boxed trial", "Measure learning"], "TEAM DEVELOPMENT"),
            s("Advance one rung at a time", ["Predeclare thresholds", "Watch drift", "Reduce permissions"], "ADOPTION LADDER"),
            s("A protocol to test", ["25 tasks", "19 developers", "Anecdotes", "Vendor reports"], "LIMITATIONS"),
            s("Advance, hold, or step back", ["Acceptance", "Safety", "Maintainability", "Total cost"], "DECISION"),
        ),
    ),
    VideoSpec(
        "04-technical-demonstration",
        "TECHNICAL DEMONSTRATION",
        ROOT / "docs/DEMO_SCRIPT.md",
        (
            s("Purpose and system boundary", ["config/project.json", "run.sh", "AI is bounded"], "REPOSITORY VIEW"),
            s("The implemented pipeline", ["3 collectors", "30-date filter", "Coverage gate", "Approval gate"], "ARCHITECTURE"),
            s("Trace one claim end to end", ["claim:02-c9", "v-fa6a1…", "seg-0060 → 0063"], "docs/CLAIM_TRACE.md"),
            s("Immutable evidence, one store interface", ["data/assets/…", "data/store.sh", "JSON Lines"], "EVIDENCE STORE"),
            s("Two live days, real updates", ["10 new", "5 changed", "12 unchanged", "2 window exclusions"], "RUN SUMMARIES"),
            s("Failures remain visible", ["TLS repair", "YouTube fallback", "Rejected pairing", "Targeted rerun"], "docs/RECOVERY_LOG.md"),
            s("Policy revision is operational", ["Availability ≠ readiness", "Keep denominators", "Defer opaque numbers"], "POLICY v1 → v2"),
            s("Human judgment is a hard gate", ["review fingerprint", "approval.json", "immutable package"], "APPROVAL HANDOFF"),
            s("Why local storage wins here", ["Exact provenance", "Simple replay", "Credential-free", "12–30 items/run"], "ARCHITECTURE TRADEOFF"),
            s("Four rendered deliverables", ["3 article/video pairs", "1 technical demo", "Shareable URLs"], "PRODUCTION OUTPUTS"),
            s("The result and its limits", ["Bounded task", "Acceptance test", "Supervision regime", "No vendor ranking"], "CENTRAL RESULT"),
        ),
    ),
)


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_MONO if mono else FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(path, size=size)


def parse_script(path: Path) -> tuple[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^#\s+(.+)$", text, re.M)
    if not match:
        raise ValueError(f"Missing title in {path}")
    title = match.group(1).strip()
    narrations = [
        re.sub(r"\s+", " ", chunk).strip()
        for chunk in re.findall(
            r"\*\*NARRATION:\*\*\s*(.*?)(?=\n\n|\n\[|\n<!--|\Z)",
            text,
            flags=re.S,
        )
    ]
    if not narrations:
        raise ValueError(f"No narration blocks in {path}")
    return title, narrations


def fit_lines(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def compact_takeaway(text: str, max_words: int = 42) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picked: list[str] = []
    count = 0
    for sentence in sentences:
        words = sentence.split()
        if picked and count + len(words) > max_words:
            break
        picked.append(sentence)
        count += len(words)
        if count >= 24:
            break
    result = " ".join(picked).strip()
    if len(result.split()) > max_words:
        result = " ".join(result.split()[:max_words]).rstrip(".,;:") + "…"
    return result


def gradient_background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    start = (7, 19, 31)
    end = (14, 43, 58)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(start, end))
        draw.line((0, y, WIDTH, y), fill=color)
    return image


def draw_slide(
    video_title: str,
    label: str,
    scene: SceneSpec,
    narration: str,
    index: int,
    total: int,
) -> Image.Image:
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    # Brand rail and progress.
    draw.rounded_rectangle((72, 58, 386, 112), radius=24, fill=TEAL)
    draw.text((100, 70), "AGENT SIGNAL", font=font(28, bold=True), fill=NAVY)
    draw.text((420, 72), label, font=font(25, bold=True), fill=MUTED)
    counter = f"{index:02d} / {total:02d}"
    counter_w = draw.textbbox((0, 0), counter, font=font(25, mono=True))[2]
    draw.text((1848 - counter_w, 72), counter, font=font(25, mono=True), fill=MUTED)
    draw.rounded_rectangle((72, 135, 1848, 143), radius=4, fill="#274255")
    draw.rounded_rectangle((72, 135, 72 + int(1776 * index / total), 143), radius=4, fill=TEAL)

    # Title area.
    title_font = font(68, bold=True)
    title_lines = fit_lines(draw, scene.title, title_font, 1030)
    y = 210
    for line in title_lines[:2]:
        draw.text((110, y), line, font=title_font, fill=INK)
        y += 80

    # Takeaway panel.
    top = max(400, y + 34)
    draw.rounded_rectangle((96, top, 1120, 874), radius=30, fill=PANEL, outline="#28475C", width=2)
    draw.text((142, top + 40), "KEY TAKEAWAY", font=font(24, bold=True), fill=TEAL)
    takeaway = compact_takeaway(narration)
    body_font = font(42)
    body_lines = fit_lines(draw, takeaway, body_font, 920)
    body_y = top + 96
    for line in body_lines[:7]:
        draw.text((142, body_y), line, font=body_font, fill=INK)
        body_y += 58

    # Evidence / diagram panel.
    draw.rounded_rectangle((1170, 210, 1824, 874), radius=30, fill=PANEL_2, outline="#31546C", width=2)
    draw.text((1212, 252), scene.source, font=font(24, bold=True), fill=AMBER)
    chip_top = 324
    chip_colors = (TEAL, BLUE, AMBER, CORAL)
    for chip_index, chip in enumerate(scene.chips):
        color = chip_colors[chip_index % len(chip_colors)]
        bottom = chip_top + 94
        draw.rounded_rectangle((1212, chip_top, 1782, bottom), radius=22, fill="#0D1D29", outline=color, width=3)
        chip_font = font(31, bold=True)
        lines = fit_lines(draw, chip, chip_font, 500)
        text_y = chip_top + (94 - 38 * min(2, len(lines))) / 2
        for line in lines[:2]:
            draw.text((1244, text_y), line, font=chip_font, fill=INK)
            text_y += 38
        chip_top = bottom + 24

    # Footer.
    draw.text((96, 946), video_title, font=font(28, bold=True), fill=INK)
    disclosure = "SYNTHETIC NARRATION • AI-ASSISTED RESEARCH, DRAFTING & PRESENTATION • HUMAN-APPROVED RECOMMENDATIONS"
    draw.text((96, 1002), disclosure, font=font(20, bold=True), fill=MUTED)
    return image


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def quote_concat(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def caption_chunks(text: str, target_words: int = 9) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    for start in range(0, len(words), target_words):
        chunks.append(" ".join(words[start : start + target_words]))
    return chunks


def write_srt(narrations: list[str], durations: list[float], path: Path) -> None:
    entries: list[str] = []
    cursor = 0.0
    number = 1
    for narration, duration in zip(narrations, durations):
        chunks = caption_chunks(narration)
        weights = [max(1, len(chunk.split())) for chunk in chunks]
        available = max(0.1, duration - 0.35)
        offset = 0.0
        for chunk, weight in zip(chunks, weights):
            chunk_duration = available * weight / sum(weights)
            start = cursor + offset
            end = min(cursor + available, start + chunk_duration)
            entries.extend([str(number), f"{srt_time(start)} --> {srt_time(end)}", chunk, ""])
            number += 1
            offset += chunk_duration
        cursor += duration
    path.write_text("\n".join(entries), encoding="utf-8")


def render_video(spec: VideoSpec, voice: str, rate: int, force: bool) -> dict[str, object]:
    video_title, narrations = parse_script(spec.script)
    if len(narrations) != len(spec.scenes):
        raise ValueError(
            f"{spec.slug}: {len(narrations)} narration blocks but {len(spec.scenes)} scene specs"
        )

    job = WORK / spec.slug
    if force and job.exists():
        shutil.rmtree(job)
    job.mkdir(parents=True, exist_ok=True)

    slide_paths: list[Path] = []
    wav_paths: list[Path] = []
    durations: list[float] = []
    total = len(narrations)

    for index, (scene, narration) in enumerate(zip(spec.scenes, narrations), start=1):
        slide = job / f"slide-{index:02d}.png"
        raw_audio = job / f"speech-{index:02d}.aiff"
        padded_audio = job / f"speech-{index:02d}.wav"

        if force or not slide.exists():
            draw_slide(video_title, spec.label, scene, narration, index, total).save(slide)
        if force or not padded_audio.exists():
            run(["/usr/bin/say", "-v", voice, "-r", str(rate), "-o", str(raw_audio), narration])
            if raw_audio.stat().st_size < 5_000:
                raise RuntimeError(f"TTS produced an invalid audio file: {raw_audio}")
            run(
                [
                    str(FFMPEG),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(raw_audio),
                    "-af",
                    "apad=pad_dur=0.35",
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(padded_audio),
                ]
            )
        slide_paths.append(slide)
        wav_paths.append(padded_audio)
        duration = wav_duration(padded_audio)
        minimum_plausible = max(2.0, len(narration.split()) / 260 * 60)
        if duration < minimum_plausible:
            raise RuntimeError(
                f"Implausibly short narration ({duration:.2f}s) for {len(narration.split())} words: {padded_audio}"
            )
        durations.append(duration)

    audio_list = job / "audio-concat.txt"
    audio_list.write_text(
        "\n".join(f"file '{quote_concat(path)}'" for path in wav_paths) + "\n",
        encoding="utf-8",
    )
    narration_wav = job / "narration.wav"
    run(
        [
            str(FFMPEG),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_list),
            "-c:a",
            "pcm_s16le",
            str(narration_wav),
        ]
    )

    visual_list = job / "visual-concat.txt"
    visual_lines: list[str] = []
    for slide, duration in zip(slide_paths, durations):
        visual_lines.extend([f"file '{quote_concat(slide)}'", f"duration {duration:.6f}"])
    visual_lines.append(f"file '{quote_concat(slide_paths[-1])}'")
    visual_list.write_text("\n".join(visual_lines) + "\n", encoding="utf-8")

    OUT.mkdir(parents=True, exist_ok=True)
    video_path = OUT / f"{spec.slug}.mp4"
    captions_path = OUT / f"{spec.slug}.srt"
    thumbnail_path = OUT / f"{spec.slug}-thumbnail.png"
    write_srt(narrations, durations, captions_path)
    shutil.copy2(slide_paths[0], thumbnail_path)

    run(
        [
            str(FFMPEG),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(visual_list),
            "-i",
            str(narration_wav),
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-tune",
            "stillimage",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            "-t",
            f"{sum(durations):.3f}",
            "-shortest",
            str(video_path),
        ]
    )

    digest = hashlib.sha256(video_path.read_bytes()).hexdigest()
    return {
        "slug": spec.slug,
        "title": video_title,
        "label": spec.label,
        "script": str(spec.script.relative_to(ROOT)),
        "video": str(video_path.relative_to(ROOT)),
        "captions": str(captions_path.relative_to(ROOT)),
        "thumbnail": str(thumbnail_path.relative_to(ROOT)),
        "duration_seconds": round(sum(durations), 3),
        "scene_count": total,
        "voice": voice,
        "rate_words_per_minute": rate,
        "bytes": video_path.stat().st_size,
        "sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="Samantha")
    parser.add_argument("--rate", type=int, default=155)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--only", choices=[video.slug for video in VIDEOS])
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    chosen = [video for video in VIDEOS if not args.only or video.slug == args.only]
    records = [render_video(video, args.voice, args.rate, args.force) for video in chosen]

    manifest_path = OUT / "media_manifest.json"
    existing: dict[str, dict[str, object]] = {}
    if manifest_path.exists() and not args.force:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing = {record["slug"]: record for record in payload.get("videos", [])}
    for record in records:
        existing[str(record["slug"])] = record
    manifest = {
        "narration_disclosure": "Local synthetic text-to-speech narration; no cloned voice.",
        "production_disclosure": "AI assisted research, drafting, and presentation. A human editor approved the reviewed recommendations.",
        "videos": [existing[key] for key in sorted(existing)],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
