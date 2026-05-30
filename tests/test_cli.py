from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
        import os
        env = {"PYTHONPATH": str(PROJECT_ROOT / "src"), **os.environ}
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, "-m", "album_assetizer.cli", *args],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_stats_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = self.run_cli("--root", tmpdir, "stats")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["command"], "stats")
            self.assertIn("counts", payload)

    def test_stats_returns_zero_counts_on_empty_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = self.run_cli("--root", tmpdir, "stats")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["counts"]["total"], 0)

    def test_scan_command_finds_jpg(self) -> None:
        """扫描包含一张 jpg 的目录，应写入一条 pending 记录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个假 jpg 文件
            fake_jpg = Path(tmpdir) / "photo.jpg"
            fake_jpg.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)

            proc = self.run_cli("--root", tmpdir, "scan")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["command"], "scan")
            self.assertEqual(payload["scan"]["inserted"], 1)
            self.assertEqual(payload["counts"]["pending"], 1)

    def test_scan_ignores_non_image_files(self) -> None:
        """扫描只含 txt 文件的目录，应无新增记录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "notes.txt").write_text("hello")
            proc = self.run_cli("--root", tmpdir, "scan")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["scan"]["inserted"], 0)

    def test_export_writes_files(self) -> None:
        """export 命令应生成四个导出文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = self.run_cli("--root", tmpdir, "export")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["command"], "export")
            # 验证四个输出路径键都存在
            for key in ("results_jsonl", "results_csv", "failures_jsonl", "original_results_jsonl"):
                self.assertIn(key, payload)
            # 验证文件实际存在
            results_jsonl = Path(tmpdir) / payload["results_jsonl"]
            self.assertTrue(results_jsonl.exists())

    def test_run_requires_api_key(self) -> None:
        """run 命令在没有 API key 时应以非零退出码退出。"""
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {k: v for k, v in os.environ.items()
                   if k not in ("ALBUM_ASSETIZER_API_KEY",)}
            env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            result = subprocess.run(
                [sys.executable, "-m", "album_assetizer.cli", "--root", tmpdir, "run"],
                cwd=PROJECT_ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
