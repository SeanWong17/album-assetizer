"""数据类与异常定义。独立模块，避免 db.py 与 worker.py 之间的循环导入。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class StopRequested(Exception):
    """收到停止信号时抛出，用于中断工作线程。"""


class UnsupportedAssetError(Exception):
    """不支持的素材格式或损坏文件。"""


@dataclass(slots=True)
class AssetRecord:
    """数据库中一条素材记录的内存表示。"""
    asset_id: int
    rel_path: str
    abs_path: Path
    asset_type: str
    source_format: str
    size_bytes: int
    mtime_ns: int
    companion_video: str | None
    status: str
    attempts: int
    content_sig: str


@dataclass(slots=True)
class RefineRecord:
    """待精修的已完成素材记录。"""
    asset_id: int
    rel_path: str
    draft_json: str


@dataclass(slots=True)
class PreparedImage:
    """经过预处理后的图片，准备发送给 API。"""
    jpeg_bytes: bytes
    width: int
    height: int
    mime_type: str
    source_note: str


@dataclass(slots=True)
class WorkerResult:
    """工作线程处理单个素材后的结果。"""
    ok: bool
    asset_id: int
    rel_path: str
    prepared_width: int | None = None
    prepared_height: int | None = None
    prepared_bytes: int | None = None
    result_json: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    response_text: str | None = None
    raw_response_json: dict[str, Any] | None = None
    model_used: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    traceback_text: str | None = None
    retryable: bool = False
