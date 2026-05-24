"""Handler Lambda para automações: validação, finalização e persistência."""

import json
import logging
import os
import uuid
from typing import Any, Dict

from workloads.shared.dynamo_store import save_run_result
from workloads.shared.ingest_watermark import mark_incoming_processed, mark_simulated_run
from workloads.shared.regression import compare_records, summarize_diffs
from workloads.shared.aws_clients import get_s3_client
from workloads.shared.s3_ingest import check_new_data

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def _validate(event: Dict[str, Any]) -> Dict[str, Any]:
    bucket = os.environ["SOURCE_BUCKET"]
    prefix = event.get("source_prefix", "raw/")
    run_id = event.get("run_id") or str(uuid.uuid4())

    client = get_s3_client()
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
    has_data = "Contents" in response and len(response["Contents"]) > 0

    result = {
        "run_id": run_id,
        "source_bucket": bucket,
        "source_prefix": prefix,
        "has_data": has_data,
        "status": "validated" if has_data else "no_input",
    }

    save_run_result(run_id, result["status"], {"phase": "validate", **result})
    return result


def _check_new_data(event: Dict[str, Any]) -> Dict[str, Any]:
    bucket = os.environ["SOURCE_BUCKET"]
    table = os.environ["DYNAMODB_TABLE"]
    result = check_new_data(
        bucket=bucket,
        incoming_prefix=os.environ.get("INCOMING_PREFIX", "incoming/"),
        ingest_simulated=os.environ.get("INGEST_SIMULATED", "false").lower() == "true",
        ingest_mode=os.environ.get("INGEST_MODE", "daily"),
        step_minutes=int(os.environ.get("INGEST_STEP_MINUTES", "10")),
        table_name=table,
        glue_job_name=os.environ.get("GLUE_JOB_NAME"),
    )
    result["run_id"] = event.get("run_id") or str(uuid.uuid4())
    result["status"] = "new_data" if result["has_new_data"] else "no_new_data"
    save_run_result(result["run_id"], result["status"], {"phase": "check_new_data", **result})
    return result


def _finalize(event: Dict[str, Any]) -> Dict[str, Any]:
    run_id = event["run_id"]
    validation = event.get("validation", {})
    glue_result = event.get("glue", {})
    check = event.get("check", {})

    validation_status = validation
    if isinstance(validation, dict) and "Payload" in validation:
        validation_status = validation["Payload"]

    diffs = compare_records(
        expected={"status": "validated"},
        actual={"status": validation_status.get("status", "unknown") if isinstance(validation_status, dict) else "unknown"},
        keys=["status"],
    )
    summary = summarize_diffs(diffs)

    check_parsed = check.get("parsed", check) if isinstance(check, dict) else {}
    if isinstance(check_parsed, dict) and "Payload" in check_parsed:
        body = check_parsed.get("Payload", {}).get("body")
        if body:
            check_parsed = json.loads(body) if isinstance(body, str) else body

    table = os.environ["DYNAMODB_TABLE"]
    new_files = check_parsed.get("new_files", []) if isinstance(check_parsed, dict) else []
    if new_files:
        mark_incoming_processed(new_files, table)
    if isinstance(check_parsed, dict) and check_parsed.get("simulated_due"):
        mark_simulated_run(table)

    result = {
        "run_id": run_id,
        "validation": validation,
        "glue": glue_result,
        "check": check,
        "regression": summary,
        "status": "success" if summary["passed"] else "failed",
    }

    save_run_result(run_id, result["status"], {"phase": "finalize", **result})
    return result


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Roteia ações do pipeline de automação."""
    logger.info("Automation lambda invoked: %s", json.dumps(event))

    action = event.get("action", "validate")
    if action == "validate":
        body = _validate(event)
    elif action == "check_new_data":
        body = _check_new_data(event)
    elif action == "finalize":
        body = _finalize(event)
    else:
        body = {"error": f"unknown action: {action}"}

    return {"statusCode": 200, "body": json.dumps(body)}
