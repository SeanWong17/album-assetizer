"""处理编排模块：并发处理素材、自动扩缩容、优雅停机。"""

from __future__ import annotations

import json
import logging
import queue
import signal
import sqlite3
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from tqdm import tqdm

from album_assetizer.api import ApiCapabilities
from album_assetizer.config import RuntimeConfig
from album_assetizer.db import (
    fetch_assets_for_processing,
    fetch_assets_for_refinement,
    get_status_counts,
    mark_asset_running,
    record_failure,
    record_success,
    requeue_asset_after_failure,
    update_refined_result,
)
from album_assetizer.models import AssetRecord, RefineRecord, StopRequested, WorkerResult
from album_assetizer.rate_limiter import RateLimiter
from album_assetizer.worker import worker_process_asset, worker_refine_record


def process_assets(conn: sqlite3.Connection, cfg: RuntimeConfig) -> None:
    """并发处理所有待处理素材，支持自动扩缩容和优雅停机。"""
    assets = fetch_assets_for_processing(conn, cfg)
    if not assets:
        counts = get_status_counts(conn)
        logging.info(
            "没有待处理素材。total=%s done=%s error=%s pending=%s",
            counts["total"], counts["done"], counts["error"], counts["pending"],
        )
        return

    stop_event = threading.Event()
    capabilities = ApiCapabilities()
    rate_limiter = RateLimiter(cfg.rpm, stop_event)
    current_workers = cfg.workers
    submitted = successes = failures = requeued = consecutive_errors = 0
    scaled_up = scaled_down = False
    started_at = time.monotonic()
    future_map: dict[Future[WorkerResult], AssetRecord] = {}
    pending_queue: queue.SimpleQueue[AssetRecord] = queue.SimpleQueue()
    for asset in assets:
        pending_queue.put(asset)

    def handle_signal(signum: int, frame: Any) -> None:
        stop_event.set()
        logging.warning("收到信号 %s，等待在途任务完成后停止", signum)

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    total = len(assets)
    progress = tqdm(total=total, unit="img", desc="标注中", dynamic_ncols=True)

    try:
        with ThreadPoolExecutor(max_workers=cfg.workers, thread_name_prefix="caption-worker") as executor:
            # 初始填满工作槽
            while not stop_event.is_set() and len(future_map) < current_workers:
                try:
                    asset = pending_queue.get_nowait()
                except queue.Empty:
                    break
                mark_asset_running(conn, asset)
                future = executor.submit(worker_process_asset, asset, cfg, rate_limiter, stop_event, capabilities)
                future_map[future] = asset
                submitted += 1

            while future_map:
                done, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED, timeout=1.0)
                if not done:
                    continue

                for future in done:
                    asset = future_map.pop(future)
                    result = future.result()
                    progress.update(1)

                    if result.ok:
                        record_success(conn, asset.asset_id, result)
                        successes += 1
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                        # 同一次运行内立即重试一次
                        if (cfg.retry_once_immediately and result.retryable
                                and asset.attempts < max(1, cfg.max_attempts - 1)):
                            requeue_asset_after_failure(conn, asset.asset_id, result)
                            retry_asset = AssetRecord(
                                asset_id=asset.asset_id,
                                rel_path=asset.rel_path,
                                abs_path=asset.abs_path,
                                asset_type=asset.asset_type,
                                source_format=asset.source_format,
                                size_bytes=asset.size_bytes,
                                mtime_ns=asset.mtime_ns,
                                companion_video=asset.companion_video,
                                status="pending",
                                attempts=asset.attempts + 1,
                                content_sig=asset.content_sig,
                            )
                            pending_queue.put(retry_asset)
                            requeued += 1
                            logging.warning("重新入队 %s | %s | %s", asset.rel_path, result.error_type, result.error_message)
                        else:
                            record_failure(conn, asset.asset_id, result)
                            failures += 1
                            logging.error("失败 %s | %s | %s", asset.rel_path, result.error_type, result.error_message)

                    # 自动扩容：稳定后提升并发和速率
                    if (cfg.auto_scale and not scaled_up
                            and successes >= cfg.scale_up_after_successes and failures <= 1):
                        current_workers = max(current_workers, cfg.scale_up_workers)
                        rate_limiter.set_rpm(max(rate_limiter.get_rpm(), cfg.scale_up_rpm))
                        scaled_up = True
                        logging.info(
                            "自动扩容 | workers=%s rpm=%s after_successes=%s",
                            current_workers, rate_limiter.get_rpm(), successes,
                        )

                    # 自动缩容：连续失败后降回保守配置
                    if (cfg.auto_scale and scaled_up and not scaled_down
                            and consecutive_errors >= cfg.scale_down_error_streak):
                        current_workers = min(current_workers, cfg.workers)
                        rate_limiter.set_rpm(min(rate_limiter.get_rpm(), cfg.rpm))
                        scaled_down = True
                        logging.warning(
                            "自动缩容 | workers=%s rpm=%s after_consecutive_errors=%s",
                            current_workers, rate_limiter.get_rpm(), consecutive_errors,
                        )

                    elapsed = max(1e-6, time.monotonic() - started_at)
                    rate = (successes + failures) / elapsed * 60.0
                    progress.set_postfix(
                        ok=successes, err=failures,
                        rpm=f"{rate:.1f}", wrk=current_workers, cap=rate_limiter.get_rpm(),
                    )

                    # 补充新任务填满工作槽
                    while not stop_event.is_set() and len(future_map) < current_workers:
                        try:
                            next_asset = pending_queue.get_nowait()
                        except queue.Empty:
                            break
                        mark_asset_running(conn, next_asset)
                        next_future = executor.submit(
                            worker_process_asset, next_asset, cfg, rate_limiter, stop_event, capabilities,
                        )
                        future_map[next_future] = next_asset
                        submitted += 1
    finally:
        progress.close()
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

    counts = get_status_counts(conn)
    logging.info(
        "处理完成。submitted=%s ok=%s error=%s requeued=%s total=%s done=%s pending=%s",
        submitted, successes, failures, requeued,
        counts["total"], counts["done"], counts["pending"],
    )


def refine_done_results(conn: sqlite3.Connection, cfg: RuntimeConfig) -> None:
    """对所有已完成但未精修的素材进行二轮文本精修。"""
    if not cfg.text_refine_model:
        raise SystemExit("refine-done 需要指定 --text-refine-model")

    records = fetch_assets_for_refinement(conn)
    if not records:
        logging.info("没有待精修的已完成记录")
        return

    stop_event = threading.Event()
    rate_limiter = RateLimiter(cfg.rpm, stop_event)
    current_workers = cfg.workers
    submitted = refined = failures = 0
    started_at = time.monotonic()
    future_map: dict[Future[WorkerResult], RefineRecord] = {}
    pending_queue: queue.SimpleQueue[RefineRecord] = queue.SimpleQueue()
    for record in records:
        pending_queue.put(record)

    def handle_signal(signum: int, frame: Any) -> None:
        stop_event.set()
        logging.warning("收到信号 %s，等待在途精修任务完成后停止", signum)

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logging.info(
        "精修队列 | total=%s workers=%s rpm=%s model=%s",
        len(records), current_workers, rate_limiter.get_rpm(), cfg.text_refine_model,
    )
    progress = tqdm(total=len(records), unit="img", desc="精修中", dynamic_ncols=True)

    try:
        with ThreadPoolExecutor(max_workers=cfg.workers, thread_name_prefix="refine-worker") as executor:
            while not stop_event.is_set() and len(future_map) < current_workers:
                try:
                    record = pending_queue.get_nowait()
                except queue.Empty:
                    break
                future = executor.submit(worker_refine_record, record, cfg, rate_limiter, stop_event)
                future_map[future] = record
                submitted += 1

            while future_map:
                done, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED, timeout=1.0)
                if not done:
                    continue

                for future in done:
                    record = future_map.pop(future)
                    result = future.result()
                    draft = json.loads(record.draft_json)
                    progress.update(1)

                    if result.ok:
                        update_refined_result(
                            conn=conn,
                            asset_id=record.asset_id,
                            original_result=draft,
                            refined_result=result.result_json or {},
                            model_used=cfg.text_refine_model,
                            usage_json=result.usage or {},
                            response_text=result.response_text or "",
                            raw_response_json=result.raw_response_json or {},
                        )
                        refined += 1
                    else:
                        failures += 1
                        logging.error("精修失败 %s | %s | %s", record.rel_path, result.error_type, result.error_message)

                    elapsed = max(1e-6, time.monotonic() - started_at)
                    rate = (refined + failures) / elapsed * 60.0
                    progress.set_postfix(
                        ok=refined, err=failures,
                        rpm=f"{rate:.1f}", wrk=current_workers, cap=rate_limiter.get_rpm(),
                    )

                    while not stop_event.is_set() and len(future_map) < current_workers:
                        try:
                            next_record = pending_queue.get_nowait()
                        except queue.Empty:
                            break
                        next_future = executor.submit(worker_refine_record, next_record, cfg, rate_limiter, stop_event)
                        future_map[next_future] = next_record
                        submitted += 1
    finally:
        progress.close()
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

    logging.info(
        "精修完成。submitted=%s total=%s ok=%s error=%s model=%s",
        submitted, len(records), refined, failures, cfg.text_refine_model,
    )
