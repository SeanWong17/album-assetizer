"""注释字段定义与 OpenAI JSON Schema，是导出器和提示词的单一数据源。"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "v1.0.0"
SCHEMA_NAME = "album_image_annotation"

# 带类型和中文描述的完整字段定义，供导出器和文档使用
ANNOTATION_FIELDS: list[dict[str, Any]] = [
    {"name": "caption_short", "type": "str", "description": "一句话简短描述"},
    {"name": "caption_long", "type": "str", "description": "详细描述，适合检索和回顾"},
    {"name": "scene", "type": "str", "description": "场景分类（如：户外、室内、街道）"},
    {"name": "tags", "type": "list[str]", "description": "语义标签列表"},
    {"name": "main_subjects", "type": "list[str]", "description": "画面主体（如：人物、建筑、食物）"},
    {"name": "activities", "type": "list[str]", "description": "正在发生的活动"},
    {"name": "style_labels", "type": "list[str]", "description": "风格标签（如：黑白、复古、HDR）"},
    {"name": "quality_flags", "type": "list[str]", "description": "质量标记（如：模糊、过曝）"},
    {"name": "safety_flags", "type": "list[str]", "description": "安全标记（如：敏感内容）"},
    {"name": "contains_text", "type": "bool", "description": "画面中是否包含文字"},
    {"name": "ocr_text", "type": "str", "description": "识别到的文字内容（≤300字）"},
    {"name": "people_count", "type": "int", "description": "画面中的人数，-1 表示无法判断"},
    {"name": "confidence", "type": "float", "description": "模型对本次标注的置信度 (0-1)"},
]

# 字段名平铺列表，供 parse_result_json 使用
ANNOTATION_FIELD_NAMES: list[str] = [f["name"] for f in ANNOTATION_FIELDS]
SCHEMA_FIELDS: list[str] = ANNOTATION_FIELD_NAMES

# OpenAI Structured Output 格式的 JSON Schema
JSON_SCHEMA: dict[str, Any] = {
    "name": SCHEMA_NAME,
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "caption_short": {"type": "string"},
            "caption_long": {"type": "string"},
            "scene": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "main_subjects": {"type": "array", "items": {"type": "string"}},
            "activities": {"type": "array", "items": {"type": "string"}},
            "style_labels": {"type": "array", "items": {"type": "string"}},
            "quality_flags": {"type": "array", "items": {"type": "string"}},
            "safety_flags": {"type": "array", "items": {"type": "string"}},
            "contains_text": {"type": "boolean"},
            "ocr_text": {"type": "string"},
            "people_count": {"type": "integer"},
            "confidence": {"type": "number"},
        },
        "required": [
            "caption_short",
            "caption_long",
            "scene",
            "tags",
            "main_subjects",
            "activities",
            "style_labels",
            "quality_flags",
            "safety_flags",
            "contains_text",
            "ocr_text",
            "people_count",
            "confidence",
        ],
    },
}

# 连通性探测用的轻量 Schema
TEXT_SMOKE_SCHEMA: dict[str, Any] = {
    "name": "text_smoke_probe",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reply": {"type": "string"},
            "model_family": {"type": "string"},
            "language": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["reply", "model_family", "language", "note"],
    },
}
