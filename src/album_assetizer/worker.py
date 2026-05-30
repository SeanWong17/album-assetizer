"""工作线程模块：单个素材的处理逻辑、错误分类、指数退避重试。"""

from __future__ import annotations

import logging
import threading
import traceback
import zipfile
from typing import Any

from openai import APIConnectionError, APIError, RateLimitError
from PIL import UnidentifiedImageError

from album_assetizer.api import ApiCapabilities, build_client, call_model_with_fallback, call_text_refine_model
from album_assetizer.config import RuntimeConfig
from album_assetizer.image_prep import prepare_asset_image
from album_assetizer.models import AssetRecord, RefineRecord, StopRequested, UnsupportedAssetError, WorkerResult
from album_assetizer.rate_limiter import RateLimiter


def backoff_sleep(stop_event: threading.Event, seconds: float) -> None:
    """分段休眠，每秒检查一次停止信号，收到信号则抛出 StopRequested。"""
    remaining = seconds
    while remaining > 0 and not stop_event.is_set():
        chunk = min(remaining, 1.0)
        stop_event.wait(chunk)
        remaining -= chunk
    if stop_event.is_set():
        raise StopRequested("退避等待期间收到停止信号")


def classify_exception(exc: Exception) -> tuple[str, bool]:
    """将异常分类为 (错误类型字符串, 是否可重试)。"""
    if isinstance(exc, UnsupportedAssetError):
        return "unsupported_asset", False
    if isinstance(exc, UnidentifiedImageError):
        return "invalid_image", False
    if isinstance(exc, zipfile.BadZipFile):
        return "invalid_livp_zip", False
    if isinstance(exc, RateLimitError):
        return "rate_limit", True
    if isinstance(exc, APIConnectionError):
        return "api_connection_error", True
    if isinstance(exc, APIError):
        status_code = getattr(exc, "status_code", None)
        if status_code in {408, 409, 429, 500, 502, 503, 504}:
            return f"api_error_{status_code}", True
        return f"api_error_{status_code}", False
    return exc.__class__.__name__, False


def worker_process_asset(
    asset: AssetRecord,
    cfg: RuntimeConfig,
    rate_limiter: RateLimiter,
    stop_event: threading.Event,
    capabilities: ApiCapabilities,
) -> WorkerResult:
    """处理单个素材：预处理图片 → 调用 API → 返回结果。失败时按策略重试。"""
    client = build_client(cfg)
    try:
        attempt = 0
        while True:
            if stop_event.is_set():
                raise StopRequested("收到停止信号")
            attempt += 1
            try:
                prepared = prepare_asset_image(asset, cfg)
                rate_limiter.acquire()
                parsed, response_text, usage_json, raw_response_json = call_model_with_fallback(
                    client=client,
                    cfg=cfg,
                    prepared=prepared,
                    capabilities=capabilities,
                )
                # 将素材来源信息附加到结果中
                parsed["source_asset"] = {
                    "rel_path": asset.rel_path,
                    "asset_type": asset.asset_type,
                    "source_format": asset.source_format,
                    "companion_video": asset.companion_video,
                }
                return WorkerResult(
                    ok=True,
                    asset_id=asset.asset_id,
                    rel_path=asset.rel_path,
                    prepared_width=prepared.width,
                    prepared_height=prepared.height,
                    prepared_bytes=len(prepared.jpeg_bytes),
                    result_json=parsed,
                    usage=usage_json,
                    response_text=response_text,
                    raw_response_json=raw_response_json,
                    model_used=cfg.text_refine_model or cfg.model,
                )
            except Exception as exc:
                error_type, retryable = classify_exception(exc)
                if retryable and attempt < cfg.max_attempts:
                    # 指数退避 + 抖动，避免多线程同时重试
                    delay = min(cfg.retry_max_seconds, cfg.retry_base_seconds * (2 ** (attempt - 1)))
                    jitter = min(3.0, attempt * 0.37)
                    logging.warning(
                        "可重试错误 %s (第 %s/%s 次): %s | 等待 %.1fs",
                        asset.rel_path, attempt, cfg.max_attempts, exc, delay + jitter,
                    )
                    backoff_sleep(stop_event, delay + jitter)
                    continue
                return WorkerResult(
                    ok=False,
                    asset_id=asset.asset_id,
                    rel_path=asset.rel_path,
                    model_used=cfg.text_refine_model or cfg.model,
                    error_type=error_type,
                    error_message=str(exc),
                    traceback_text=traceback.format_exc(limit=10),
                    retryable=retryable,
                )
    finally:
        client.close()


def worker_refine_record(
    record: RefineRecord,
    cfg: RuntimeConfig,
    rate_limiter: RateLimiter,
    stop_event: threading.Event,
) -> WorkerResult:
    """对已完成素材的首轮结果进行文本精修。"""
    import json
    client = build_client(cfg)
    draft = json.loads(record.draft_json)
    try:
        attempt = 0
        while True:
            if stop_event.is_set():
                raise StopRequested("收到停止信号")
            attempt += 1
            try:
                rate_limiter.acquire()
                parsed, response_text, usage_json, raw_response_json = call_text_refine_model(
                    client=client,
                    cfg=cfg,
                    draft=draft,
                )
                # 保留原始素材来源信息
                if isinstance(draft.get("source_asset"), dict):
                    parsed["source_asset"] = draft["source_asset"]
                return WorkerResult(
                    ok=True,
                    asset_id=record.asset_id,
                    rel_path=record.rel_path,
                    result_json=parsed,
                    usage=usage_json,
                    response_text=response_text,
                    raw_response_json=raw_response_json,
                    model_used=cfg.text_refine_model,
                )
            except Exception as exc:
                error_type, retryable = classify_exception(exc)
                if retryable and attempt < cfg.max_attempts:
                    delay = min(cfg.retry_max_seconds, cfg.retry_base_seconds * (2 ** (attempt - 1)))
                    jitter = min(3.0, attempt * 0.37)
                    logging.warning(
                        "精修可重试错误 %s (第 %s/%s 次): %s | 等待 %.1fs",
                        record.rel_path, attempt, cfg.max_attempts, exc, delay + jitter,
                    )
                    backoff_sleep(stop_event, delay + jitter)
                    continue
                return WorkerResult(
                    ok=False,
                    asset_id=record.asset_id,
                    rel_path=record.rel_path,
                    model_used=cfg.text_refine_model,
                    error_type=error_type,
                    error_message=str(exc),
                    traceback_text=traceback.format_exc(limit=10),
                    retryable=retryable,
                )
    finally:
        client.close()
