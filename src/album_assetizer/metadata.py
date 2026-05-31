from __future__ import annotations

from dataclasses import dataclass
import io
import logging
from pathlib import Path
import sqlite3
from typing import Any
import zipfile

from PIL import ExifTags, Image
from pillow_heif import register_heif_opener

from album_assetizer.models import AssetRecord, UnsupportedAssetError
from album_assetizer.runtime import stable_json_dumps, utc_now
from album_assetizer.scanner import detect_livp_companion

register_heif_opener()

GPS_INFO_TAG = 0x8825
DATETIME_ORIGINAL_TAG = 0x9003
DATETIME_DIGITIZED_TAG = 0x9004
DATETIME_TAG = 0x0132
OFFSET_TIME_TAG = 0x9010
OFFSET_TIME_ORIGINAL_TAG = 0x9011
OFFSET_TIME_DIGITIZED_TAG = 0x9012


@dataclass(slots=True)
class AssetMetadata:
    taken_at: str | None
    gps_lat: float | None
    gps_lng: float | None
    metadata_json: dict[str, Any]


def _decode_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return value.decode(encoding).strip("\x00 ").strip() or None
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="ignore").strip("\x00 ").strip() or None
    text = str(value).strip()
    return text or None


def _rational_to_float(value: Any) -> float:
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        denominator = float(value.denominator) or 1.0
        return float(value.numerator) / denominator
    if isinstance(value, tuple) and len(value) == 2:
        denominator = float(value[1]) or 1.0
        return float(value[0]) / denominator
    return float(value)


def _parse_coord(value: Any, ref: str | None) -> float | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        degrees = _rational_to_float(value[0])
        minutes = _rational_to_float(value[1])
        seconds = _rational_to_float(value[2])
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    coord = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if ref and ref.upper() in {"S", "W"}:
        coord = -coord
    return round(coord, 7)


def parse_exif_datetime(raw_value: Any, raw_offset: Any) -> str | None:
    from datetime import datetime, timedelta, timezone

    value = _decode_text(raw_value)
    if not value:
        return None

    try:
        parsed = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None

    offset = _decode_text(raw_offset)
    if offset and len(offset) >= 6 and offset[0] in {"+", "-"} and offset[3] == ":":
        try:
            hours = int(offset[1:3])
            minutes = int(offset[4:6])
            delta = timedelta(hours=hours, minutes=minutes)
            if offset[0] == "-":
                delta = -delta
            parsed = parsed.replace(tzinfo=timezone(delta))
        except ValueError:
            pass

    return parsed.isoformat(timespec="seconds")


def parse_gps_info(gps_info: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = _parse_coord(gps_info.get("GPSLatitude"), _decode_text(gps_info.get("GPSLatitudeRef")))
    lng = _parse_coord(gps_info.get("GPSLongitude"), _decode_text(gps_info.get("GPSLongitudeRef")))
    return lat, lng


def _extract_named_exif(image: Image.Image) -> tuple[dict[str, Any], dict[str, Any]]:
    exif = image.getexif()
    named_exif: dict[str, Any] = {}
    for tag_id, value in exif.items():
        named_exif[ExifTags.TAGS.get(tag_id, str(tag_id))] = value

    named_gps: dict[str, Any] = {}
    try:
        gps_ifd = exif.get_ifd(GPS_INFO_TAG)
    except Exception:
        gps_ifd = named_exif.get("GPSInfo")

    if isinstance(gps_ifd, dict):
        for tag_id, value in gps_ifd.items():
            named_gps[ExifTags.GPSTAGS.get(tag_id, str(tag_id))] = value

    return named_exif, named_gps


def extract_metadata_from_pil(image: Image.Image, source_kind: str) -> AssetMetadata:
    named_exif, named_gps = _extract_named_exif(image)
    taken_at = (
        parse_exif_datetime(named_exif.get(ExifTags.TAGS.get(DATETIME_ORIGINAL_TAG)), named_exif.get(ExifTags.TAGS.get(OFFSET_TIME_ORIGINAL_TAG)))
        or parse_exif_datetime(named_exif.get(ExifTags.TAGS.get(DATETIME_DIGITIZED_TAG)), named_exif.get(ExifTags.TAGS.get(OFFSET_TIME_DIGITIZED_TAG)))
        or parse_exif_datetime(named_exif.get(ExifTags.TAGS.get(DATETIME_TAG)), named_exif.get(ExifTags.TAGS.get(OFFSET_TIME_TAG)))
    )
    gps_lat, gps_lng = parse_gps_info(named_gps)

    metadata_json = {
        "source_kind": source_kind,
        "has_exif": bool(named_exif),
        "datetime_original": _decode_text(named_exif.get(ExifTags.TAGS.get(DATETIME_ORIGINAL_TAG))),
        "datetime_digitized": _decode_text(named_exif.get(ExifTags.TAGS.get(DATETIME_DIGITIZED_TAG))),
        "datetime": _decode_text(named_exif.get(ExifTags.TAGS.get(DATETIME_TAG))),
        "offset_time_original": _decode_text(named_exif.get(ExifTags.TAGS.get(OFFSET_TIME_ORIGINAL_TAG))),
        "offset_time_digitized": _decode_text(named_exif.get(ExifTags.TAGS.get(OFFSET_TIME_DIGITIZED_TAG))),
        "offset_time": _decode_text(named_exif.get(ExifTags.TAGS.get(OFFSET_TIME_TAG))),
        "gps_lat": gps_lat,
        "gps_lng": gps_lng,
        "gps_lat_ref": _decode_text(named_gps.get("GPSLatitudeRef")),
        "gps_lng_ref": _decode_text(named_gps.get("GPSLongitudeRef")),
    }
    return AssetMetadata(
        taken_at=taken_at,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        metadata_json=metadata_json,
    )


def extract_regular_image_metadata(path: Path) -> AssetMetadata:
    with Image.open(path) as image:
        image.load()
        return extract_metadata_from_pil(image, source_kind="image_exif")


def extract_livp_metadata(path: Path) -> AssetMetadata:
    with zipfile.ZipFile(path) as zf:
        image_name, _ = detect_livp_companion(zf)
        with zf.open(image_name, "r") as fp:
            image_bytes = fp.read()
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        return extract_metadata_from_pil(image, source_kind="livp_exif")


def extract_asset_metadata(asset: AssetRecord) -> AssetMetadata:
    if asset.asset_type == "livp":
        return extract_livp_metadata(asset.abs_path)
    if asset.asset_type == "image":
        return extract_regular_image_metadata(asset.abs_path)
    raise UnsupportedAssetError(f"不支持的素材类型: {asset.asset_type}")


def fetch_assets_for_metadata_sync(
    conn: sqlite3.Connection,
    *,
    only_missing: bool,
    limit: int | None,
) -> list[AssetRecord]:
    sql = """
        SELECT asset_id, rel_path, abs_path, asset_type, source_format, size_bytes, mtime_ns,
               companion_video, status, attempts, content_sig
        FROM assets
    """
    params: list[Any] = []
    if only_missing:
        sql += " WHERE metadata_json IS NULL OR metadata_json = ''"
    sql += " ORDER BY asset_id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        AssetRecord(
            asset_id=row["asset_id"],
            rel_path=row["rel_path"],
            abs_path=Path(row["abs_path"]),
            asset_type=row["asset_type"],
            source_format=row["source_format"],
            size_bytes=row["size_bytes"],
            mtime_ns=row["mtime_ns"],
            companion_video=row["companion_video"],
            status=row["status"],
            attempts=row["attempts"],
            content_sig=row["content_sig"],
        )
        for row in rows
    ]


def update_asset_metadata(
    conn: sqlite3.Connection,
    asset_id: int,
    metadata: AssetMetadata | None,
    error_message: str | None,
) -> None:
    now = utc_now()
    payload = metadata.metadata_json if metadata else {"source_kind": "unavailable"}
    conn.execute(
        """
        UPDATE assets
        SET updated_at = ?,
            metadata_updated_at = ?,
            taken_at = ?,
            gps_lat = ?,
            gps_lng = ?,
            metadata_json = ?,
            metadata_error = ?
        WHERE asset_id = ?
        """,
        (
            now,
            now,
            metadata.taken_at if metadata else None,
            metadata.gps_lat if metadata else None,
            metadata.gps_lng if metadata else None,
            stable_json_dumps(payload),
            error_message,
            asset_id,
        ),
    )


def sync_asset_metadata(
    conn: sqlite3.Connection,
    *,
    only_missing: bool = True,
    limit: int | None = None,
    commit_every: int = 200,
) -> dict[str, int]:
    assets = fetch_assets_for_metadata_sync(conn, only_missing=only_missing, limit=limit)
    stats = {
        "total": len(assets),
        "updated": 0,
        "with_taken_at": 0,
        "with_gps": 0,
        "empty": 0,
        "failed": 0,
    }

    for index, asset in enumerate(assets, start=1):
        try:
            metadata = extract_asset_metadata(asset)
            if metadata.taken_at:
                stats["with_taken_at"] += 1
            if metadata.gps_lat is not None and metadata.gps_lng is not None:
                stats["with_gps"] += 1
            if not metadata.metadata_json.get("has_exif"):
                stats["empty"] += 1
            update_asset_metadata(conn, asset.asset_id, metadata, None)
            stats["updated"] += 1
        except Exception as exc:
            logging.warning("元数据读取失败 %s: %s", asset.rel_path, exc)
            update_asset_metadata(conn, asset.asset_id, None, str(exc))
            stats["failed"] += 1

        if commit_every > 0 and index % commit_every == 0:
            conn.commit()

        if index % 200 == 0:
            logging.info(
                "元数据同步进度 %s/%s | updated=%s with_taken_at=%s with_gps=%s failed=%s",
                index,
                len(assets),
                stats["updated"],
                stats["with_taken_at"],
                stats["with_gps"],
                stats["failed"],
            )

    conn.commit()
    return stats
