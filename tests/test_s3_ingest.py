"""Testes de detecção de dados novos em S3."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from workloads.shared.s3_ingest import check_new_data, should_run_simulated_micro


@patch("workloads.shared.s3_ingest.get_watermark")
@patch("workloads.shared.s3_ingest.list_incoming_files")
def test_check_new_data_unprocessed_files(mock_list, mock_wm):
    mock_wm.return_value = {"processed_keys": {"incoming/a.csv": "old-etag"}}
    mock_list.return_value = [
        {"key": "incoming/a.csv", "etag": "new-etag", "last_modified": "2026-01-01T00:00:00+00:00"},
    ]

    result = check_new_data("bucket", ingest_simulated=False)

    assert result["has_new_data"] is True
    assert result["new_file_keys"] == ["incoming/a.csv"]
    assert result["simulated_due"] is False


@patch("workloads.shared.s3_ingest.get_watermark")
@patch("workloads.shared.s3_ingest.list_incoming_files")
def test_check_new_data_micro_throttle(mock_list, mock_wm):
    mock_list.return_value = []
    recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    mock_wm.return_value = {"last_simulated_at": recent}

    throttled = check_new_data(
        "bucket",
        ingest_simulated=True,
        ingest_mode="micro",
        step_minutes=10,
    )
    assert throttled["simulated_due"] is False
    assert throttled["has_new_data"] is False

    old = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    mock_wm.return_value = {"last_simulated_at": old}
    due = check_new_data(
        "bucket",
        ingest_simulated=True,
        ingest_mode="micro",
        step_minutes=10,
    )
    assert due["simulated_due"] is True
    assert due["has_new_data"] is True


@patch("workloads.shared.s3_ingest.get_watermark")
def test_should_run_simulated_micro_no_watermark(mock_wm):
    mock_wm.return_value = {}
    assert should_run_simulated_micro(10) is True


@patch("workloads.shared.s3_ingest.get_watermark")
def test_should_run_simulated_micro_after_interval(mock_wm):
    old = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    mock_wm.return_value = {"last_simulated_at": old}
    assert should_run_simulated_micro(10) is True
