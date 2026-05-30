from __future__ import annotations

import sqlite3
from pathlib import Path

from album_assetizer.models import AssetRecord, RefineRecord, WorkerResult
from album_assetizer.runtime import ensure_dir, stable_json_dumps, utc_now
from album_assetizer.schemas import PROMPT_VERSION


def create_connection(db_path: Path) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path TEXT NOT NULL UNIQUE,
            abs_path TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            source_format TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            content_sig TEXT NOT NULL,
            companion_video TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            discovered_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_attempt_at TEXT,
            completed_at TEXT,
            prompt_version TEXT,
            model_used TEXT,
            prepared_width INTEGER,
            prepared_height INTEGER,
            prepared_bytes INTEGER,
            original_result_json TEXT,
            result_json TEXT,
            usage_json TEXT,
            response_text TEXT,
            raw_response_json TEXT,
            last_error_type TEXT,
            last_error TEXT,
            last_traceback TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
        CREATE INDEX IF NOT EXISTS idx_assets_asset_type ON assets(asset_type);
        """
    )
    # 兼容旧版本数据库，补充缺失列
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(assets)").fetchall()}
    if "original_result_json" not in columns:
        conn.execute("ALTER TABLE assets ADD COLUMN original_result_json TEXT")
    conn.commit()


def get_status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS c FROM assets GROUP BY status").fetchall()
    counts = {"pending": 0, "running": 0, "done": 0, "error": 0}
    for row in rows:
        counts[row["status"]] = row["c"]
    counts["total"] = sum(counts.values())
    return counts


def mark_running_as_pending(conn: sqlite3.Connection) -> int:
    """将上次中断时遗留的 running 状态恢复为 pending，返回恢复数量。"""
    now = utc_now()
    cur = conn.execute(
        """
        UPDATE assets
        SET status = 'pending',
            updated_at = ?,
            last_error_type = COALESCE(last_error_type, 'interrupted'),
            last_error = CASE
                WHEN last_error IS NULL OR last_error = '' THEN 'Recovered stale running task after previous interruption'
                ELSE last_error
            END
        WHERE status = 'running'
        """,
        (now,),
    )
    conn.commit()
    return cur.rowcount


def mark_asset_running(conn: sqlite3.Connection, asset: AssetRecord) -> None:
    """将素材标记为处理中，并递增尝试次数。"""
    now = utc_now()
    conn.execute(
        """
        UPDATE assets
        SET status = 'running',
            attempts = attempts + 1,
            updated_at = ?,
            last_attempt_at = ?
        WHERE asset_id = ?
        """,
        (now, now, asset.asset_id),
    )
    conn.commit()


def record_success(conn: sqlite3.Connection, asset_id: int, result: WorkerResult) -> None:
    """写入成功结果，清除错误字段。"""
    now = utc_now()
    conn.execute(
        """
        UPDATE assets
        SET status = 'done',
            updated_at = ?,
            completed_at = ?,
            prompt_version = ?,
            model_used = ?,
            prepared_width = ?,
            prepared_height = ?,
            prepared_bytes = ?,
            result_json = ?,
            usage_json = ?,
            response_text = ?,
            raw_response_json = ?,
            last_error_type = NULL,
            last_error = NULL,
            last_traceback = NULL
        WHERE asset_id = ?
        """,
        (
            now,
            now,
            PROMPT_VERSION,
            result.model_used,
            result.prepared_width,
            result.prepared_height,
            result.prepared_bytes,
            stable_json_dumps(result.result_json or {}),
            stable_json_dumps(result.usage or {}),
            result.response_text,
            stable_json_dumps(result.raw_response_json or {}),
            asset_id,
        ),
    )
    conn.commit()


def record_failure(conn: sqlite3.Connection, asset_id: int, result: WorkerResult) -> None:
    """写入失败信息，保留已有的 response_text 和 raw_response_json。"""
    now = utc_now()
    conn.execute(
        """
        UPDATE assets
        SET status = 'error',
            updated_at = ?,
            model_used = ?,
            last_error_type = ?,
            last_error = ?,
            last_traceback = ?,
            response_text = COALESCE(?, response_text),
            raw_response_json = COALESCE(?, raw_response_json)
        WHERE asset_id = ?
        """,
        (
            now,
            result.model_used,
            result.error_type,
            result.error_message,
            result.traceback_text,
            result.response_text,
            stable_json_dumps(result.raw_response_json) if result.raw_response_json else None,
            asset_id,
        ),
    )
    conn.commit()


def update_refined_result(
    conn: sqlite3.Connection,
    asset_id: int,
    original_result: dict,
    refined_result: dict,
    model_used: str,
    usage_json: dict,
    response_text: str,
    raw_response_json: dict,
) -> None:
    """写入精修结果，用 COALESCE 保留首次原始结果快照。"""
    now = utc_now()
    conn.execute(
        """
        UPDATE assets
        SET updated_at = ?,
            completed_at = ?,
            prompt_version = ?,
            model_used = ?,
            original_result_json = COALESCE(original_result_json, ?),
            result_json = ?,
            usage_json = ?,
            response_text = ?,
            raw_response_json = ?,
            last_error_type = NULL,
            last_error = NULL,
            last_traceback = NULL
        WHERE asset_id = ?
        """,
        (
            now,
            now,
            PROMPT_VERSION,
            model_used,
            stable_json_dumps(original_result),
            stable_json_dumps(refined_result),
            stable_json_dumps(usage_json or {}),
            response_text,
            stable_json_dumps(raw_response_json or {}),
            asset_id,
        ),
    )
    conn.commit()


def requeue_asset_after_failure(conn: sqlite3.Connection, asset_id: int, result: WorkerResult) -> None:
    """将失败素材重新入队（同一次运行内立即重试）。"""
    now = utc_now()
    conn.execute(
        """
        UPDATE assets
        SET status = 'pending',
            updated_at = ?,
            model_used = ?,
            last_error_type = ?,
            last_error = ?,
            last_traceback = ?,
            response_text = COALESCE(?, response_text),
            raw_response_json = COALESCE(?, raw_response_json)
        WHERE asset_id = ?
        """,
        (
            now,
            result.model_used,
            result.error_type,
            result.error_message,
            result.traceback_text,
            result.response_text,
            stable_json_dumps(result.raw_response_json) if result.raw_response_json else None,
            asset_id,
        ),
    )
    conn.commit()


def fetch_assets_for_processing(conn: sqlite3.Connection, cfg) -> list[AssetRecord]:
    """获取待处理素材列表，cfg.retry_errors 控制是否包含失败记录。"""
    retry_filter = "status IN ('pending', 'error')" if cfg.retry_errors else "status = 'pending'"
    rows = conn.execute(
        f"""
        SELECT asset_id, rel_path, abs_path, asset_type, source_format, size_bytes, mtime_ns,
               companion_video, status, attempts, content_sig
        FROM assets
        WHERE {retry_filter}
          AND attempts < ?
        ORDER BY asset_id
        """,
        (cfg.max_attempts,),
    ).fetchall()
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


def fetch_assets_for_refinement(conn: sqlite3.Connection) -> list[RefineRecord]:
    """获取已完成但尚未精修的素材列表。"""
    rows = conn.execute(
        """
        SELECT asset_id, rel_path, result_json
        FROM assets
        WHERE status = 'done'
          AND result_json IS NOT NULL
          AND original_result_json IS NULL
        ORDER BY asset_id
        """
    ).fetchall()
    return [
        RefineRecord(
            asset_id=row["asset_id"],
            rel_path=row["rel_path"],
            draft_json=row["result_json"],
        )
        for row in rows
    ]
