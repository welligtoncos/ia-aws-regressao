"""Registra partições no Glue Data Catalog para consulta no Athena."""

import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _partition_descriptor(table_meta, location):
    storage = dict(table_meta["StorageDescriptor"])
    storage["Location"] = location
    return storage


def register_partitions(df, bucket, database, table, prefix, region="us-east-1"):
    """Cria/atualiza partições (ano, mes, segmento) após gravar Parquet no S3."""
    if not database or not table:
        logger.warning("OUTPUT_DATABASE/OUTPUT_TABLE ausentes; catálogo não atualizado.")
        return

    glue = boto3.client("glue", region_name=region)
    table_meta = glue.get_table(DatabaseName=database, Name=table)["Table"]
    base = f"s3://{bucket}/{prefix.strip('/')}/"

    for (ano, mes, segmento), _ in df.groupby(["ano", "mes", "segmento"]):
        location = f"{base}ano={ano}/mes={mes}/segmento={segmento}/"
        values = [str(int(ano)), str(int(mes)), str(segmento)]
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
            logger.info("Partição criada: %s", "/".join(values))
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "AlreadyExistsException":
                raise
            glue.update_partition(
                DatabaseName=database,
                TableName=table,
                PartitionValueList=values,
                PartitionInput=part_input,
            )
            logger.info("Partição atualizada: %s", "/".join(values))
