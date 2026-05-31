from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
import sqlite3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a clean snapshot for album-explorer from album-assetizer DB.",
    )
    parser.add_argument("--db", required=True, help="album-assetizer sqlite db path")
    parser.add_argument("--output-dir", required=True, help="output directory for explorer snapshot")
    parser.add_argument("--root", required=True, help="album root path")
    return parser.parse_args()


def to_month_bucket(taken_at: str | None) -> str | None:
    if not taken_at:
        return None
    try:
        dt = datetime.fromisoformat(taken_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return f"{dt.year:04d}-{dt.month:02d}"


def city_bucket(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    return f"{lat:.3f},{lng:.3f}"


def cluster_key(scene: str, tags: list[str], caption_short: str) -> str:
    scene = (scene or "").strip()
    if scene:
        return scene
    if tags:
        return " / ".join(tags[:3])
    return (caption_short or "未分类").strip() or "未分类"


def export_snapshot(db_path: Path, output_dir: Path, root: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_jsonl = output_dir / "explorer_snapshot.jsonl"
    clusters_json = output_dir / "explorer_clusters.json"
    summary_json = output_dir / "explorer_summary.json"
    snapshot_csv = output_dir / "explorer_snapshot.csv"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT asset_id, rel_path, abs_path, asset_type, source_format, companion_video,
               status, completed_at, model_used, taken_at, gps_lat, gps_lng,
               metadata_json, result_json
        FROM assets
        WHERE status = 'done'
          AND result_json IS NOT NULL
          AND rel_path NOT LIKE 'album-assetizer/%'
          AND rel_path NOT LIKE 'album-explorer/%'
          AND rel_path NOT LIKE '_album_migrations/%'
        ORDER BY asset_id
        """
    ).fetchall()

    cluster_counts: dict[str, int] = {}
    month_counts: dict[str, int] = {}
    city_counts: dict[str, int] = {}

    with (
        snapshot_jsonl.open("w", encoding="utf-8") as jf,
        snapshot_csv.open("w", encoding="utf-8", newline="") as cf,
    ):
        writer = csv.DictWriter(
            cf,
            fieldnames=[
                "asset_id",
                "rel_path",
                "asset_type",
                "source_format",
                "taken_at",
                "gps_lat",
                "gps_lng",
                "month_bucket",
                "city_bucket",
                "cluster_label",
                "caption_short",
                "scene",
                "tags",
                "main_subjects",
                "activities",
                "style_labels",
                "quality_flags",
                "contains_text",
                "people_count",
            ],
        )
        writer.writeheader()

        for row in rows:
            result = json.loads(row["result_json"]) if row["result_json"] else {}
            metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            tags = result.get("tags", []) or []
            main_subjects = result.get("main_subjects", []) or []
            activities = result.get("activities", []) or []
            style_labels = result.get("style_labels", []) or []
            quality_flags = result.get("quality_flags", []) or []
            scene = result.get("scene", "") or ""
            caption_short = result.get("caption_short", "") or ""
            month_bucket = to_month_bucket(row["taken_at"])
            location_bucket = city_bucket(row["gps_lat"], row["gps_lng"])
            cluster_label = cluster_key(scene, tags, caption_short)

            if month_bucket:
                month_counts[month_bucket] = month_counts.get(month_bucket, 0) + 1
            if location_bucket:
                city_counts[location_bucket] = city_counts.get(location_bucket, 0) + 1
            cluster_counts[cluster_label] = cluster_counts.get(cluster_label, 0) + 1

            payload = {
                "asset_id": row["asset_id"],
                "rel_path": row["rel_path"],
                "abs_path": row["abs_path"],
                "asset_type": row["asset_type"],
                "source_format": row["source_format"],
                "companion_video": row["companion_video"],
                "status": row["status"],
                "completed_at": row["completed_at"],
                "model_used": row["model_used"],
                "taken_at": row["taken_at"],
                "gps_lat": row["gps_lat"],
                "gps_lng": row["gps_lng"],
                "month_bucket": month_bucket,
                "city_bucket": location_bucket,
                "cluster_label": cluster_label,
                "metadata": metadata,
                "result": result,
            }
            jf.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

            writer.writerow(
                {
                    "asset_id": row["asset_id"],
                    "rel_path": row["rel_path"],
                    "asset_type": row["asset_type"],
                    "source_format": row["source_format"],
                    "taken_at": row["taken_at"] or "",
                    "gps_lat": row["gps_lat"] if row["gps_lat"] is not None else "",
                    "gps_lng": row["gps_lng"] if row["gps_lng"] is not None else "",
                    "month_bucket": month_bucket or "",
                    "city_bucket": location_bucket or "",
                    "cluster_label": cluster_label,
                    "caption_short": caption_short,
                    "scene": scene,
                    "tags": "|".join(tags),
                    "main_subjects": "|".join(main_subjects),
                    "activities": "|".join(activities),
                    "style_labels": "|".join(style_labels),
                    "quality_flags": "|".join(quality_flags),
                    "contains_text": result.get("contains_text", False),
                    "people_count": result.get("people_count", -1),
                }
            )

    summary = {
        "root": str(root),
        "db_path": str(db_path),
        "total_items": len(rows),
        "with_taken_at": sum(month_counts.values()),
        "with_gps": sum(city_counts.values()),
        "cluster_count": len(cluster_counts),
        "top_clusters": sorted(
            [{"label": k, "count": v} for k, v in cluster_counts.items()],
            key=lambda x: (-x["count"], x["label"]),
        )[:100],
        "top_months": sorted(
            [{"month": k, "count": v} for k, v in month_counts.items()],
            key=lambda x: (-x["count"], x["month"]),
        )[:100],
        "top_locations": sorted(
            [{"bucket": k, "count": v} for k, v in city_counts.items()],
            key=lambda x: (-x["count"], x["bucket"]),
        )[:100],
    }
    clusters = sorted(
        [{"label": k, "count": v} for k, v in cluster_counts.items()],
        key=lambda x: (-x["count"], x["label"]),
    )

    clusters_json.write_text(json.dumps(clusters, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "snapshot_jsonl": snapshot_jsonl,
        "snapshot_csv": snapshot_csv,
        "clusters_json": clusters_json,
        "summary_json": summary_json,
    }


def main() -> int:
    args = parse_args()
    paths = export_snapshot(Path(args.db), Path(args.output_dir), Path(args.root))
    print(json.dumps({k: str(v) for k, v in paths.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
