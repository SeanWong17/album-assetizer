from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from album_assetizer.exporters import export_csv, export_jsonl


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


if __name__ == "__main__":
    unittest.main()
