from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def stable_json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def display_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return path.name


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def default_mime_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    if suffix in {".heic", ".heif"}:
        return "image/heic"
    return "image/jpeg"


def build_content_sig(path: Path, size_bytes: int, mtime_ns: int) -> str:
    return sha1_text(f"{path.as_posix()}|{size_bytes}|{mtime_ns}")


def load_env_file(path: Path) -> dict[str, str]:
    """从 .env 文件加载 KEY=VALUE 配置，忽略注释和空行。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values
