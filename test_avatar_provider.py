import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import avatar_provider
import analytics


class FakeResponse:
    def __init__(self, data=None, content=b"", status=200):
        self.data = data or {}
        self.content = content
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")
    def json(self):
        return self.data
    def iter_content(self, chunk_size=1024):
        yield self.content


class FakeSession:
    def __init__(self):
        self.posts = 0
        self.gets = 0
    def post(self, *args, **kwargs):
        self.posts += 1
        return FakeResponse({"data": {"video_id": "vid_123", "status": "processing"}})
    def get(self, url, **kwargs):
        self.gets += 1
        if "/v3/videos/" in url:
            return FakeResponse({"data": {"video_id": "vid_123", "status": "completed",
                                          "video_url": "https://cdn.example/video.mp4"}})
        return FakeResponse(content=b"x" * 12000)


class HeyGenProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "HEYGEN_API_KEY": "test-key",
            "HEYGEN_AVATAR_ID": "avatar-id",
            "HEYGEN_VOICE_ID": "voice-id",
            "HEYGEN_CONFIRM_BILLING": "true",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_billing_confirmation_is_required(self):
        with patch.dict(os.environ, {"HEYGEN_CONFIRM_BILLING": "false"}):
            with self.assertRaises(avatar_provider.AvatarProviderError):
                avatar_provider._config()

    def test_missing_avatar_settings_are_rejected(self):
        with patch.dict(os.environ, {"HEYGEN_AVATAR_ID": ""}):
            with self.assertRaises(avatar_provider.AvatarProviderError):
                avatar_provider._config()

    def test_scene_generation_downloads_completed_video(self):
        fake = FakeSession()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "scene.mp4"
            result = avatar_provider.render_scene(
                "Namaskar, aaj bazaar ka update.", target,
                session=fake, poll_seconds=0, timeout_seconds=5
            )
            self.assertEqual(result["video_id"], "vid_123")
            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size, 10000)
            self.assertEqual(fake.posts, 1)
            self.assertGreaterEqual(fake.gets, 2)

    def test_analytics_metric_columns_are_mapped_in_api_order(self):
        mapped = analytics._map_analytics_row(["vid", 100, 12.5, 42, 73.2, 4, 88])
        self.assertEqual(mapped["minutes"], 12.5)
        self.assertEqual(mapped["avg_view_sec"], 42)
        self.assertEqual(mapped["avg_view_pct"], 73.2)
        self.assertEqual(mapped["subs_gained"], 4)
        self.assertEqual(mapped["engaged_views"], 88)

    def test_non_https_download_url_is_rejected(self):
        class BadUrlSession(FakeSession):
            def get(self, url, **kwargs):
                if "/v3/videos/" in url:
                    return FakeResponse({"data": {"status": "completed", "video_url": "http://bad.test/a.mp4"}})
                return super().get(url, **kwargs)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(avatar_provider.AvatarProviderError):
                avatar_provider.render_scene("test", Path(td) / "x.mp4",
                                             session=BadUrlSession(), poll_seconds=0, timeout_seconds=5)


if __name__ == "__main__":
    unittest.main()
