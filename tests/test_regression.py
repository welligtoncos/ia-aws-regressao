"""Testes de regressão/comparação genéricos."""

from workloads.shared.regression import compare_records, summarize_diffs


def test_compare_records_no_diff():
    assert compare_records({"a": 1}, {"a": 1}, ["a"]) == []


def test_compare_records_with_diff():
    diffs = compare_records({"a": 1}, {"a": 2}, ["a"])
    assert len(diffs) == 1
    assert "expected=1" in diffs[0]


def test_summarize_diffs():
    summary = summarize_diffs(["x", "y"])
    assert summary["passed"] is False
    assert summary["diff_count"] == 2
