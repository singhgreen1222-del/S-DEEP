#!/usr/bin/env python3
"""
S DEEP — AI 3D Animated Scene Video Generator Backend
Integrates with existing generated scripts (data/scripts/*.json, data/dryrun_preview.json)
without modifying or replacing pipeline.py.

All AI Video API keys are read securely from environment variables (GitHub Actions Secrets):
  - FAL_KEY             (Fal.ai Kling / Minimax / Wan image-to-video & text-to-video)
  - LUMA_API_KEY        (Luma Dream Machine v1)
  - REPLICATE_API_TOKEN (Replicate video models)
  - VEO_API_KEY / GEMINI_API_KEY (Google Veo 2.0 / Gemini script breakdown)

Honest status reporting: if no video generation API key is configured or an API fails,
scenes are marked 'api_not_configured' or 'failed' with the exact error; no fake videos are created.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SCENE_VIDEOS_DIR = DATA_DIR / "scene_videos"

STYLE_3D = (
    "Photorealistic 3D animated storytelling style, Pixar and Unreal Engine 5 cinematic realism, "
    "smooth character movement, natural body language, realistic facial expressions and lip-sync, "
    "authentic Indian characters and environments, 16:9 widescreen, Full HD 1080p, no text overlay, no collage"
)
DEFAULT_NEG = (
    "static image, slideshow, zoom only, collage, split screen, grid, text overlay, watermark, "
    "deformed hands, extra fingers, distorted face, 2d flat cartoon, blurry, low resolution"
)

CHAR_ARCHETYPES = [
    {
        "id": "arjun",
        "name": "Arjun",
        "age": "32",
        "role": "Indian Retail Investor",
        "face": "Warm expressive brown eyes, rounded jawline, light trimmed beard, thin round-framed glasses",
        "hairstyle": "Short neat dark black hair",
        "skin_tone": "Warm medium-brown Indian skin tone",
        "body_type": "Lean-medium Indian male build",
        "outfit": "Casual navy blue cotton linen shirt with rolled sleeves",
        "keywords": r"\b(aap|you|investor|retail|sip|portfolio|salary|middle class|aam aadmi|demat|trading|profit|loss|paisa|ghar|emi)\b",
    },
    {
        "id": "meera",
        "name": "Meera",
        "age": "30",
        "role": "Indian Financial Analyst",
        "face": "Sharp attentive dark eyes, confident calm expression, oval face",
        "hairstyle": "Shoulder-length wavy dark black hair",
        "skin_tone": "Wheatish-brown Indian skin tone",
        "body_type": "Slim poised Indian female build",
        "outfit": "Tailored charcoal blazer over an ivory kurta top",
        "keywords": r"\b(rbi|sebi|analyst|report|data|chart|sensex|nifty|gdp|inflation|cpi|fii|dii|market|stock|index|rate|expert)\b",
    },
    {
        "id": "vikram",
        "name": "Vikram",
        "age": "45",
        "role": "Indian Corporate & Banking Executive",
        "face": "Strong clean-shaven jawline, seasoned focused eyes",
        "hairstyle": "Salt-and-pepper neatly side-parted hair",
        "skin_tone": "Warm olive-brown Indian skin tone",
        "body_type": "Broad-shouldered upright Indian male build",
        "outfit": "Dark charcoal tailored suit with a crisp white shirt",
        "keywords": r"\b(bank|ceo|company|corporate|psu|ipo|rupee|dollar|govt|government|policy|fund|crore|lakh|billion|trillion)\b",
    },
    {
        "id": "priya",
        "name": "Priya",
        "age": "29",
        "role": "Indian Household Finance Planner",
        "face": "Gentle warm smile, expressive dark eyes, soft rounded cheeks",
        "hairstyle": "Long dark hair tied in a neat low ponytail",
        "skin_tone": "Warm golden-brown Indian skin tone",
        "body_type": "Medium graceful Indian female build",
        "outfit": "Pastel teal cotton kurti with minimal silver earrings",
        "keywords": r"\b(family|home|gold|wedding|kitchen|parents|kids|education|rent|budget|savings|bachat|kharcha)\b",
    },
]


def _seed(text: str) -> int:
    return (int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % 899999) + 100000


def _http_json(url: str, payload: dict | None = None, headers: dict | None = None, method: str | None = None, timeout: int = 60) -> dict:
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method or ("POST" if data else "GET"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(url: str, dest: Path, timeout: int = 180) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "S-DEEP-SceneEngine/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())
    return dest


def load_existing_script(script_id: str) -> dict:
    """Fetch already-generated script without modifying or regenerating via pipeline.py."""
    if script_id == "__dryrun__":
        p = DATA_DIR / "dryrun_preview.json"
    else:
        p = DATA_DIR / "scripts" / f"{script_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Existing script not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def detect_or_load_characters(script_id: str, script_data: dict, out_dir: Path) -> list[dict]:
    char_file = out_dir / "characters.json"
    if char_file.exists():
        try:
            existing = json.loads(char_file.read_text(encoding="utf-8"))
            if isinstance(existing, list) and existing:
                return existing
        except Exception:
            pass

    full_text = (script_data.get("title", "") + "\n" + "\n".join(s.get("text", "") for s in script_data.get("scenes", [])))
    gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
    chars = []

    if gem_key:
        prompt = (
            "Identify all recurring characters needed for a 3D animated storytelling video of this Indian finance script. "
            "Output STRICT JSON array of objects with keys: name, age, role, face, hairstyle, skin_tone, body_type, outfit. "
            "Keep realistic Indian features.\n\nScript:\n" + full_text[:4000]
        )
        for model in ("gemini-3.5-flash-lite", "gemini-3.6-flash"):
            try:
                res = _http_json(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(gem_key)}",
                    payload={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}},
                )
                txt = res["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(re.sub(r"^```json\s*|```$", "", txt.strip()))
                if isinstance(parsed, list) and parsed:
                    for c in parsed[:4]:
                        cid = re.sub(r"[^a-z0-9_]", "_", c.get("name", "char").lower()).strip("_") or "char"
                        chars.append({
                            "id": cid,
                            "name": c.get("name", "Arjun"),
                            "age": str(c.get("age", "32")),
                            "role": c.get("role", "Storyteller"),
                            "face": c.get("face", "Warm expressive brown eyes, natural Indian facial features"),
                            "hairstyle": c.get("hairstyle", "Neat dark black hair"),
                            "skin_tone": c.get("skin_tone", "Warm medium-brown Indian skin tone"),
                            "body_type": c.get("body_type", "Medium build"),
                            "outfit": c.get("outfit", "Smart casual Indian attire"),
                            "seed": _seed("sdeep_char_" + cid),
                        })
                    break
            except Exception:
                continue

    if not chars:
        for arch in CHAR_ARCHETYPES:
            if re.search(arch["keywords"], full_text, re.I):
                chars.append({
                    "id": arch["id"],
                    "name": arch["name"],
                    "age": arch["age"],
                    "role": arch["role"],
                    "face": arch["face"],
                    "hairstyle": arch["hairstyle"],
                    "skin_tone": arch["skin_tone"],
                    "body_type": arch["body_type"],
                    "outfit": arch["outfit"],
                    "seed": _seed("sdeep_char_" + arch["id"]),
                })
        if not chars:
            a = CHAR_ARCHETYPES[0]
            chars.append({k: a[k] for k in ("id", "name", "age", "role", "face", "hairstyle", "skin_tone", "body_type", "outfit")} | {"seed": _seed("sdeep_char_" + a["id"])})

    # Generate permanent character reference images (free Pollinations) if missing
    for c in chars:
        ref_rel = f"char_{c['id']}.png"
        ref_path = out_dir / ref_rel
        c["reference_image"] = f"data/scene_videos/{script_id}/{ref_rel}"
        c["identity_lock"] = f"{c['name']} ({c['age']}yo Indian {c['role']}, {c['skin_tone']}, {c['face']}, {c['hairstyle']}, {c['body_type']}, wearing {c['outfit']})"
        if not ref_path.exists():
            ref_prompt = f"{STYLE_3D}, character reference portrait of {c['identity_lock']}, neutral studio background, centered head and shoulders, single character"
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(ref_prompt)}?width=768&height=768&nologo=true&seed={c['seed']}"
            try:
                _download_file(url, ref_path, timeout=45)
            except Exception as e:
                c["ref_error"] = str(e)

    char_file.write_text(json.dumps(chars, indent=2, ensure_ascii=False), encoding="utf-8")
    return chars


def breakdown_script_to_scenes(script_data: dict, characters: list[dict]) -> list[dict]:
    """Divide existing script into 5-10s 3D animated storytelling scenes with separated narration and dialogues."""
    raw_scenes = script_data.get("scenes", [])
    merged = []
    for s in raw_scenes:
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        wc = len(txt.split())
        if merged and (wc < 14 or len(merged[-1]["text"].split()) < 14) and (len(merged[-1]["text"].split()) + wc <= 42):
            merged[-1]["text"] += " " + txt
        else:
            merged.append({"text": txt, "chapter": s.get("chapter", "")})

    cameras = [
        "Slow cinematic dolly push-in at eye level with shallow depth of field",
        "Smooth horizontal tracking pan across the room",
        "Three-quarter medium shot with subtle handheld breathing motion",
        "Over-the-shoulder shot pivoting toward glowing financial data screen",
        "Wide establishing shot slowly zooming toward the speaker",
    ]
    lights = [
        "Warm golden-hour Indian sunlight with soft volumetric rim light",
        "Dramatic moody amber and cool cyan monitor glow",
        "Crisp natural daylight with soft cinematic studio fill",
        "Warm indoor tungsten lamp light with subtle dusk contrast",
    ]
    envs = [
        "Modern Mumbai financial workspace overlooking Dalal Street BSE skyline",
        "Warm realistic middle-class Indian apartment living room with wooden furniture and balcony",
        "Sleek Bengaluru corporate meeting room with glass walls and city view",
        "Cozy Indian home study desk with laptop, family photo frame and books",
    ]

    scenes = []
    for i, m in enumerate(merged):
        txt = m["text"]
        wc = len(txt.split())
        dur = max(5, min(10, round(wc / 3.2)))
        c_main = characters[i % len(characters)]
        c_list = [c_main["name"]]
        if len(characters) > 1 and i % 2 == 1:
            c_list.append(characters[(i + 1) % len(characters)]["name"])

        if re.search(r"\b(crash|gir|panic|loss|risk|warning)\b", txt, re.I):
            actions = f"{c_main['name']} leans forward with concerned eyebrows, gesturing toward falling red market candles while speaking"
        elif re.search(r"\b(rally|high|profit|growth|buying|uchhal)\b", txt, re.I):
            actions = f"{c_main['name']} smiles energetically, nodding and pointing toward rising green financial charts"
        else:
            actions = f"{c_main['name']} speaks naturally with expressive hand gestures and realistic lip-sync"

        bg = envs[i % len(envs)]
        cam = cameras[i % len(cameras)]
        light = lights[i % len(lights)]
        anim_3d = f"Continuous {dur}s 3D character animation: natural head turns, blinking, expressive hand gestures, accurate lip-sync, subtle cloth physics, and {cam.lower()}."

        locked_chars = "; ".join(c["identity_lock"] for c in characters if c["name"] in c_list)
        video_prompt = f"{STYLE_3D}. Characters: {locked_chars}. Action & Expression: {actions}. Environment: {bg}. Camera: {cam}. Lighting: {light}."

        dialogues = []
        if len(c_list) > 1:
            dialogues.append({"speaker": c_list[0], "line": txt})
            narration = ""
        else:
            narration = txt

        scenes.append({
            "scene_number": i + 1,
            "title": (m.get("chapter") or f"Scene {i+1}").strip(),
            "duration_sec": dur,
            "characters_present": c_list,
            "actions_and_expressions": actions,
            "narration": narration,
            "dialogues": dialogues,
            "location_and_background": bg,
            "camera_angle_and_movement": cam,
            "lighting_and_atmosphere": light,
            "animation_3d_instructions": anim_3d,
            "video_prompt": video_prompt,
            "negative_prompt": DEFAULT_NEG,
            "seed": c_main["seed"] + (i + 1) * 19,
            "status": "queued",
            "retry_count": 0,
            "error": "",
            "video_path": "",
            "provider": "",
        })
    return scenes


def _call_video_api(scene: dict, ref_img_path: Path | None, out_mp4: Path) -> str:
    """
    Calls configured AI Video Generation API using backend secrets.
    Returns provider name on success; raises RuntimeError with honest reason otherwise.
    """
    fal_key = os.environ.get("FAL_KEY", "").strip()
    luma_key = os.environ.get("LUMA_API_KEY", "").strip()
    rep_token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    veo_key = os.environ.get("VEO_API_KEY", "").strip()

    prompt = scene["video_prompt"]
    dur = scene.get("duration_sec", 5)

    # 1. Fal.ai (Kling / Minimax text-to-video)
    if fal_key:
        endpoint = "https://queue.fal.run/fal-ai/kling-video/v1.6/standard/text-to-video"
        sub = _http_json(
            endpoint,
            payload={"prompt": prompt, "duration": "10" if dur >= 8 else "5", "aspect_ratio": "16:9"},
            headers={"Authorization": f"Key {fal_key}"},
        )
        status_url = sub.get("status_url")
        resp_url = sub.get("response_url")
        if not status_url:
            raise RuntimeError(f"Fal.ai invalid response: {sub}")
        for _ in range(90):
            time.sleep(5)
            st = _http_json(status_url, headers={"Authorization": f"Key {fal_key}"})
            if st.get("status") == "COMPLETED":
                res = _http_json(resp_url, headers={"Authorization": f"Key {fal_key}"})
                vid_url = (res.get("video") or {}).get("url")
                if not vid_url:
                    raise RuntimeError(f"Fal.ai missing video URL: {res}")
                _download_file(vid_url, out_mp4)
                return "fal-kling-1.6"
            if st.get("status") in ("FAILED", "ERROR"):
                raise RuntimeError(f"Fal.ai failed: {st}")
        raise RuntimeError("Fal.ai generation timed out")

    # 2. Luma Dream Machine
    if luma_key:
        sub = _http_json(
            "https://api.lumalabs.ai/dream-machine/v1/generations",
            payload={"prompt": prompt, "aspect_ratio": "16:9", "loop": False},
            headers={"Authorization": f"Bearer {luma_key}"},
        )
        gid = sub.get("id")
        if not gid:
            raise RuntimeError(f"Luma invalid response: {sub}")
        for _ in range(90):
            time.sleep(5)
            st = _http_json(f"https://api.lumalabs.ai/dream-machine/v1/generations/{gid}", headers={"Authorization": f"Bearer {luma_key}"})
            if st.get("state") == "completed":
                vid_url = (st.get("assets") or {}).get("video")
                if not vid_url:
                    raise RuntimeError("Luma completed without video URL")
                _download_file(vid_url, out_mp4)
                return "luma-dream-machine"
            if st.get("state") == "failed":
                raise RuntimeError(f"Luma failed: {st.get('failure_reason')}")
        raise RuntimeError("Luma generation timed out")

    # 3. Replicate
    if rep_token:
        sub = _http_json(
            "https://api.replicate.com/v1/models/minimax/video-01/predictions",
            payload={"input": {"prompt": prompt, "prompt_optimizer": True}},
            headers={"Authorization": f"Bearer {rep_token}"},
        )
        poll_url = (sub.get("urls") or {}).get("get")
        if not poll_url:
            raise RuntimeError(f"Replicate invalid response: {sub}")
        for _ in range(90):
            time.sleep(5)
            st = _http_json(poll_url, headers={"Authorization": f"Bearer {rep_token}"})
            if st.get("status") == "succeeded":
                vid_url = st.get("output") if isinstance(st.get("output"), str) else (st.get("output") or [None])[0]
                if not vid_url:
                    raise RuntimeError("Replicate missing output URL")
                _download_file(vid_url, out_mp4)
                return "replicate-minimax"
            if st.get("status") in ("failed", "canceled"):
                raise RuntimeError(f"Replicate failed: {st.get('error')}")
        raise RuntimeError("Replicate generation timed out")

    # 4. Google Veo (if VEO_API_KEY configured)
    if veo_key:
        raise RuntimeError("VEO_API_KEY endpoint requires Vertex AI / Veo long-running polling configuration.")

    raise RuntimeError(
        "No AI video-generation API key configured. Add FAL_KEY, LUMA_API_KEY, or REPLICATE_API_TOKEN in GitHub Actions Secrets."
    )


def process_scene_jobs(manifest: dict, characters: list[dict], out_dir: Path, target_scenes: list[int] | None = None):
    manifest_path = out_dir / "manifest.json"
    char_map = {c["name"]: c for c in characters}
    for s in manifest["scenes"]:
        num = s["scene_number"]
        if target_scenes and num not in target_scenes:
            continue
        if not target_scenes and s.get("status") == "ready" and (ROOT / s.get("video_path", "")).exists():
            continue

        s["status"] = "generating"
        s["error"] = ""
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        out_mp4 = out_dir / f"scene_{num:02d}.mp4"
        ref_img = None
        if s.get("characters_present"):
            c0 = char_map.get(s["characters_present"][0])
            if c0 and c0.get("reference_image"):
                cand = ROOT / c0["reference_image"]
                if cand.exists():
                    ref_img = cand

        last_err = ""
        for attempt in range(2):
            try:
                prov = _call_video_api(s, ref_img, out_mp4)
                s["status"] = "ready"
                s["provider"] = prov
                s["video_path"] = f"data/scene_videos/{manifest['script_id']}/scene_{num:02d}.mp4"
                s["error"] = ""
                break
            except Exception as e:
                last_err = str(e)
                s["retry_count"] = s.get("retry_count", 0) + 1
                if "No AI video-generation API key configured" in last_err:
                    s["status"] = "api_not_configured"
                    s["error"] = last_err
                    break
                time.sleep(2)
        else:
            s["status"] = "failed"
            s["error"] = last_err

        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def merge_and_export(manifest: dict, out_dir: Path, target_scenes: list[int] | None, resolution: str, aspect: str, include_narration: bool, include_bgm: bool):
    scenes = [s for s in manifest["scenes"] if (not target_scenes or s["scene_number"] in target_scenes)]
    clips = [ROOT / s["video_path"] for s in scenes if s.get("status") == "ready" and s.get("video_path") and (ROOT / s["video_path"]).exists()]
    if not clips:
        raise RuntimeError("No ready scene MP4 clips found to merge. Generate scene videos first.")

    w, h = (1920, 1080) if resolution == "1080p" else (1280, 720)
    if aspect == "9:16":
        w, h = h, w

    concat_txt = out_dir / "concat_list.txt"
    norm_clips = []
    for idx, cl in enumerate(clips):
        nc = out_dir / f"_norm_{idx:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(cl),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(nc)
        ], check=True)
        norm_clips.append(nc)

    concat_txt.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips), encoding="utf-8")
    merged_mp4 = out_dir / "complete_video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c", "copy", str(merged_mp4)
    ], check=True)

    for nc in norm_clips:
        nc.unlink(missing_ok=True)
    concat_txt.unlink(missing_ok=True)

    manifest["complete_video_path"] = f"data/scene_videos/{manifest['script_id']}/complete_video.mp4"
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Merged complete video:", merged_mp4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script-id", required=True)
    ap.add_argument("--action", default="breakdown_and_generate", choices=["breakdown_only", "breakdown_and_generate", "regenerate_scene", "merge_export"])
    ap.add_argument("--scenes", default="", help="Comma-separated scene numbers")
    ap.add_argument("--resolution", default="1080p", choices=["1080p", "720p"])
    ap.add_argument("--aspect-ratio", default="16:9", choices=["16:9", "9:16"])
    ap.add_argument("--include-narration", default="true")
    ap.add_argument("--include-bgm", default="false")
    args = ap.parse_args()

    out_dir = SCENE_VIDEOS_DIR / args.script_id
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"

    script_data = load_existing_script(args.script_id)
    characters = detect_or_load_characters(args.script_id, script_data, out_dir)

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "script_id": args.script_id,
            "title": script_data.get("title", args.script_id),
            "characters": characters,
            "scenes": breakdown_script_to_scenes(script_data, characters),
            "complete_video_path": "",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    target = [int(x.strip()) for x in args.scenes.split(",") if x.strip().isdigit()] or None

    if args.action == "breakdown_only":
        print("Breakdown saved:", manifest_path)
    elif args.action in ("breakdown_and_generate", "regenerate_scene"):
        process_scene_jobs(manifest, characters, out_dir, target_scenes=target)
    elif args.action == "merge_export":
        merge_and_export(
            manifest, out_dir, target, args.resolution, args.aspect_ratio,
            args.include_narration.lower() == "true", args.include_bgm.lower() == "true"
        )


if __name__ == "__main__":
    main()
