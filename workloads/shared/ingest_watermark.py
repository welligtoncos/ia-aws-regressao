"""Watermark de ingestão (arquivos S3 já processados)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from workloads.shared.dynamo_store import get_run_result, save_run_result

WATERMARK_ID = "__ingest_watermark__"


def get_watermark(table_name: Optional[str] = None) -> Dict[str, Any]:
    item = get_run_result(WATERMARK_ID, table_name)
    return item.get("payload", {}) if item else {}


def save_watermark(payload: Dict[str, Any], table_name: Optional[str] = None) -> None:
    save_run_result(WATERMARK_ID, "watermark", payload, table_name)


def mark_incoming_processed(keys: List[Dict[str, str]], table_name: Optional[str] = None) -> None:
    wm = get_watermark(table_name)
    processed = dict(wm.get("processed_keys", {}))
    for item in keys:
        processed[item["key"]] = item.get("etag", "")
    wm["processed_keys"] = processed
    wm["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_watermark(wm, table_name)


def mark_simulated_run(table_name: Optional[str] = None) -> None:
    wm = get_watermark(table_name)
    wm["last_simulated_at"] = datetime.now(timezone.utc).isoformat()
    save_watermark(wm, table_name)
