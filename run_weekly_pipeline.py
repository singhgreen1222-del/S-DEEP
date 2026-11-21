#!/usr/bin/env python3
"""
S DEEP (@sdeepworldwide) - End-to-End Weekly Video & Thumbnail Producer + YouTube Scheduler
==========================================================================================
1. Reads week_config.json (all 16 weekly items: 14 Shorts + 2 Long-form).
2. Generates High-CTR 1280x720 Thumbnails (bold typography, accent arrows/badges, host cutout).
3. Generates Hindi voiceover via Piper TTS (or Coqui XTTS-v2 if voice_sample.wav exists).
4. Renders multi-scene advanced MP4s (1080x1920 Shorts & 1920x1080 Long-form, 30 FPS) with charts & captions.
5. Uploads all videos to YouTube as Unlisted/Scheduled (`publishAt` IST) and writes `status_report.json`.
"""

import argparse
import json
import os
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from s_deep_auto_producer import (
    create_market_chart,
    render_scene_frame,
    assemble_video_ffmpeg,
    generate_voiceover_piper,
    find_font,
)


def create_high_ctr_thumbnail(item: dict, out_png: str, host_png: str = None) -> str:
    """Create a bold, high-contrast 1280x720 High-CTR thumbnail."""
    w, h = 1280, 720
    accent_hex = item.get("thumb_color", "#00D09C")
    accent = tuple(int(accent_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    img = Image.new("RGB", (w, h), color=(10, 14, 28))
    draw = ImageDraw.Draw(img)

    # Subtle grid lines
    for x in range(0, w, 80):
        draw.line([(x, 0), (x, h)], fill=(22, 30, 52), width=2)
    for y in range(0, h, 80):
        draw.line([(0, y), (w, y)], fill=(22, 30, 52), width=2)

    # Left vertical accent bar
    draw.rectangle([0, 0, 24, h], fill=accent)

    font_bold = find_font(bold=True)
    font_reg = find_font(bold=False)
    f_badge = ImageFont.truetype(font_bold, 34) if font_bold else ImageFont.load_default()
    f_head = ImageFont.truetype(font_bold, 76) if font_bold else ImageFont.load_default()
    f_sub = ImageFont.truetype(font_bold, 42) if font_bold else ImageFont.load_default()
    f_foot = ImageFont.truetype(font_reg, 26) if font_reg else ImageFont.load_default()

    # Top-left badge
    badge_text = item.get("thumb_badge", "MARKET UPDATE").upper()
    draw.rectangle([65, 55, 520, 125], fill=accent)
    draw.text((88, 70), badge_text[:20], fill=(10, 14, 28), font=f_badge)

    # Bold main headline
    y = 175
    for line in textwrap.wrap(item.get("thumb_headline", item["title"]), width=16)[:3]:
        draw.text((65, y), line, fill=(255, 255, 255), font=f_head)
        y += 95

    # Sub-headline
    draw.text((65, y + 25), item.get("thumb_sub", "")[:34], fill=accent, font=f_sub)

    # Footer branding
    draw.text((65, 650), "S DEEP  |  @sdeepworldwide  |  EDUCATIONAL ONLY", fill=(148, 163, 184), font=f_foot)

    # Host cutout circle on right
    cx, cy, r = 1020, 360, 210
    if host_png and os.path.exists(host_png):
        host = Image.open(host_png).convert("RGBA")
        side = min(host.size)
        left = (host.width - side) // 2
        top = (host.height - side) // 2
        host = host.crop((left, top, left + side, top + side)).resize((r * 2, r * 2), Image.Resampling.LANCZOS)
        mask = Image.new("L", (r * 2, r * 2), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, r * 2, r * 2], fill=255)
        img.paste(host, (cx - r, cy - r), mask)
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(22, 32, 58))
        draw.text((cx - 110, cy - 15), "AI HOST", fill=(148, 163, 184), font=f_badge)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=10)

    img.save(out_png)
    return out_png


def build_video_scenes(item: dict, out_dir: Path, host_png: str = None):
    is_short = item["format"] == "short"
    w, h = (1080, 1920) if is_short else (1920, 1080)
    sc_dir = out_dir / f"scenes_{item['id']}"
    sc_dir.mkdir(parents=True, exist_ok=True)

    # Split script into 3-4 dynamic visual scenes
    sentences = [s.strip() for s in item["script"].split(".") if s.strip()]
    if not sentences:
        sentences = [item["title"]]
    chunks = sentences[:4]

    chart_png = None
    if item.get("chart"):
        c = item["chart"]
        chart_png = str(sc_dir / "chart.png")
        create_market_chart(c["title"], c["labels"], c["values"], c["unit"], c["source"], chart_png, is_vertical=is_short)

    frame_paths, durations = [], []
    for idx, text in enumerate(chunks):
        fp = str(sc_dir / f"frame_{idx}.png")
        render_scene_frame(
            headline=item["thumb_headline"] if idx == 0 else item["title"][:48],
            caption=text + ".",
            out_png=fp,
            width=w,
            height=h,
            chart_png=chart_png if idx in (0, 1) else None,
            host_png=host_png if (host_png and os.path.exists(host_png)) else None,
            badge=item.get("thumb_badge", "S DEEP"),
        )
        frame_paths.append(fp)
        durations.append(4.0 if is_short else 6.0)

    wav_path = str(sc_dir / "voice.wav")
    has_voice = generate_voiceover_piper(item["script"], wav_path)

    mp4_path = str(out_dir / f"video_{item['id']}_{item['format']}.mp4")
    assemble_video_ffmpeg(frame_paths, durations, mp4_path, audio_wav=wav_path if has_voice else None, fps=30)
    return mp4_path, has_voice


def run_pipeline(config_path: str, out_dir_str: str, host_png: str = None, upload: bool = False, render_limit: int = 16):
    items = json.loads(Path(config_path).read_text(encoding="utf-8"))
    out_dir = Path(out_dir_str)
    out_dir.mkdir(parents=True, exist_ok=True)

    yt = None
    if upload and all(k in os.environ for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
        from youtube_uploader import get_youtube_service, upload_and_schedule
        yt = get_youtube_service()

    report = []
    for idx, item in enumerate(items):
        thumb_path = str(out_dir / f"thumb_{item['id']}.png")
        create_high_ctr_thumbnail(item, thumb_path, host_png=host_png)

        mp4_path = None
        has_voice = False
        status = "Thumbnail Ready | Render Queued"
        yt_url = ""

        if idx < render_limit:
            mp4_path, has_voice = build_video_scenes(item, out_dir, host_png=host_png)
            status = "Rendered (With Voice)" if has_voice else "Rendered (Captioned Visual)"

            if yt is not None:
                yt_url = upload_and_schedule(
                    yt,
                    video_path=mp4_path,
                    title=item["title"],
                    description=item["script"],
                    tags=item.get("tags", []),
                    publish_at_iso=item["publish_at"],
                    thumbnail_path=thumb_path,
                    is_short=(item["format"] == "short"),
                )
                status = "Uploaded & Scheduled (Unlisted until publishAt)"

        report.append({
            "id": item["id"],
            "day": item["day"],
            "format": item["format"],
            "title": item["title"],
            "publish_at": item["publish_at"],
            "thumbnail": os.path.basename(thumb_path),
            "video": os.path.basename(mp4_path) if mp4_path else "",
            "has_voice": has_voice,
            "status": status,
            "youtube_url": yt_url,
            "script": item["script"],
        })

    report_path = out_dir / "status_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Pipeline complete: {len(report)} items -> {report_path}")
    return str(report_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="week_config.json")
    parser.add_argument("--out", default="weekly_build")
    parser.add_argument("--host", default="host_face.png")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--limit", type=int, default=16)
    args = parser.parse_args()
    run_pipeline(args.config, args.out, host_png=args.host, upload=args.upload, render_limit=args.limit)
