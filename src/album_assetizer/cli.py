from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from album_assetizer.config import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MAX_IMAGE_EDGE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_RETRY_BASE,
    DEFAULT_RETRY_MAX,
    DEFAULT_RPM,
    DEFAULT_WORKERS,
    RuntimeConfig,
)
from album_assetizer.db import create_connection, get_status_counts, init_db, mark_running_as_pending
from album_assetizer.exporters import export_asset_results
from album_assetizer.runtime import display_path, ensure_dir, load_env_file
from album_assetizer.scanner import DEFAULT_IGNORE_DIRS, scan_assets


def setup_logging(log_path: Path) -> None:
    """配置控制台 + 滚动文件双输出日志。"""
    ensure_dir(log_path.parent)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

    # 单文件最大 5MB，保留 3 个备份
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(threadName)s | %(message)s")
    )

    root_logger.addHandler(console)
    root_logger.addHandler(file_handler)


def build_arg_parser() -> argparse.ArgumentParser:
    from album_assetizer import __version__

    parser = argparse.ArgumentParser(
        prog="album-assetizer",
        description="Generate structured semantic assets from personal albums.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", default=".", help="相册根目录")
    parser.add_argument("--workspace-dir", default=".album-assetizer", help="工作目录（存放数据库、日志、导出文件）")
    parser.add_argument("--env-file", default=".album-assetizer/.env", help=".env 配置文件路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="视觉理解模型")
    parser.add_argument("--text-refine-model", default=None, help="可选的文本精修模型")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="并发工作线程数")
    parser.add_argument("--rpm", type=int, default=DEFAULT_RPM, help="每分钟最大请求数")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help="单个素材最大调度次数（跨运行累计）")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help="单次调度内 HTTP 级别最大重试次数")
    parser.add_argument("--max-image-edge", type=int, default=DEFAULT_MAX_IMAGE_EDGE, help="图片最长边缩放上限（像素）")
    parser.add_argument("--max-image-bytes", type=int, default=DEFAULT_MAX_IMAGE_BYTES, help="预处理后图片最大字节数")
    parser.add_argument("--jpeg-quality", type=int, default=DEFAULT_JPEG_QUALITY, help="JPEG 压缩质量")
    parser.add_argument("--request-timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT, help="API 请求超时（秒）")
    parser.add_argument("--retry-base-seconds", type=float, default=DEFAULT_RETRY_BASE, help="重试退避基础秒数")
    parser.add_argument("--retry-max-seconds", type=float, default=DEFAULT_RETRY_MAX, help="重试退避最大秒数")
    parser.add_argument("--retry-errors", action="store_true", help="本次运行包含之前失败的素材")
    parser.add_argument("--no-rescan", action="store_true", help="跳过 run 前的目录扫描")
    parser.add_argument("--ignore-dir", action="append", default=[], help="额外忽略的目录名（可多次指定）")
    parser.add_argument("--auto-scale", action="store_true", help="稳定后自动提升并发，连续失败后自动降回")
    parser.add_argument("--scale-up-workers", type=int, default=3, help="扩容后的工作线程数")
    parser.add_argument("--scale-up-rpm", type=int, default=60, help="扩容后的 RPM")
    parser.add_argument("--scale-up-after-successes", type=int, default=30, help="成功多少次后触发扩容")
    parser.add_argument("--scale-down-error-streak", type=int, default=3, help="连续失败多少次后触发缩容")
    parser.add_argument("--retry-once-immediately", action="store_true", help="同一次运行内对可重试失败立即重试一次")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scan", help="扫描素材文件到本地状态库")
    subparsers.add_parser("run", help="扫描并处理待标注素材")
    subparsers.add_parser("refine-done", help="对已完成结果进行二轮文本精修")
    sync_metadata = subparsers.add_parser("sync-metadata", help="读取 EXIF/GPS 元数据并写入本地状态库")
    sync_metadata.add_argument("--all", action="store_true", help="重跑全部素材，不只处理缺失元数据的记录")
    sync_metadata.add_argument("--limit", type=int, default=None, help="限制本次处理的素材数量")
    subparsers.add_parser("stats", help="查看当前处理统计")
    subparsers.add_parser("export", help="导出 JSONL/CSV/失败列表")

    smoke_text = subparsers.add_parser("smoke-text", help="文本连通性探测（不需要图片）")
    smoke_text.add_argument("--prompt", default=None, help="自定义探测提示词")
    smoke_text.add_argument("--probe-model", default=None, help="覆盖探测用模型")

    smoke_image = subparsers.add_parser("smoke-image", help="单图探测（验证完整流程）")
    smoke_image.add_argument("--path", required=True, help="探测用图片路径（相对或绝对）")

    return parser


def resolve_config(args: argparse.Namespace) -> RuntimeConfig:
    """从命令行参数和 .env 文件解析运行时配置。"""
    root = Path(args.root).resolve()
    workspace_dir = Path(args.workspace_dir)
    if not workspace_dir.is_absolute():
        workspace_dir = (root / workspace_dir).resolve()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()

    env_values = load_env_file(env_file)
    api_key = (os.environ.get("ALBUM_ASSETIZER_API_KEY")
               or env_values.get("ALBUM_ASSETIZER_API_KEY") or "")
    base_url = (os.environ.get("ALBUM_ASSETIZER_BASE_URL")
                or env_values.get("ALBUM_ASSETIZER_BASE_URL") or "")

    # 需要 API 的命令必须有 key
    if not api_key and args.command in {"run", "refine-done", "smoke-text", "smoke-image"}:
        raise SystemExit(
            "缺少 ALBUM_ASSETIZER_API_KEY，请在环境变量或 .album-assetizer/.env 中配置"
        )

    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    ignore_dirs.update(args.ignore_dir or [])

    return RuntimeConfig(
        root=root,
        workspace_dir=workspace_dir,
        db_path=workspace_dir / "state" / "album_assetizer.db",
        cache_dir=workspace_dir / "cache",
        export_dir=workspace_dir / "exports",
        log_path=workspace_dir / "logs" / "album_assetizer.log",
        api_key=api_key,
        base_url=base_url,
        model=args.model,
        text_refine_model=args.text_refine_model,
        workers=max(1, args.workers),
        rpm=max(1, args.rpm),
        max_attempts=max(1, args.max_attempts),
        max_retries=max(0, args.max_retries),
        max_image_edge=max(256, args.max_image_edge),
        max_image_bytes=max(256 * 1024, args.max_image_bytes),
        jpeg_quality=max(45, min(95, args.jpeg_quality)),
        request_timeout=max(30, args.request_timeout),
        retry_base_seconds=max(1.0, args.retry_base_seconds),
        retry_max_seconds=max(5.0, args.retry_max_seconds),
        auto_scale=args.auto_scale,
        scale_up_workers=max(1, args.scale_up_workers),
        scale_up_rpm=max(1, args.scale_up_rpm),
        scale_up_after_successes=max(1, args.scale_up_after_successes),
        scale_down_error_streak=max(1, args.scale_down_error_streak),
        retry_once_immediately=args.retry_once_immediately,
        ignore_dirs=ignore_dirs,
        rescan=not args.no_rescan,
        retry_errors=args.retry_errors,
    )


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    cfg = resolve_config(args)

    ensure_dir(cfg.workspace_dir)
    ensure_dir(cfg.cache_dir)
    ensure_dir(cfg.export_dir)
    setup_logging(cfg.log_path)

    logging.info(
        "root=%s workspace=%s model=%s text_refine_model=%s workers=%s rpm=%s",
        cfg.root, cfg.workspace_dir, cfg.model, cfg.text_refine_model, cfg.workers, cfg.rpm,
    )

    # smoke 命令不需要数据库
    if args.command == "smoke-text":
        from album_assetizer.api import build_client, call_text_smoke
        from album_assetizer.runtime import stable_json_dumps
        probe_model = args.probe_model or cfg.text_refine_model or cfg.model
        logging.info("文本探测开始 | model=%s", probe_model)
        client = build_client(cfg)
        try:
            payload, text, usage_json, _ = call_text_smoke(
                client=client, model=probe_model,
                timeout=cfg.request_timeout, prompt=args.prompt,
            )
        finally:
            client.close()
        logging.info("文本探测成功 | usage=%s", usage_json)
        print(stable_json_dumps({"model": probe_model, "result": payload, "raw_text": text}))
        return 0

    if args.command == "smoke-image":
        from album_assetizer.api import ApiCapabilities, build_client, call_model_with_fallback
        from album_assetizer.image_prep import prepare_asset_image
        from album_assetizer.models import AssetRecord
        from album_assetizer.runtime import stable_json_dumps
        from album_assetizer.scanner import LIVP_DIR_NAME

        probe_path = Path(args.path)
        if not probe_path.is_absolute():
            probe_path = (cfg.root / probe_path).resolve()
        if not probe_path.exists():
            raise SystemExit(f"图片路径不存在: {probe_path}")

        is_livp = probe_path.parent.name == LIVP_DIR_NAME and probe_path.suffix.lower() == ".zip"
        asset = AssetRecord(
            asset_id=0,
            rel_path=probe_path.relative_to(cfg.root).as_posix(),
            abs_path=probe_path,
            asset_type="livp" if is_livp else "image",
            source_format="livp_zip" if is_livp else probe_path.suffix.lower().lstrip("."),
            size_bytes=probe_path.stat().st_size,
            mtime_ns=probe_path.stat().st_mtime_ns,
            companion_video=None,
            status="pending",
            attempts=0,
            content_sig="probe",
        )
        capabilities = ApiCapabilities()
        prepared = prepare_asset_image(asset, cfg)
        client = build_client(cfg)
        try:
            parsed, text, usage_json, _ = call_model_with_fallback(
                client=client, cfg=cfg, prepared=prepared, capabilities=capabilities,
            )
        finally:
            client.close()
        logging.info(
            "图片探测成功 | path=%s size=%sx%s prepared_bytes=%s usage=%s",
            asset.rel_path, prepared.width, prepared.height, len(prepared.jpeg_bytes), usage_json,
        )
        print(stable_json_dumps({"path": asset.rel_path, "result": parsed, "raw_text": text}))
        return 0

    # 其余命令需要数据库
    conn = create_connection(cfg.db_path)
    try:
        init_db(conn)

        if args.command == "scan":
            stats = scan_assets(conn, cfg)
            logging.info("扫描完成: %s", stats)
            counts = get_status_counts(conn)
            print(json.dumps({"command": "scan", "scan": stats, "counts": counts}, ensure_ascii=False))

        elif args.command == "run":
            from album_assetizer.processor import process_assets
            stale = mark_running_as_pending(conn)
            if stale:
                logging.info("恢复 %s 个中断任务为 pending", stale)
            if cfg.rescan:
                stats = scan_assets(conn, cfg)
                logging.info("运行前扫描: %s", stats)
            counts = get_status_counts(conn)
            logging.info(
                "开始处理 | total=%s pending=%s done=%s error=%s",
                counts["total"], counts["pending"], counts["done"], counts["error"],
            )
            process_assets(conn, cfg)
            counts = get_status_counts(conn)
            print(json.dumps({"command": "run", "counts": counts}, ensure_ascii=False))

        elif args.command == "refine-done":
            from album_assetizer.processor import refine_done_results
            refine_done_results(conn, cfg)
            counts = get_status_counts(conn)
            print(json.dumps({"command": "refine-done", "counts": counts}, ensure_ascii=False))

        elif args.command == "sync-metadata":
            from album_assetizer.metadata import sync_asset_metadata
            stats = sync_asset_metadata(
                conn,
                only_missing=not args.all,
                limit=args.limit,
            )
            counts = get_status_counts(conn)
            print(json.dumps({"command": "sync-metadata", "sync": stats, "counts": counts}, ensure_ascii=False))

        elif args.command == "stats":
            counts = get_status_counts(conn)
            print(json.dumps({"command": "stats", "counts": counts}, ensure_ascii=False))

        elif args.command == "export":
            paths = export_asset_results(conn, cfg.export_dir)
            print(json.dumps(
                {
                    "command": "export",
                    "results_jsonl": display_path(paths["jsonl"], cfg.root),
                    "results_csv": display_path(paths["csv"], cfg.root),
                    "failures_jsonl": display_path(paths["failures"], cfg.root),
                    "original_results_jsonl": display_path(paths["original_jsonl"], cfg.root),
                },
                ensure_ascii=False,
            ))

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
