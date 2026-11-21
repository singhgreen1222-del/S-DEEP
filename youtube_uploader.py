#!/usr/bin/env python3
"""
S DEEP & CreatorAuto AI - 100% Free YouTube Auto-Uploader & Scheduler
======================================================================
Uploads rendered MP4 videos + 1280x720 thumbnails to YouTube using
YouTube Data API v3 with OAuth 2.0 and schedules them via `publishAt` (IST).

Zero paid tools. Runs on GitHub Actions Free Tier or local/Termux.
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

IST = timezone(timedelta(hours=5, minutes=30))


def get_youtube_service():
    client_id = os.environ["YT_CLIENT_ID"]
    client_secret = os.environ["YT_CLIENT_SECRET"]
    refresh_token = os.environ["YT_REFRESH_TOKEN"]
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
        ],
    )
    return build("youtube", "v3", credentials=creds)


def upload_and_schedule(youtube, video_path: str, title: str, description: str, tags: list, publish_at_iso: str, thumbnail_path: str = None, is_short: bool = False):
    if is_short and "#Shorts" not in title and "#Shorts" not in description:
        description = f"{description}\n\n#Shorts"

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:15],
            "categoryId": "22" if not is_short else "27",  # 27 = Education
            "defaultLanguage": "hi",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at_iso,  # ISO 8601 UTC/IST e.g. 2026-11-23T11:00:00+05:30
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"Uploaded & scheduled video ID: {video_id} for {publish_at_iso}")

    if thumbnail_path and os.path.exists(thumbnail_path):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
        ).execute()
        print(f"Thumbnail set for {video_id}")

    return f"https://youtu.be/{video_id}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Auto-Uploader & Scheduler")
    parser.add_argument("--manifest", required=True, help="JSON list of rendered videos to upload")
    args = parser.parse_args()

    yt = get_youtube_service()
    items = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    results = []
    for item in items:
        url = upload_and_schedule(
            yt,
            video_path=item["video_path"],
            title=item["title"],
            description=item["description"],
            tags=item.get("tags", []),
            publish_at_iso=item["publish_at"],
            thumbnail_path=item.get("thumbnail_path"),
            is_short=item.get("is_short", False),
        )
        results.append({"title": item["title"], "url": url, "publish_at": item["publish_at"]})

    print(json.dumps(results, indent=2, ensure_ascii=False))
