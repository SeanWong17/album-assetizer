"""相册文件扫描模块：发现素材、计算内容签名、写入数据库。"""

from __future__ import annotations

import logging
import os
import sqlite3
import zipfile
from pathlib import Path
from typing import Iterable

from album_assetizer.models import UnsupportedAssetError
from album_assetizer.runtime import build_content_sig, utc_now

# 支持的图片扩展名
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".bmp", ".heic", ".heif", ".dng", ".cr3",
}

# RAW 格式，需要 rawpy 解码
RAW_EXTENSIONS = {".dng", ".cr3"}

# Apple Live Photo 解包目录名
LIVP_DIR_NAME = "livp"

# 默认忽略的目录名
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".codex",
    ".agents",
    "__pycache__",
    "album_captioner",
    ".album-assetizer",
}


def should_ignore_dir(path: Path, cfg) -> bool:
    return path.name in cfg.ignore_dirs


def detect_livp_companion(zip_path: Path) -> tuple[str, str | None]:
    """从 LIVP zip 中找到图片文件名和可选的视频文件名。"""
    with zipfile.ZipFile(zip_path) as zf:
        image_name: str | None = None
        video_name: str | None = None
        for info in zf.infolist():
            lower = info.filename.lower()
            if lower.endswith((".heic", ".heif", ".jpg", ".jpeg", ".png")) and image_name is None:
                image_name = info.filename
            if lower.endswith((".mov", ".mp4")) and video_name is None:
                video_name = info.filename
        if image_name is None:
            raise UnsupportedAssetError(f"LIVP zip 中未找到图片文件: {zip_path}")
        return image_name, video_name


def iter_candidate_files(root: Path, cfg) -> Iterable[Path]:
    """递归遍历目录，跳过忽略目录，逐个 yield 候选文件路径。"""
    for current_root, dirnames, filenames in os.walk(root):
        current_path = Path(current_root)
        dirnames[:] = [name for name in dirnames if not should_ignore_dir(current_path / name, cfg)]
        for filename in filenames:
            yield current_path / filename


def scan_assets(conn: sqlite3.Connection, cfg) -> dict[str, int]:
    """扫描相册目录，将新增/变更素材写入数据库，返回统计信息。"""
    discovered = inserted = updated = unchanged = skipped = 0
    now = utc_now()
    root = cfg.root

    for path in iter_candidate_files(root, cfg):
        rel_path = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        asset_type: str | None = None
        source_format: str | None = None
        companion_video: str | None = None

        # 判断素材类型
        if path.parent.name == LIVP_DIR_NAME and suffix == ".zip":
            try:
                _, companion_video = detect_livp_companion(path)
            except (zipfile.BadZipFile, UnsupportedAssetError) as exc:
                logging.warning("跳过无效 LIVP zip %s: %s", rel_path, exc)
                skipped += 1
                continue
            asset_type = "livp"
            source_format = "livp_zip"
        elif suffix in IMAGE_EXTENSIONS:
            asset_type = "image"
            source_format = suffix.lstrip(".")
        else:
            skipped += 1
            continue

        stat = path.stat()
        size_bytes = stat.st_size
        mtime_ns = stat.st_mtime_ns
        content_sig = build_content_sig(Path(rel_path), size_bytes, mtime_ns)
        discovered += 1

        existing = conn.execute(
            "SELECT asset_id, content_sig, status FROM assets WHERE rel_path = ?",
            (rel_path,),
        ).fetchone()

        if existing is None:
            # 新素材，直接插入
            conn.execute(
                """
                INSERT INTO assets (
                    rel_path, abs_path, asset_type, source_format, size_bytes, mtime_ns,
                    content_sig, companion_video, status, attempts, discovered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (rel_path, str(path), asset_type, source_format, size_bytes, mtime_ns,
                 content_sig, companion_video, now, now),
            )
            inserted += 1
            continue

        if existing["content_sig"] == content_sig:
            # 文件未变更，跳过
            unchanged += 1
            continue

        # 文件已变更，重置为 pending
        conn.execute(
            """
            UPDATE assets
            SET abs_path = ?, asset_type = ?, source_format = ?, size_bytes = ?,
                mtime_ns = ?, content_sig = ?, companion_video = ?,
                status = 'pending', updated_at = ?, completed_at = NULL,
                prepared_width = NULL, prepared_height = NULL, prepared_bytes = NULL,
                result_json = NULL, usage_json = NULL, response_text = NULL,
                raw_response_json = NULL, last_error_type = NULL,
                last_error = NULL, last_traceback = NULL
            WHERE rel_path = ?
            """,
            (str(path), asset_type, source_format, size_bytes, mtime_ns,
             content_sig, companion_video, now, rel_path),
        )
        updated += 1

    conn.commit()
    return {
        "discovered": discovered,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
    }
