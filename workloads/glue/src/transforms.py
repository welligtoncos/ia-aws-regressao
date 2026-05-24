"""Transformações e agregações reutilizáveis para jobs Glue."""

from typing import Iterable


def aggregate_by_key(records: Iterable[dict], group_field: str, value_field: str) -> dict:
    """Soma valores numéricos agrupados por chave."""
    result: dict = {}
    for record in records:
        key = record[group_field]
        value = float(record[value_field])
        result[key] = result.get(key, 0.0) + value
    return result
