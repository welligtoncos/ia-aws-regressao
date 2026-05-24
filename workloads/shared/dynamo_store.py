"""Persistência de resultados de automação no DynamoDB."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from workloads.shared.aws_clients import get_dynamodb_resource


def _sanitize_for_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _sanitize_for_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_dynamo(v) for v in value]
    return value


def save_run_result(
    run_id: str,
    status: str,
    payload: Dict[str, Any],
    table_name: Optional[str] = None,
) -> None:
    """Grava ou atualiza o resultado de uma execução."""
    table = get_dynamodb_resource().Table(table_name or os.environ["DYNAMODB_TABLE"])
    table.put_item(
        Item=_sanitize_for_dynamo({
            "run_id": run_id,
            "status": status,
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    )


def get_run_result(run_id: str, table_name: Optional[str] = None) -> Dict[str, Any]:
    """Recupera resultado de uma execução pelo run_id."""
    table = get_dynamodb_resource().Table(table_name or os.environ["DYNAMODB_TABLE"])
    response = table.get_item(Key={"run_id": run_id})
    return response.get("Item", {})
