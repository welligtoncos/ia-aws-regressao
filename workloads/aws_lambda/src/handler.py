"""Handler Lambda para automações: validação, finalização e persistência."""

import json
import logging
import os
import uuid
from typing import Any, Dict

from workloads.shared.dynamo_store import save_run_result
from workloads.shared.regression import compare_records, summarize_diffs
from workloads.shared.aws_clients import get_s3_client

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


def _finalize(event: Dict[str, Any]) -> Dict[str, Any]:
    run_id = event["run_id"]
    validation = event.get("validation", {})
    glue_result = event.get("glue", {})

    validation_status = validation
    if isinstance(validation, dict) and "Payload" in validation:
        validation_status = validation["Payload"]

    diffs = compare_records(
        expected={"status": "validated"},
        actual={"status": validation_status.get("status", "unknown")},
        keys=["status"],
    )
    summary = summarize_diffs(diffs)

    result = {
        "run_id": run_id,
        "validation": validation,
        "glue": glue_result,
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
    elif action == "finalize":
        body = _finalize(event)
    else:
        body = {"error": f"unknown action: {action}"}

    return {"statusCode": 200, "body": json.dumps(body)}
