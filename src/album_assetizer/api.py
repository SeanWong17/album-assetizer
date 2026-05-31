"""API 调用模块：构建请求、解析响应、标准化输出字段。"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Iterable

from openai import BadRequestError, OpenAI

from album_assetizer.config import RuntimeConfig
from album_assetizer.models import PreparedImage
from album_assetizer.prompts import (
    SYSTEM_PROMPT,
    TEXT_SMOKE_SYSTEM_PROMPT,
    TEXT_SMOKE_USER_PROMPT,
    USER_PROMPT,
)
from album_assetizer.runtime import stable_json_dumps
from album_assetizer.schemas import JSON_SCHEMA, SCHEMA_FIELDS, TEXT_SMOKE_SCHEMA


def normalize_list(items: Iterable[str], limit: int | None = None) -> list[str]:
    """去重（大小写不敏感）、去空白、限制数量。"""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = " ".join(str(item).strip().split())
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def build_embedding_text(result: dict[str, Any]) -> str:
    """将所有标注字段拼接为适合 embedding 的纯文本。"""
    parts = [
        result.get("caption_short", ""),
        result.get("caption_long", ""),
        result.get("scene", ""),
        " ".join(result.get("tags", []) or []),
        " ".join(result.get("main_subjects", []) or []),
        " ".join(result.get("activities", []) or []),
        " ".join(result.get("style_labels", []) or []),
        " ".join(result.get("quality_flags", []) or []),
        " ".join(result.get("safety_flags", []) or []),
        result.get("ocr_text", ""),
    ]
    return "\n".join(part for part in parts if part).strip()


class ApiCapabilities:
    """线程安全地记录 API 能力，如是否支持 json_schema。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._json_schema_supported = True

    def json_schema_supported(self) -> bool:
        with self._lock:
            return self._json_schema_supported

    def disable_json_schema(self) -> None:
        with self._lock:
            self._json_schema_supported = False


def build_client(cfg: RuntimeConfig) -> OpenAI:
    return OpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        timeout=cfg.request_timeout,
        max_retries=0,
    )


def build_messages(data_url: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": USER_PROMPT},
            ],
        },
    ]


def build_text_smoke_messages(prompt: str | None = None) -> list[dict[str, Any]]:
    user_prompt = prompt.strip() if prompt else TEXT_SMOKE_USER_PROMPT
    return [
        {"role": "system", "content": TEXT_SMOKE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {}


def extract_text_from_response(response: Any) -> str:
    """从 API 响应中提取文本内容。"""
    if not getattr(response, "choices", None):
        raise ValueError("响应中没有 choices 字段")
    message = response.choices[0].message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif hasattr(item, "text"):
                texts.append(getattr(item, "text"))
        return "\n".join(texts).strip()
    raise ValueError("不支持的响应内容格式")


def parse_result_json(text: str) -> dict[str, Any]:
    """解析并标准化模型输出的 JSON，确保所有字段类型正确。"""
    stripped = text.strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # 尝试从文本中提取 JSON 对象
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(stripped[start: end + 1])

    if not isinstance(data, dict):
        raise ValueError("模型输出的 JSON 不是对象")

    normalized: dict[str, Any] = {}
    for field in SCHEMA_FIELDS:
        normalized[field] = data.get(field)

    # 标准化列表字段
    normalized["tags"] = normalize_list(normalized.get("tags") or [], limit=18)
    normalized["main_subjects"] = normalize_list(normalized.get("main_subjects") or [], limit=8)
    normalized["activities"] = normalize_list(normalized.get("activities") or [], limit=8)
    normalized["style_labels"] = normalize_list(normalized.get("style_labels") or [], limit=8)
    normalized["quality_flags"] = normalize_list(normalized.get("quality_flags") or [], limit=8)
    normalized["safety_flags"] = normalize_list(normalized.get("safety_flags") or [], limit=8)

    # 标准化字符串字段
    normalized["caption_short"] = str(normalized.get("caption_short") or "").strip()
    normalized["caption_long"] = str(normalized.get("caption_long") or "").strip()
    normalized["scene"] = str(normalized.get("scene") or "").strip()
    normalized["ocr_text"] = str(normalized.get("ocr_text") or "").strip()[:300]
    normalized["contains_text"] = bool(normalized.get("contains_text"))

    # 标准化数值字段
    try:
        normalized["people_count"] = int(normalized.get("people_count", -1))
    except Exception:
        normalized["people_count"] = -1
    try:
        confidence = float(normalized.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    normalized["confidence"] = max(0.0, min(1.0, confidence))

    # 生成 embedding 文本
    normalized["embedding_text"] = build_embedding_text(normalized)
    return normalized


def call_model_with_fallback(
    client: OpenAI,
    cfg: RuntimeConfig,
    prepared: PreparedImage,
    capabilities: ApiCapabilities,
    rate_limiter=None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """调用视觉模型，若 API 不支持 json_schema 则自动降级为普通 JSON 模式。"""
    from album_assetizer.image_prep import build_data_url
    messages = build_messages(build_data_url(prepared))
    use_json_schema = capabilities.json_schema_supported()

    request_kwargs: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "timeout": cfg.request_timeout,
    }
    if use_json_schema:
        request_kwargs["response_format"] = {"type": "json_schema", "json_schema": JSON_SCHEMA}

    try:
        response = client.chat.completions.create(**request_kwargs)
    except BadRequestError as exc:
        if use_json_schema:
            # API 不支持 json_schema，降级后重试
            capabilities.disable_json_schema()
            request_kwargs.pop("response_format", None)
            response = client.chat.completions.create(**request_kwargs)
        else:
            raise exc

    text = extract_text_from_response(response)
    parsed = parse_result_json(text)

    # 若配置了精修模型，对首轮结果进行文本精修（独立重试，不重做视觉请求）
    if cfg.text_refine_model:
        max_refine_retries = getattr(cfg, "max_retries", 3)
        last_refine_exc: Exception | None = None
        for refine_attempt in range(1, max_refine_retries + 2):
            try:
                if rate_limiter is not None:
                    rate_limiter.acquire()
                refined, _, usage_json, raw_json = call_text_refine_model(client, cfg, parsed)
                parsed = refined
                break
            except Exception as exc:
                from album_assetizer.worker import classify_exception as _classify
                _, retryable = _classify(exc)
                last_refine_exc = exc
                if retryable and refine_attempt <= max_refine_retries:
                    delay = min(cfg.retry_max_seconds, cfg.retry_base_seconds * (2 ** (refine_attempt - 1)))
                    logging.warning("精修重试 %s/%s: %s", refine_attempt, max_refine_retries, exc)
                    time.sleep(delay)
                    continue
                raise
    else:
        raw_json = response.model_dump() if hasattr(response, "model_dump") else {}
        usage_json = usage_to_dict(getattr(response, "usage", None))

    return parsed, text, usage_json, raw_json


def call_text_refine_model(
    client: OpenAI,
    cfg: RuntimeConfig,
    draft: dict[str, Any],
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """用纯文本模型对首轮标注结果进行规范化精修。"""
    refine_prompt = (
        "请把下面这份图片标注 JSON 规范化，保留原意，输出同一 schema 的 JSON。"
        "主要做去重、修正文案、压缩冗余标签，不要新增看不出的事实。\n\n"
        + stable_json_dumps(draft)
    )
    response = client.chat.completions.create(
        model=cfg.text_refine_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": refine_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
        timeout=cfg.request_timeout,
    )
    text = extract_text_from_response(response)
    parsed = parse_result_json(text)
    raw_json = response.model_dump() if hasattr(response, "model_dump") else {}
    usage_json = usage_to_dict(getattr(response, "usage", None))
    return parsed, text, usage_json, raw_json


def call_text_smoke(
    client: OpenAI,
    model: str,
    timeout: int,
    prompt: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """发送轻量连通性探测请求，验证 API 鉴权和结构化输出能力。"""
    response = client.chat.completions.create(
        model=model,
        messages=build_text_smoke_messages(prompt),
        timeout=timeout,
        response_format={"type": "json_schema", "json_schema": TEXT_SMOKE_SCHEMA},
    )
    text = extract_text_from_response(response)
    payload = json.loads(text)
    raw_json = response.model_dump() if hasattr(response, "model_dump") else {}
    usage_json = usage_to_dict(getattr(response, "usage", None))
    return payload, text, usage_json, raw_json
