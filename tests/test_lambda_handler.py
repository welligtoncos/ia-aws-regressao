"""Testes do handler Lambda."""

import json
import os
from unittest.mock import patch

from workloads.aws_lambda.src.handler import lambda_handler


class FakeContext:
    aws_request_id = "test-request-id"


@patch("workloads.aws_lambda.src.handler.save_run_result")
@patch("workloads.aws_lambda.src.handler.get_s3_client")
def test_lambda_validate(mock_s3_client, mock_save):
    os.environ["SOURCE_BUCKET"] = "test-bucket"
    os.environ["DYNAMODB_TABLE"] = "test-table"

    mock_s3_client.return_value.list_objects_v2.return_value = {
        "Contents": [{"Key": "raw/file.csv"}]
    }

    response = lambda_handler({"action": "validate", "run_id": "run-1"}, FakeContext())
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["status"] == "validated"
    mock_save.assert_called_once()


@patch("workloads.aws_lambda.src.handler.save_run_result")
def test_lambda_finalize(mock_save):
    os.environ["DYNAMODB_TABLE"] = "test-table"

    response = lambda_handler(
        {
            "action": "finalize",
            "run_id": "run-1",
            "validation": {"status": "validated"},
            "glue": {"JobRunState": "SUCCEEDED"},
        },
        FakeContext(),
    )
    body = json.loads(response["body"])

    assert body["status"] == "success"
    mock_save.assert_called_once()
