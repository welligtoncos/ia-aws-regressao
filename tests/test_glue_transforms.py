"""Testes das transformações Glue."""

from workloads.glue.src.transforms import aggregate_by_key


def test_aggregate_by_key():
    records = [
        {"category": "A", "value": 10},
        {"category": "A", "value": 5},
        {"category": "B", "value": 3},
    ]
    assert aggregate_by_key(records, "category", "value") == {"A": 15.0, "B": 3.0}
