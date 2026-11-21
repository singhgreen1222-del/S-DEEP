#!/usr/bin/env python3
"""
S DEEP (@sdeepworldwide) - 100% Free & Automated Video Production Pipeline
=========================================================================
- Free & Open-Source Only: Piper TTS (MIT License, commercial use allowed) + FFmpeg + Matplotlib + Pillow
- Zero paid APIs, zero paid credits.
- Supports:
  * YouTube Shorts: 1080x1920 (9:16), 30 FPS, MP4
  * Long-form Videos: 1920x1080 (16:9), 30 FPS, MP4
- Works on Linux, GitHub Actions (free tier), Google Colab (free), or Android (Termux).

Setup (on Termux / Linux / Colab with internet):
  pip install piper-tts matplotlib pillow numpy
  # Download free Hindi Piper model (MIT/open-source):
  # python3 -m piper.download_voices hi_IN-pratham-medium
"""

import argparse
import json
import os
import subprocess
import textwrap
from pathlib import Path
from typing import List, Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont


CHANNEL_NAME = "S DEEP"
CHANNEL_HANDLE = "@sdeepworldwide"
DISCLAIMER_TEXT = "Educational purpose only. Not SEBI-registered investment advice."


def find_font(bold: bool = False) -> str:
    """Locate a Devanagari/Latin compatible font on Linux/Termux."""
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def generate_voiceover_piper(text: str, out_wav: str, model: str = "hi_IN-pratham-medium") -> bool:
    """
    Generate Hindi voiceover using Piper TTS (100% free, offline, MIT license, commercial use OK).
    Returns True if successful, False if Piper is not installed/model missing.
    """
    try:
        proc = subprocess.run(
            ["piper", "--model", model, "--output_file", out_wav],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 0
    except Exception as exc:
        print(f"[Piper TTS unavailable]: {exc}")
        return False


def create_market_chart(
    title: str,
    labels: List[str],
    values: List[float],
    unit: str,
    source_note: str,
    out_png: str,
    is_vertical: bool = True,
) -> str:
    """Generate a clean dark-themed financial chart for Shorts (9:16) or Long-form (16:9)."""
    fig_size = (9, 6) if is_vertical else (12, 6.5)
    fig, ax = plt.subplots(figsize=fig_size, dpi=150)
    fig.patch.set_facecolor("#0B132B")
    ax.set_facecolor("#111C3A")

    colors = ["#00D09C" if v >= 0 else "#FF5A5F" for v in values]
    bars = ax.bar(labels, values, color=colors, width=0.55, edgecolor="#FFFFFF", linewidth=0.6)

    ax.axhline(0, color="#8A99B5", linewidth=0.9, linestyle="--")
    ax.set_title(title, color="#FFFFFF", fontsize=15, fontweight="bold", pad=16)
    ax.set_ylabel(unit, color="#CBD5E1", fontsize=11)
    ax.tick_params(colors="#E2E8F0", labelsize=10)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color("#334155")

    for bar, val in zip(bars, values):
        y_pos = bar.get_height()
        va = "bottom" if val >= 0 else "top"
        offset = max(abs(max(values, default=1)), abs(min(values, default=0))) * 0.03
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            y_pos + (offset if val >= 0 else -offset),
            f"{val:,.2f}",
            ha="center",
            va=va,
            color="#FFFFFF",
            fontsize=10,
            fontweight="bold",
        )

    fig.text(0.5, 0.015, source_note, ha="center", color="#94A3B8", fontsize=8.5)
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    plt.savefig(out_png, facecolor=fig.patch.get_facecolor())
    plt.close(fig)
    return out_png


def render_scene_frame(
    headline: str,
    caption: str,
    out_png: str,
    width: int = 1080,
    height: int = 1920,
    chart_png: Optional[str] = None,
    host_png: Optional[str] = None,
    badge: str = "MARKET UPDATE",
) -> str:
    """Compose a branded S DEEP frame with optional chart and AI Host cutout."""
    img = Image.new("RGB", (width, height), color=(11, 19, 43))
    draw = ImageDraw.Draw(img)

    # Top branding bar
    bar_h = int(height * 0.08)
    draw.rectangle([0, 0, width, bar_h], fill=(28, 37, 65))

    font_bold_path = find_font(bold=True)
    font_reg_path = find_font(bold=False)
    f_brand = ImageFont.truetype(font_bold_path, 40) if font_bold_path else ImageFont.load_default()
    f_badge = ImageFont.truetype(font_bold_path, 26) if font_bold_path else ImageFont.load_default()
    f_head = ImageFont.truetype(font_bold_path, 52 if width < height else 46) if font_bold_path else ImageFont.load_default()
    f_cap = ImageFont.truetype(font_reg_path, 38 if width < height else 34) if font_reg_path else ImageFont.load_default()
    f_disc = ImageFont.truetype(font_reg_path, 22) if font_reg_path else ImageFont.load_default()

    draw.text((40, int(bar_h * 0.25)), f"{CHANNEL_NAME}  |  {CHANNEL_HANDLE}", fill=(0, 208, 156), font=f_brand)
    draw.rectangle([width - 300, 20, width - 35, bar_h - 20], fill=(0, 208, 156))
    draw.text((width - 280, int(bar_h * 0.30)), badge[:18], fill=(11, 19, 43), font=f_badge)

    # Headline
    y_cursor = bar_h + 60
    wrap_chars = 24 if width < height else 42
    for line in textwrap.wrap(headline, width=wrap_chars):
        draw.text((50, y_cursor), line, fill=(255, 255, 255), font=f_head)
        y_cursor += 66

    # Optional chart
    if chart_png and os.path.exists(chart_png):
        chart = Image.open(chart_png).convert("RGB")
        target_w = int(width * 0.90)
        ratio = target_w / chart.width
        target_h = int(chart.height * ratio)
        chart = chart.resize((target_w, target_h), Image.Resampling.LANCZOS)
        chart_x = (width - target_w) // 2
        chart_y = y_cursor + 30
        img.paste(chart, (chart_x, chart_y))
        y_cursor = chart_y + target_h + 30

    # Optional AI Host image (consistent identity)
    if host_png and os.path.exists(host_png):
        host = Image.open(host_png).convert("RGBA")
        target_h = int(height * 0.26)
        ratio = target_h / host.height
        target_w = int(host.width * ratio)
        host = host.resize((target_w, target_h), Image.Resampling.LANCZOS)
        img.paste(host, (width - target_w - 40, height - target_h - 140), host)

    # Bottom caption box
    cap_top = height - 340 if width < height else height - 220
    draw.rectangle([40, cap_top, width - 40, height - 90], fill=(20, 32, 62), outline=(0, 208, 156), width=3)
    cy = cap_top + 28
    for line in textwrap.wrap(caption, width=32 if width < height else 56)[:4]:
        draw.text((70, cy), line, fill=(241, 245, 249), font=f_cap)
        cy += 48

    # Disclaimer footer
    draw.text((40, height - 55), DISCLAIMER_TEXT, fill=(148, 163, 184), font=f_disc)
    img.save(out_png)
    return out_png


def assemble_video_ffmpeg(
    scene_pngs: List[str],
    durations: List[float],
    out_mp4: str,
    audio_wav: Optional[str] = None,
    fps: int = 30,
) -> str:
    """Assemble scene PNGs (+ optional WAV/MP3 voiceover) into 30 FPS H.264 MP4 via FFmpeg."""
    assert len(scene_pngs) == len(durations) and len(scene_pngs) > 0
    work_dir = Path(out_mp4).parent
    concat_file = work_dir / f"{Path(out_mp4).stem}_concat.txt"

    lines = []
    for png, dur in zip(scene_pngs, durations):
        lines.append(f"file '{os.path.abspath(png)}'")
        lines.append(f"duration {dur:.2f}")
    lines.append(f"file '{os.path.abspath(scene_pngs[-1])}'")
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
    ]
    if audio_wav and os.path.exists(audio_wav):
        cmd += ["-i", audio_wav, "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]

    cmd += [
        "-vf", f"fps={fps},format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-movflags", "+faststart",
        out_mp4,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_mp4


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S DEEP Free Automated Video Builder")
    parser.add_argument("--config", required=True, help="Path to scene JSON config")
    parser.add_argument("--format", choices=["short", "long"], default="short")
    parser.add_argument("--out", required=True, help="Output MP4 path")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    w, h = (1080, 1920) if args.format == "short" else (1920, 1080)
    tmp_dir = Path(args.out).parent / "_tmp_scenes"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    scene_pngs, durations = [], []
    for idx, sc in enumerate(cfg["scenes"]):
        chart_path = None
        if sc.get("chart"):
            c = sc["chart"]
            chart_path = str(tmp_dir / f"chart_{idx}.png")
            create_market_chart(
                c["title"], c["labels"], c["values"], c["unit"], c["source"], chart_path, is_vertical=(args.format == "short")
            )
        frame_path = str(tmp_dir / f"scene_{idx}.png")
        render_scene_frame(
            headline=sc["headline"],
            caption=sc["caption"],
            out_png=frame_path,
            width=w,
            height=h,
            chart_png=chart_path,
            host_png=cfg.get("host_png"),
            badge=sc.get("badge", "S DEEP FINANCE"),
        )
        scene_pngs.append(frame_path)
        durations.append(float(sc.get("duration", 5.0)))

    wav_path = str(tmp_dir / "voiceover.wav")
    has_voice = False
    if cfg.get("voiceover_text"):
        has_voice = generate_voiceover_piper(cfg["voiceover_text"], wav_path, model=cfg.get("piper_model", "hi_IN-pratham-medium"))

    assemble_video_ffmpeg(scene_pngs, durations, args.out, audio_wav=wav_path if has_voice else None, fps=30)
    print(f"Rendered {args.out} (voiceover={'yes' if has_voice else 'no - visual captioned template'})")
