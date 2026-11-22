"""Optional HeyGen v3 Digital Twin provider.

Billable external rendering is opt-in. Requires a user-owned/consented Digital Twin
and a voice available to that HeyGen account. Never logs API keys.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

API = "https://api.heygen.com"


class AvatarProviderError(RuntimeError):
    pass


def _config():
    key = os.environ.get("HEYGEN_API_KEY", "").strip()
    avatar = os.environ.get("HEYGEN_AVATAR_ID", "").strip()
    voice = os.environ.get("HEYGEN_VOICE_ID", "").strip()
    if os.environ.get("HEYGEN_CONFIRM_BILLING", "").lower() != "true":
        raise AvatarProviderError(
            "HeyGen generation is billable. Set HEYGEN_CONFIRM_BILLING=true only after reviewing your plan/credits."
        )
    if not (key and avatar and voice):
        raise AvatarProviderError(
            "HeyGen config missing: set HEYGEN_API_KEY, HEYGEN_AVATAR_ID and HEYGEN_VOICE_ID."
        )
    return key, avatar, voice


def _headers(key):
    return {"x-api-key": key, "Content-Type": "application/json", "Accept": "application/json"}


def _payload_data(response):
    try:
        body = response.json()
    except ValueError as exc:
        raise AvatarProviderError("HeyGen returned invalid JSON.") from exc
    if not isinstance(body, dict):
        raise AvatarProviderError("HeyGen returned an unexpected response.")
    if body.get("error"):
        raise AvatarProviderError(f"HeyGen API error: {str(body['error'])[:240]}")
    return body.get("data") or body


def render_scene(text: str, out_file: str | Path, aspect_ratio="9:16",
                 title="S DEEP", motion_prompt=None, engine_type="heygen-avatar-6",
                 session=None, poll_seconds=8, timeout_seconds=1800):
    """Create one avatar scene, poll completion and download the generated MP4."""
    key, avatar_id, voice_id = _config()
    if not text or not text.strip():
        raise AvatarProviderError("Scene text is empty.")
    if aspect_ratio not in {"9:16", "16:9"}:
        raise AvatarProviderError("Unsupported aspect ratio; expected 9:16 or 16:9.")

    http = session or requests
    payload = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "script": text.strip(),
        "voice_id": voice_id,
        "title": (title or "S DEEP")[:100],
        "engine": {"type": engine_type},
        "resolution": "1080p",
        "aspect_ratio": aspect_ratio,
        "caption": {"file_format": "srt"},
    }
    if motion_prompt and engine_type in {"heygen-avatar-6", "heygen-avatar-6-turbo", "avatar_v"}:
        payload["motion_prompt"] = motion_prompt[:500]

    try:
        resp = http.post(f"{API}/v3/videos", headers=_headers(key), json=payload, timeout=60)
        resp.raise_for_status()
        data = _payload_data(resp)
        video_id = data.get("video_id") or data.get("id")
        if not video_id:
            raise AvatarProviderError("HeyGen create response did not include video_id.")
        deadline = time.monotonic() + timeout_seconds
        status_data = data
        while time.monotonic() < deadline:
            status = str(status_data.get("status", "")).lower()
            if status in {"completed", "complete", "success"}:
                break
            if status in {"failed", "error"}:
                raise AvatarProviderError(
                    f"HeyGen render failed ({status_data.get('failure_code', 'unknown')}): "
                    f"{str(status_data.get('failure_message', 'no detail'))[:240]}"
                )
            time.sleep(poll_seconds)
            poll = http.get(f"{API}/v3/videos/{video_id}", headers=_headers(key), timeout=60)
            poll.raise_for_status()
            status_data = _payload_data(poll)
        else:
            raise AvatarProviderError(f"HeyGen render timed out for job {video_id}.")

        video_url = status_data.get("video_url")
        if not video_url:
            raise AvatarProviderError("HeyGen completed without a video_url.")
        # Only fetch HTTPS URLs. The signed URL is supplied by HeyGen and not logged.
        parsed = urlparse(video_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise AvatarProviderError("HeyGen returned an unsafe/invalid video URL.")
        download = http.get(video_url, stream=True, timeout=180)
        download.raise_for_status()
        target = Path(out_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with tmp.open("wb") as handle:
            for chunk in download.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        if not tmp.exists() or tmp.stat().st_size < 10_000:
            tmp.unlink(missing_ok=True)
            raise AvatarProviderError("Downloaded avatar video is empty or unexpectedly small.")
        tmp.replace(target)
        return {"video_id": video_id, "path": str(target), "duration": status_data.get("duration")}
    except requests.RequestException as exc:
        raise AvatarProviderError(f"HeyGen network/API request failed: {str(exc)[:240]}") from exc
