from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from album_assetizer.db import create_connection, init_db
from album_assetizer.exporters import export_csv, export_jsonl
from album_assetizer.runtime import utc_now


class ExporterTests(unittest.TestCase):
    def test_export_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.jsonl"
            export_jsonl([{"a": 1, "b": "x"}], path)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["a"], 1)

    def test_export_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.csv"
            export_csv([{"a": 1, "b": "x"}], path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("a,b", text)
            self.assertIn("1,x", text)

    def test_export_asset_results_includes_metadata_fields(self) -> None:
        from album_assetizer.exporters import export_asset_results

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            conn = create_connection(root / "state.db")
            init_db(conn)
            now = utc_now()
            conn.execute(
                """
                INSERT INTO assets (
                    rel_path, abs_path, asset_type, source_format, size_bytes, mtime_ns,
                    content_sig, companion_video, status, attempts, discovered_at, updated_at,
                    completed_at, taken_at, gps_lat, gps_lng, metadata_json, result_json, usage_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "photo.jpg",
                    str(root / "photo.jpg"),
                    "image",
                    "jpg",
                    10,
                    1,
                    "sig",
                    None,
                    "done",
                    1,
                    now,
                    now,
                    now,
                    "2024-05-01T08:30:00+08:00",
                    36.1234567,
                    117.1234567,
                    json.dumps({"source_kind": "image_exif"}, ensure_ascii=False),
                    json.dumps({"caption_short": "x"}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            conn.commit()

            paths = export_asset_results(conn, root / "exports")
            row = json.loads(paths["jsonl"].read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["taken_at"], "2024-05-01T08:30:00+08:00")
            self.assertEqual(row["gps_lat"], 36.1234567)
            self.assertEqual(row["gps_lng"], 117.1234567)
            self.assertEqual(row["metadata"]["source_kind"], "image_exif")
            csv_text = paths["csv"].read_text(encoding="utf-8")
            self.assertIn("taken_at", csv_text)
            self.assertIn("gps_lat", csv_text)
            conn.close()


if __name__ == "__main__":
    unittest.main()
