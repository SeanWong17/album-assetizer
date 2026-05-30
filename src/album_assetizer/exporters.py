from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3

from album_assetizer.runtime import stable_json_dumps


def export_jsonl(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def export_csv(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = list(records[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return path


def export_asset_results(conn: sqlite3.Connection, export_dir: Path) -> dict[str, Path]:
    export_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = export_dir / "results.jsonl"
    csv_path = export_dir / "results.csv"
    failures_path = export_dir / "failures.jsonl"
    original_jsonl_path = export_dir / "results_original_before_refine.jsonl"

    rows = conn.execute(
        """
        SELECT asset_id, rel_path, asset_type, source_format, companion_video, status,
               attempts, completed_at, model_used, prepared_width, prepared_height,
               prepared_bytes, original_result_json, result_json, usage_json,
               last_error_type, last_error
        FROM assets
        ORDER BY asset_id
        """
    ).fetchall()

    with (
        jsonl_path.open("w", encoding="utf-8") as jf,
        failures_path.open("w", encoding="utf-8") as ff,
        original_jsonl_path.open("w", encoding="utf-8") as ojf,
        csv_path.open("w", encoding="utf-8", newline="") as cf,
    ):
        writer = csv.DictWriter(
            cf,
            fieldnames=[
                "asset_id",
                "rel_path",
                "asset_type",
                "source_format",
                "companion_video",
                "status",
                "attempts",
                "completed_at",
                "model_used",
                "prepared_width",
                "prepared_height",
                "prepared_bytes",
                "has_original_result_snapshot",
                "caption_short",
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
                "embedding_text",
                "last_error_type",
                "last_error",
            ],
        )
        writer.writeheader()

        for row in rows:
            original_result_json = json.loads(row["original_result_json"]) if row["original_result_json"] else {}
            result_json = json.loads(row["result_json"]) if row["result_json"] else {}
            usage_json = json.loads(row["usage_json"]) if row["usage_json"] else {}
            payload = {
                "asset_id": row["asset_id"],
                "rel_path": row["rel_path"],
                "asset_type": row["asset_type"],
                "source_format": row["source_format"],
                "companion_video": row["companion_video"],
                "status": row["status"],
                "attempts": row["attempts"],
                "completed_at": row["completed_at"],
                "model_used": row["model_used"],
                "prepared_width": row["prepared_width"],
                "prepared_height": row["prepared_height"],
                "prepared_bytes": row["prepared_bytes"],
                "original_result": original_result_json,
                "result": result_json,
                "usage": usage_json,
                "last_error_type": row["last_error_type"],
                "last_error": row["last_error"],
            }
            jf.write(stable_json_dumps(payload) + "\n")

            if original_result_json:
                ojf.write(
                    stable_json_dumps(
                        {
                            "asset_id": row["asset_id"],
                            "rel_path": row["rel_path"],
                            "model_used": row["model_used"],
                            "original_result": original_result_json,
                        }
                    )
                    + "\n"
                )

            if row["status"] == "error":
                ff.write(stable_json_dumps(payload) + "\n")

            writer.writerow(
                {
                    "asset_id": row["asset_id"],
                    "rel_path": row["rel_path"],
                    "asset_type": row["asset_type"],
                    "source_format": row["source_format"],
                    "companion_video": row["companion_video"],
                    "status": row["status"],
                    "attempts": row["attempts"],
                    "completed_at": row["completed_at"],
                    "model_used": row["model_used"],
                    "prepared_width": row["prepared_width"],
                    "prepared_height": row["prepared_height"],
                    "prepared_bytes": row["prepared_bytes"],
                    "has_original_result_snapshot": bool(original_result_json),
                    "caption_short": result_json.get("caption_short", ""),
                    "scene": result_json.get("scene", ""),
                    "tags": "|".join(result_json.get("tags", []) or []),
                    "main_subjects": "|".join(result_json.get("main_subjects", []) or []),
                    "activities": "|".join(result_json.get("activities", []) or []),
                    "style_labels": "|".join(result_json.get("style_labels", []) or []),
                    "quality_flags": "|".join(result_json.get("quality_flags", []) or []),
                    "safety_flags": "|".join(result_json.get("safety_flags", []) or []),
                    "contains_text": result_json.get("contains_text", False),
                    "ocr_text": result_json.get("ocr_text", ""),
                    "people_count": result_json.get("people_count", -1),
                    "confidence": result_json.get("confidence", 0),
                    "embedding_text": result_json.get("embedding_text", ""),
                    "last_error_type": row["last_error_type"],
                    "last_error": row["last_error"],
                }
            )

    return {
        "jsonl": jsonl_path,
        "csv": csv_path,
        "failures": failures_path,
        "original_jsonl": original_jsonl_path,
    }
