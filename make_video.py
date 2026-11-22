#!/usr/bin/env python3
"""Script JSON -> Hindi voice -> host photo + charts -> captions -> MP4 (intro/outro included)."""
import argparse, asyncio, json, os, re, subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZES = {"short": (1080, 1920), "long": (1920, 1080)}
FPS, PAD, CARD = 30, 0.35, 2.0
LABELS = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX", "^NSEBANK": "BANK NIFTY"}
DISCLAIMER = "Educational content only. Not investment advice."
YELLOW = (250, 204, 21)


def run(cmd, cwd=None):
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)


def media_duration(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "default=nokey=1:noprint_wrappers=1", str(path)])
    return float(out.decode().strip())


# ---------------- voice ----------------
def split_chunks(text, limit=180):
    parts = [p.strip() for p in re.split(r"(?<=[।.?!])\s+", text) if p.strip()]
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 <= limit:
            cur = (cur + " " + p).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


_xtts = None


def tts_xtts(text, out_wav, ref):
    """Clone voice from reference.wav (XTTS-v2). Model license: non-commercial."""
    global _xtts
    import soundfile as sf
    if _xtts is None:
        import torch
        from TTS.api import TTS
        _xtts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda" if torch.cuda.is_available() else "cpu")
    sr = _xtts.synthesizer.output_sample_rate
    wavs = []
    for ch in split_chunks(text):
        wavs.append(np.array(_xtts.tts(text=ch, speaker_wav=str(ref), language="hi")))
        wavs.append(np.zeros(int(sr * 0.25)))
    sf.write(str(out_wav), np.concatenate(wavs), sr)



def tts_piper(text, out_wav, model="hi_IN-pratham-medium"):
    import subprocess
    subprocess.run(
        ["piper", "--model", model, "--output_file", str(out_wav)],
        input=text.encode("utf-8"),
        check=True,
    )

def tts_edge(text, out_mp3, voice):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, voice).save(str(out_mp3)))


def tts_gtts(text, out_mp3):
    from gtts import gTTS
    gTTS(text=text, lang="hi").save(str(out_mp3))


def tts_test(text, out_wav):
    """Dry-run: quiet tone, no internet/model needed. Pipeline test ke liye."""
    dur = max(1.5, len(text.split()) / 2.6)
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur:.2f}",
         "-af", "volume=0.05", "-ar", "44100", out_wav])


def synth(engine, text, base, ref, voice):
    if engine == "xtts":
        if not ref or not Path(ref).exists():
            raise RuntimeError("reference.wav nahi mila (Voice tab mein banao)")
        p = Path(str(base) + ".wav"); tts_xtts(text, p, ref)
    elif engine == "test":
        p = Path(str(base) + ".wav"); tts_test(text, p)
    else:
        p = Path(str(base) + ".mp3")
        if engine == "piper":
            p = base.with_suffix(".wav")
            try:
                tts_piper(text, p)
            except Exception as e:
                print(f"  ! piper fail ({e}); gTTS fallback")
                p = base.with_suffix(".mp3")
                tts_gtts(text, p)
        elif engine == "gtts":
            tts_gtts(text, p)
        else:
            try:
                tts_edge(text, p, voice)
            except Exception as e:  # cloud IP par kabhi block hota hai
                print(f"  ! edge-tts fail ({e}); gTTS fallback")
                tts_gtts(text, p)
    return p


# ---------------- visuals ----------------
def font(size):
    for name in ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def chart_box(mode):
    return (1190, 110, 1880, 640) if mode == "long" else (40, 1010, 1040, 1470)


def full_box(mode):
    return (150, 110, 1770, 830) if mode == "long" else (30, 230, 1050, 1350)


def make_chart(symbol, out_png, bw, bh):
    try:
        import yfinance as yf
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        df = yf.download(symbol, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            print(f"  ! {symbol}: data nahi mila, chart skip")
            return False
        close = df["Close"].squeeze().dropna()
        col = "#22c55e" if close.iloc[-1] >= close.iloc[0] else "#ef4444"
        fig, ax = plt.subplots(figsize=(bw / 100, bh / 100), dpi=100)
        fig.patch.set_facecolor("#0b1226"); ax.set_facecolor("#0b1226")
        ax.plot(close.index, close.values, color=col, linewidth=3)
        ax.fill_between(close.index, close.values, close.values.min(), color=col, alpha=0.15)
        ax.set_title(f"{LABELS.get(symbol, symbol)} | last close {close.iloc[-1]:,.0f} | as of {close.index[-1].date()}",
                     color="white", fontsize=15, pad=10)
        ax.tick_params(colors="#cbd5e1", labelsize=11)
        for s in ax.spines.values():
            s.set_color("#334155")
        ax.grid(alpha=0.15); fig.autofmt_xdate(); fig.tight_layout()
        fig.savefig(out_png, facecolor=fig.get_facecolor()); plt.close(fig)
        return True
    except Exception as e:
        print(f"  ! chart error ({symbol}): {e}")
        return False


def gradient(w, h):
    t = np.linspace(0, 1, h)[:, None, None]
    c0, c1 = np.array([8, 14, 32]), np.array([18, 36, 72])
    return Image.fromarray(np.repeat((c0 + (c1 - c0) * t).astype("uint8"), w, axis=1))


def load_host(path):
    im = Image.open(path)
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (12, 20, 40)); bg.paste(im, mask=im.split()[3]); return bg
    return im.convert("RGB")


def cover(img, w, h, cx=0.5, cy=0.0):
    iw, ih = img.size
    s = max(w / iw, h / ih)
    r = img.resize((int(iw * s) + 1, int(ih * s) + 1), Image.LANCZOS)
    x, y = int((r.width - w) * cx), int((r.height - h) * cy)
    return r.crop((x, y, x + w, y + h))


def bottom_shade(img, frac=0.38, maxa=205):
    w, h = img.size
    hh = int(h * frac)
    a = np.repeat(np.linspace(0, maxa, hh).astype("uint8")[:, None], w, axis=1)
    layer = Image.new("RGBA", (w, hh), (0, 0, 0, 255)); layer.putalpha(Image.fromarray(a))
    img.paste(layer, (0, h - hh), layer)


def paste_fit(img, pic, box, outline=True):
    x0, y0, x1, y1 = box
    p = pic.copy(); p.thumbnail((x1 - x0, y1 - y0))
    x, y = x0 + (x1 - x0 - p.width) // 2, y0 + (y1 - y0 - p.height) // 2
    img.paste(p, (x, y))
    if outline:
        ImageDraw.Draw(img).rectangle([x - 2, y - 2, x + p.width + 2, y + p.height + 2], outline=YELLOW, width=3)


def make_frame(mode, layout, chart_png, host_path, out_png):
    w, h = SIZES[mode]
    if layout == "chart_full" or not host_path:
        img = gradient(w, h)
        if chart_png:
            paste_fit(img, Image.open(chart_png).convert("RGB"), full_box(mode))
        elif not host_path:
            ImageDraw.Draw(img).text((w // 2, h // 2), "S DEEP", font=font(120), fill=(255, 255, 255), anchor="mm")
    else:
        img = cover(load_host(host_path), w, h, cx=0.46 if mode == "short" else 0.5, cy=0.0 if mode == "short" else 0.1)
        bottom_shade(img)
        if layout == "host_chart" and chart_png:
            paste_fit(img, Image.open(chart_png).convert("RGB"), chart_box(mode))
    d = ImageDraw.Draw(img)
    d.text((34, 26), "S DEEP", font=font(50), fill=YELLOW, stroke_width=3, stroke_fill=(0, 0, 0))
    if mode == "long":
        d.text((w - 40, 40), DISCLAIMER, font=font(24), fill=(203, 213, 225), anchor="ra", stroke_width=2, stroke_fill=(0, 0, 0))
    else:
        d.text((w // 2, h - 40), DISCLAIMER, font=font(26), fill=(203, 213, 225), anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
    img.save(out_png)


def card_clip(mode, title, sub, base):
    w, h = SIZES[mode]
    img = gradient(w, h); d = ImageDraw.Draw(img)
    d.text((w // 2, h // 2 - 40), title, font=font(150 if mode == "long" else 130), fill=YELLOW, anchor="mm")
    d.text((w // 2, h // 2 + 90), sub, font=font(42 if mode == "long" else 38), fill=(255, 255, 255), anchor="mm")
    png, clip = base.with_suffix(".png"), base.with_suffix(".mp4")
    img.save(png)
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", FPS, "-t", CARD, "-i", png,
         "-f", "lavfi", "-t", CARD, "-i", "anullsrc=r=44100:cl=stereo", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest", clip])
    return clip.name


THEMES = {"bullish": ((6, 38, 26), (34, 197, 94)), "gold": ((34, 24, 4), (250, 204, 21)),
          "alert": ((46, 8, 10), (239, 68, 68)), "blue": ((6, 20, 52), (59, 130, 246))}


def _fit_text(d, text, maxw, maxh):
    words = text.upper().split()
    for sz in range(150, 56, -6):
        f = font(sz); lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= maxw:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= 3 and all(d.textlength(l, font=f) <= maxw for l in lines) and len(lines) * sz * 1.08 <= maxh:
            return f, lines, sz
    return font(56), lines[:3], 56


def make_thumb(host_path, text, out_jpg, badge="S DEEP", theme="gold"):
    """1280x720 click-worthy thumbnail: big stroked headline, host face, glow, badge, rising arrow."""
    from PIL import ImageChops, ImageFilter
    W, H = 1280, 720
    bg0, acc = THEMES.get(theme, THEMES["gold"])
    img = Image.new("RGB", (W, H), bg0)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([640, 40, 1260, 700], fill=tuple(int(c * 0.6) for c in acc))
    img = ImageChops.add(img, glow.filter(ImageFilter.GaussianBlur(110)))
    if host_path:
        host = load_host(host_path); iw, ih = host.size
        crop = host.crop((int(iw * 0.18), 0, int(iw * 0.80), int(ih * 0.80)))
        crop = crop.resize((int(crop.width * H / crop.height), H), Image.LANCZOS)
        x = W - crop.width + 40
        fade = np.ones((H, crop.width), dtype="float32") * 255
        fw = 170
        fade[:, :fw] = np.linspace(0, 255, fw)[None, :]
        img.paste(crop, (x, 0), Image.fromarray(fade.astype("uint8")))
    d = ImageDraw.Draw(img)
    # rising arrow motif (bottom-left)
    pts = [(50, 690), (200, 640), (300, 665), (470, 560), (560, 590), (700, 470)]
    if theme == "alert":  # girta hua arrow
        pts = [(x, 1160 - y) for x, y in pts]
    d.line(pts, fill=acc, width=10, joint="curve")
    ex, ey = pts[-1]; sg = 1 if theme != "alert" else -1
    d.polygon([(ex, ey), (ex - 50, ey + 8 * sg), (ex - 12, ey + 42 * sg)], fill=acc)
    # headline
    f, lines, sz = _fit_text(d, text or "S DEEP", 640, 430)
    y = 150 + (430 - len(lines) * sz * 1.08) / 2
    for i, ln in enumerate(lines):
        col = acc if i % 2 == 1 or len(lines) == 1 else (255, 255, 255)
        d.text((50, y), ln, font=f, fill=col, stroke_width=9, stroke_fill=(0, 0, 0))
        y += sz * 1.08
    # badge
    bf = font(40); bt = (badge or "S DEEP").upper()[:16]
    bw = d.textlength(bt, font=bf) + 50
    d.rounded_rectangle([48, 40, 48 + bw, 112], radius=16, fill=acc)
    d.text((48 + bw / 2, 76), bt, font=bf, fill=(0, 0, 0), anchor="mm")
    # brand + border
    d.text((W - 40, H - 36), "S DEEP", font=font(46), fill=(255, 255, 255), anchor="rm", stroke_width=5, stroke_fill=(0, 0, 0))
    d.rectangle([0, 0, W - 1, H - 1], outline=acc, width=8)
    img.save(out_jpg, quality=90)


# ---------------- captions ----------------
def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def caption_lines(text, per):
    words = text.split()
    return [" ".join(words[i:i + per]) for i in range(0, len(words), per)] or [text]


# ---------------- main renderer ----------------
def render_video(cfg, slug, out_dir, engine="piper", ref=None, voice="hi-IN-MadhurNeural",
                 host=None, music=None, intro=True, log=print):
    mode = cfg.get("mode", "short")
    w, h = SIZES[mode]
    out_dir = Path(out_dir)
    work = out_dir / f"{slug}_work"
    work.mkdir(parents=True, exist_ok=True)
    clips, srt, t, n, chapters = [], [], 0.0, 1, []
    if intro:
        clips.append(card_clip(mode, "S DEEP", "Finance | Share Market | Indian Economy", work / "intro")); t += CARD
    charts, frames, scenes = {}, {}, cfg["scenes"]
    for i, sc in enumerate(scenes):
        log(f"[{slug}] scene {i + 1}/{len(scenes)}")
        if sc.get("chapter"):
            chapters.append([round(t, 1) if chapters else 0.0, sc["chapter"]])
        if engine == "heygen":
            from avatar_provider import render_scene
            avatar_clip = work / f"avatar_scene{i}.mp4"
            ratio = "9:16" if mode == "short" else "16:9"
            render_scene(
                sc["text"], avatar_clip, aspect_ratio=ratio,
                title=cfg.get("title", "S DEEP"),
                motion_prompt=os.environ.get(
                    "HEYGEN_MOTION_PROMPT",
                    "Speak naturally to camera with subtle head movement, warm expression and restrained hand gestures."
                ),
                engine_type=os.environ.get("HEYGEN_ENGINE", "heygen-avatar-6"),
            )
            # Normalize provider output so concat demuxer sees identical dimensions/codecs
            # across scenes, regardless of the provider's internal encoding profile.
            normalized_clip = work / f"clip{i}.mp4"
            run([
                "ffmpeg", "-y", "-loglevel", "error", "-i", avatar_clip,
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
                "-r", FPS, "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-ar", "44100", "-ac", "2", "-movflags", "+faststart", normalized_clip
            ])
            # Provider returns a finished talking-head clip with its own synchronized audio.
            dur = media_duration(normalized_clip)
            clips.append(normalized_clip.name)
            lines = caption_lines(sc["text"], 5 if mode == "short" else 8)
            weights = [len(l) for l in lines]; tw, tt = sum(weights), t
            for l, wt in zip(lines, weights):
                d_ = dur * wt / tw
                srt.append(f"{n}\n{srt_time(tt)} --> {srt_time(tt + d_)}\n{l}\n"); n += 1; tt += d_
            t += dur
            continue
        audio = synth(engine, sc["text"], work / f"a{i}", ref, voice)
        dur = media_duration(audio)
        sym = sc.get("chart")
        layout = sc.get("layout") or ("host_chart" if sym else "host")
        chart_png = None
        if sym:
            key = (sym, layout)
            if key not in charts:
                b = full_box(mode) if layout == "chart_full" else chart_box(mode)
                p = work / f"chart{len(charts)}.png"
                charts[key] = p if make_chart(sym, p, b[2] - b[0], b[3] - b[1]) else None
            chart_png = charts[key]
            if chart_png is None:
                layout = "host"
        fk = (layout, str(chart_png))
        if fk not in frames:
            fp = work / f"frame{len(frames)}.png"
            make_frame(mode, layout, chart_png, host, fp)
            frames[fk] = fp
        total = dur + PAD
        clip = work / f"clip{i}.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", FPS, "-i", frames[fk], "-i", audio,
             "-af", f"apad=pad_dur={PAD}", "-t", f"{total:.3f}", "-c:v", "libx264", "-tune", "stillimage",
             "-pix_fmt", "yuv420p", "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", clip])
        clips.append(clip.name)
        lines = caption_lines(sc["text"], 5 if mode == "short" else 8)
        weights = [len(l) for l in lines]; tw, tt = sum(weights), t
        for l, wt in zip(lines, weights):
            d_ = dur * wt / tw
            srt.append(f"{n}\n{srt_time(tt)} --> {srt_time(tt + d_)}\n{l}\n"); n += 1; tt += d_
        t += total
    if intro:
        clips.append(card_clip(mode, "Like | Subscribe", "@sdeepworldwide", work / "outro"))

    (work / "subs.srt").write_text("\n".join(srt), encoding="utf-8")
    (work / "chapters.json").write_text(json.dumps(chapters, ensure_ascii=False), encoding="utf-8")
    (out_dir / f"{slug}.srt").write_text("\n".join(srt), encoding="utf-8")
    (work / "list.txt").write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
         "joined.mp4"], cwd=work)

    size, mv = (13, 12) if mode == "long" else (9, 45)
    style = (f"FontName=Noto Sans Devanagari,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,"
             f"OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV={mv}")
    vf = f"subtitles=subs.srt:force_style='{style}'"
    out = (out_dir / f"{slug}.mp4").resolve()
    enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", FPS,
           "-c:a", "aac", "-b:a", "192k"]
    if music and Path(music).exists():
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", "joined.mp4", "-stream_loop", "-1", "-i",
             Path(music).resolve(), "-filter_complex",
             f"[0:v]{vf}[v];[1:a]volume=0.07[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "[v]", "-map", "[a]", *enc, out], cwd=work)
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", "joined.mp4", "-vf", vf, *enc, out], cwd=work)
    final = media_duration(out)
    msg = f"DONE {out.name} ({final / 60:.1f} min, {w}x{h}, {FPS}fps)"
    if mode == "long" and not 18 * 60 <= final <= 22 * 60:
        msg += "  ! 18-22 min target se bahar"
    if mode == "short" and final > 180:
        msg += "  ! 3 min se lamba (Short nahi ginega)"
    log(msg)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("script"); ap.add_argument("--engine", choices=["xtts", "edge", "gtts", "test", "heygen"], default="piper")
    ap.add_argument("--ref"); ap.add_argument("--voice", default="hi-IN-MadhurNeural")
    ap.add_argument("--host"); ap.add_argument("--music"); ap.add_argument("--out", default="out")
    a = ap.parse_args()
    render_video(json.loads(Path(a.script).read_text(encoding="utf-8")), Path(a.script).stem, a.out,
                 a.engine, a.ref, a.voice, a.host, a.music)
