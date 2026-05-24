"""Registra partições existentes no S3 no Glue Data Catalog (bootstrap Athena)."""

import re
import sys

import boto3
from botocore.exceptions import ClientError

PARTITION_RE = re.compile(
    r"processed/([^/]+)/ano=(\d+)/mes=(\d+)/segmento=([^/]+)/"
)


def _partition_descriptor(table_meta, location):
    storage = dict(table_meta["StorageDescriptor"])
    storage["Location"] = location
    return storage


def register_from_s3(bucket, database, table, prefix, region="us-east-1"):
    s3 = boto3.client("s3", region_name=region)
    glue = boto3.client("glue", region_name=region)
    table_meta = glue.get_table(DatabaseName=database, Name=table)["Table"]
    seen = set()
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            match = PARTITION_RE.search(obj["Key"])
            if not match:
                continue
            tbl, ano, mes, segmento = match.groups()
            if tbl != table:
                continue
            key = (ano, mes, segmento)
            if key in seen:
                continue
            seen.add(key)
            location = f"s3://{bucket}/{prefix}ano={ano}/mes={mes}/segmento={segmento}/"
            values = [ano, mes, segmento]
            part_input = {
                "Values": values,
                "StorageDescriptor": _partition_descriptor(table_meta, location),
            }
            try:
                glue.create_partition(
                    DatabaseName=database,
                    TableName=table,
                    PartitionInput=part_input,
                )
                print(f"criada: {values}")
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "AlreadyExistsException":
                    raise
                glue.update_partition(
                    DatabaseName=database,
                    TableName=table,
                    PartitionValueList=values,
                    PartitionInput=part_input,
                )
                print(f"atualizada: {values}")

    print(f"Total partições: {len(seen)}")


if __name__ == "__main__":
    register_from_s3(
        bucket=sys.argv[1] if len(sys.argv) > 1 else "saldo-previsto-data-prod",
        database=sys.argv[2] if len(sys.argv) > 2 else "saldo_previsto_db_prod",
        table=sys.argv[3] if len(sys.argv) > 3 else "tb_saldo_previsto_prod",
        prefix=f"processed/{sys.argv[3] if len(sys.argv) > 3 else 'tb_saldo_previsto_prod'}/",
    )
