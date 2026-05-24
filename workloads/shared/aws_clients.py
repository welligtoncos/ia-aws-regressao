"""Clientes AWS reutilizáveis."""

import os
from typing import Optional

import boto3


def get_s3_client(region: Optional[str] = None):
    return boto3.client("s3", region_name=region or os.getenv("AWS_REGION", "us-east-1"))


def get_dynamodb_resource(region: Optional[str] = None):
    return boto3.resource("dynamodb", region_name=region or os.getenv("AWS_REGION", "us-east-1"))


def get_glue_client(region: Optional[str] = None):
    return boto3.client("glue", region_name=region or os.getenv("AWS_REGION", "us-east-1"))
