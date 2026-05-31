"""关键路径单元测试：parse_result_json、classify_exception、RateLimiter、detect_livp_companion。"""

from __future__ import annotations

import io
import sys
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from album_assetizer.api import parse_result_json
from album_assetizer.models import StopRequested, UnsupportedAssetError
from album_assetizer.rate_limiter import RateLimiter
from album_assetizer.scanner import detect_livp_companion
from album_assetizer.worker import classify_exception


class TestParseResultJson(unittest.TestCase):
    """parse_result_json 的脏输出兼容、字段归一化、截断与类型纠正。"""

    def _minimal_valid(self, **overrides) -> str:
        import json
        data = {
            "caption_short": "A photo",
            "caption_long": "A longer description",
            "scene": "outdoor",
            "tags": ["nature"],
            "main_subjects": ["tree"],
            "activities": [],
            "style_labels": [],
            "quality_flags": [],
            "safety_flags": [],
            "ocr_text": "",
            "contains_text": False,
            "people_count": 0,
            "confidence": 0.9,
        }
        data.update(overrides)
        return json.dumps(data)

    def test_clean_json(self):
        result = parse_result_json(self._minimal_valid())
        self.assertEqual(result["caption_short"], "A photo")
        self.assertEqual(result["confidence"], 0.9)

    def test_json_wrapped_in_markdown_code_block(self):
        raw = "```json\n" + self._minimal_valid() + "\n```"
        result = parse_result_json(raw)
        self.assertEqual(result["caption_short"], "A photo")

    def test_json_with_leading_garbage(self):
        raw = "Here is the result:\n" + self._minimal_valid()
        result = parse_result_json(raw)
        self.assertEqual(result["caption_short"], "A photo")

    def test_duplicate_tags_deduplicated(self):
        result = parse_result_json(self._minimal_valid(tags=["Nature", "nature", "NATURE", "sky"]))
        self.assertEqual(result["tags"], ["Nature", "sky"])

    def test_tags_limited_to_18(self):
        tags = [f"tag{i}" for i in range(30)]
        result = parse_result_json(self._minimal_valid(tags=tags))
        self.assertEqual(len(result["tags"]), 18)

    def test_ocr_text_truncated_to_300(self):
        long_text = "x" * 500
        result = parse_result_json(self._minimal_valid(ocr_text=long_text))
        self.assertEqual(len(result["ocr_text"]), 300)

    def test_confidence_clamped(self):
        result = parse_result_json(self._minimal_valid(confidence=1.5))
        self.assertEqual(result["confidence"], 1.0)
        result = parse_result_json(self._minimal_valid(confidence=-0.5))
        self.assertEqual(result["confidence"], 0.0)

    def test_people_count_non_numeric_defaults_to_minus_one(self):
        result = parse_result_json(self._minimal_valid(people_count="many"))
        self.assertEqual(result["people_count"], -1)

    def test_contains_text_coerced_to_bool(self):
        result = parse_result_json(self._minimal_valid(contains_text=1))
        self.assertIs(result["contains_text"], True)
        result = parse_result_json(self._minimal_valid(contains_text=0))
        self.assertIs(result["contains_text"], False)

    def test_embedding_text_generated(self):
        result = parse_result_json(self._minimal_valid())
        self.assertIn("embedding_text", result)
        self.assertIn("A photo", result["embedding_text"])

    def test_invalid_json_raises(self):
        with self.assertRaises((ValueError, Exception)):
            parse_result_json("not json at all {{{")


class TestClassifyException(unittest.TestCase):
    """worker.classify_exception 的错误分类正确性。"""

    def test_unsupported_asset_not_retryable(self):
        error_type, retryable = classify_exception(UnsupportedAssetError("bad"))
        self.assertEqual(error_type, "unsupported_asset")
        self.assertFalse(retryable)

    def test_rate_limit_retryable(self):
        from openai import RateLimitError
        exc = RateLimitError.__new__(RateLimitError)
        exc.message = "rate limited"
        error_type, retryable = classify_exception(exc)
        self.assertEqual(error_type, "rate_limit")
        self.assertTrue(retryable)

    def test_api_connection_error_retryable(self):
        from openai import APIConnectionError
        exc = APIConnectionError.__new__(APIConnectionError)
        exc.message = "connection failed"
        error_type, retryable = classify_exception(exc)
        self.assertEqual(error_type, "api_connection_error")
        self.assertTrue(retryable)

    def test_api_error_500_retryable(self):
        from openai import APIError
        exc = APIError.__new__(APIError)
        exc.status_code = 500
        exc.message = "server error"
        error_type, retryable = classify_exception(exc)
        self.assertEqual(error_type, "api_error_500")
        self.assertTrue(retryable)

    def test_api_error_400_not_retryable(self):
        from openai import APIError
        exc = APIError.__new__(APIError)
        exc.status_code = 400
        exc.message = "bad request"
        error_type, retryable = classify_exception(exc)
        self.assertEqual(error_type, "api_error_400")
        self.assertFalse(retryable)

    def test_bad_zip_not_retryable(self):
        import zipfile
        error_type, retryable = classify_exception(zipfile.BadZipFile("corrupt"))
        self.assertEqual(error_type, "invalid_livp_zip")
        self.assertFalse(retryable)

    def test_unknown_exception_not_retryable(self):
        error_type, retryable = classify_exception(RuntimeError("unknown"))
        self.assertEqual(error_type, "RuntimeError")
        self.assertFalse(retryable)


class TestRateLimiter(unittest.TestCase):
    """RateLimiter 的节流正确性。"""

    def test_first_acquire_immediate(self):
        stop = threading.Event()
        rl = RateLimiter(60, stop)
        start = time.monotonic()
        rl.acquire()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)

    def test_respects_rpm_interval(self):
        stop = threading.Event()
        rl = RateLimiter(600, stop)  # 10 per second, interval = 0.1s
        rl.acquire()
        start = time.monotonic()
        rl.acquire()
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.08)  # allow small timing tolerance

    def test_stop_event_raises(self):
        stop = threading.Event()
        rl = RateLimiter(1, stop)  # 1 per minute
        rl.acquire()  # first one passes
        stop.set()
        with self.assertRaises(StopRequested):
            rl.acquire()

    def test_set_rpm_changes_interval(self):
        stop = threading.Event()
        rl = RateLimiter(6000, stop)  # 100 per second, interval = 0.01s
        rl.acquire()
        rl.acquire()
        rl.set_rpm(60)  # 1 per second — next acquire sets _next_allowed_at with new interval
        rl.acquire()  # passes quickly but schedules next slot at now + 1.0s
        start = time.monotonic()
        rl.acquire()  # this one should wait ~1.0s
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.9)

    def test_concurrent_acquires_serialized(self):
        stop = threading.Event()
        rl = RateLimiter(600, stop)  # 0.1s interval
        timestamps = []

        def worker():
            rl.acquire()
            timestamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(timestamps), 5)
        timestamps.sort()
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            self.assertGreaterEqual(gap, 0.05)


class TestDetectLivpCompanion(unittest.TestCase):
    """detect_livp_companion 支持 Path 和 ZipFile 两种输入。"""

    def _make_livp_zip(self, tmpdir: Path, image_name="photo.heic", video_name="video.mov"):
        zip_path = tmpdir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(image_name, b"fake image data")
            if video_name:
                zf.writestr(video_name, b"fake video data")
        return zip_path

    def test_with_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = self._make_livp_zip(Path(tmpdir))
            image, video = detect_livp_companion(zip_path)
            self.assertEqual(image, "photo.heic")
            self.assertEqual(video, "video.mov")

    def test_with_zipfile_object(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = self._make_livp_zip(Path(tmpdir))
            with zipfile.ZipFile(zip_path) as zf:
                image, video = detect_livp_companion(zf)
            self.assertEqual(image, "photo.heic")
            self.assertEqual(video, "video.mov")

    def test_no_image_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "empty.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("readme.txt", b"no image here")
            with self.assertRaises(UnsupportedAssetError):
                detect_livp_companion(zip_path)

    def test_no_video_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = self._make_livp_zip(Path(tmpdir), video_name=None)
            image, video = detect_livp_companion(zip_path)
            self.assertEqual(image, "photo.heic")
            self.assertIsNone(video)


# PLACEHOLDER_TESTS_PART2

if __name__ == "__main__":
    unittest.main()
