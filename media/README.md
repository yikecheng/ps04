# Video production

The course's text-to-speech alternative is used for all four final videos. The
three audience scripts remain the approved scripts in
`outputs/production_package/video_scripts/`; the separate technical narration
is in `docs/DEMO_SCRIPT.md`.

Generate the MP4 files, YouTube-ready captions, thumbnails, and a checksum and
duration manifest with:

```bash
.venv/bin/python media/generate_videos.py --force
```

The renderer uses the local macOS `Samantha` synthetic voice at 155 words per
minute, Pillow for 1920×1080 source cards, and the `imageio-ffmpeg` binary for
H.264/AAC encoding. It does not clone a voice, send scripts to a speech service,
or modify the approved editorial text. Generated working files live under
`outputs/final_media/work/`.

Install the small media-only dependency set with:

```bash
.venv/bin/python -m pip install -r media/requirements.txt
```

Narration generation is offline. On a headless macOS session, the local speech
synthesizer may need permission to use the native speech service.
