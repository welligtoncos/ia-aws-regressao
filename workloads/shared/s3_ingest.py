"""Detecção de arquivos novos em S3 (prefixo incoming/)."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from workloads.shared.aws_clients import get_glue_client, get_s3_client
from workloads.shared.ingest_watermark import get_watermark

logger = logging.getLogger(__name__)

GLUE_ACTIVE_STATES = frozenset({"STARTING", "RUNNING", "STOPPING", "WAITING"})


def is_glue_job_running(job_name: Optional[str]) -> bool:
    if not job_name:
        return False
    try:
        runs = get_glue_client().get_job_runs(JobName=job_name, MaxResults=5).get("JobRuns", [])
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("AccessDeniedException", "AccessDenied"):
            logger.warning("Sem permissão glue:GetJobRuns; assumindo job ocupado: %s", job_name)
            return True
        raise
    return any(r.get("JobRunState") in GLUE_ACTIVE_STATES for r in runs)



def list_incoming_files(bucket: str, prefix: str) -> List[Dict[str, str]]:
    client = get_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or not key.lower().endswith(".csv"):
                continue
            files.append({
                "key": key,
                "etag": obj.get("ETag", "").strip('"'),
                "last_modified": obj.get("LastModified", datetime.now(timezone.utc)).isoformat(),
            })
    return files


def find_unprocessed_incoming(
    bucket: str, prefix: str, table_name: Optional[str] = None
) -> List[Dict[str, str]]:
    wm = get_watermark(table_name)
    processed = wm.get("processed_keys", {})
    return [
        f for f in list_incoming_files(bucket, prefix)
        if processed.get(f["key"]) != f["etag"]
    ]


def should_run_simulated_micro(step_minutes: int, table_name: Optional[str] = None) -> bool:
    wm = get_watermark(table_name)
    last = wm.get("last_simulated_at")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
    return elapsed >= step_minutes


def check_new_data(
    bucket: str,
    incoming_prefix: str = "incoming/",
    ingest_simulated: bool = False,
    ingest_mode: str = "daily",
    step_minutes: int = 10,
    table_name: Optional[str] = None,
    glue_job_name: Optional[str] = None,
) -> Dict[str, Any]:
    if is_glue_job_running(glue_job_name):
        return {
            "has_new_data": False,
            "new_files": [],
            "new_file_keys": [],
            "simulated_due": False,
            "incoming_count": 0,
            "glue_job_running": True,
            "skip_reason": "glue_job_running",
        }

    new_files = find_unprocessed_incoming(bucket, incoming_prefix, table_name)
    simulated_due = False

    if ingest_simulated:
        simulated_due = (
            should_run_simulated_micro(step_minutes, table_name)
            if ingest_mode == "micro"
            else True
        )

    return {
        "has_new_data": len(new_files) > 0 or simulated_due,
        "new_files": new_files,
        "new_file_keys": [f["key"] for f in new_files],
        "simulated_due": simulated_due,
        "incoming_count": len(new_files),
        "glue_job_running": False,
    }
