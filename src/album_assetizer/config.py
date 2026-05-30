from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 处理默认参数
DEFAULT_RPM = 60
DEFAULT_WORKERS = 4
DEFAULT_MODEL = "mimo-v2.5"
DEFAULT_MAX_IMAGE_EDGE = 1600
DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_JPEG_QUALITY = 88
DEFAULT_REQUEST_TIMEOUT = 180
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_BASE = 3.0
DEFAULT_RETRY_MAX = 90.0


@dataclass(slots=True)
class RuntimeConfig:
    # 路径配置
    root: Path
    workspace_dir: Path
    db_path: Path
    cache_dir: Path
    export_dir: Path
    log_path: Path
    # API 配置
    api_key: str
    base_url: str
    model: str
    text_refine_model: str | None
    # 并发与速率
    workers: int
    rpm: int
    # 重试配置
    max_attempts: int
    retry_base_seconds: float
    retry_max_seconds: float
    retry_once_immediately: bool
    retry_errors: bool
    # 图片处理
    max_image_edge: int
    max_image_bytes: int
    jpeg_quality: int
    request_timeout: int
    # 自动扩缩容
    auto_scale: bool
    scale_up_workers: int
    scale_up_rpm: int
    scale_up_after_successes: int
    scale_down_error_streak: int
    # 扫描行为
    ignore_dirs: set[str]
    rescan: bool
    include_done_in_stats: bool = True
