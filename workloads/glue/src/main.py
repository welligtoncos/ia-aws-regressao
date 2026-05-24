"""
Glue Job PySpark genérico (automação ETL).
Para treino XGBoost, use app/src/glue_train.py no S3 — ver scripts/upload_glue_assets.ps1
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

from util import get_structured_logger, log_job_context

try:
    from workloads.glue.src.transforms import aggregate_by_key
except ImportError:
    from transforms import aggregate_by_key


def main() -> None:
    args = getResolvedOptions(
        sys.argv,
        ["JOB_NAME", "SOURCE_BUCKET", "OUTPUT_BUCKET", "DYNAMODB_TABLE"],
    )

    logger = get_structured_logger("glue-automation")
    log_job_context(logger, args)

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    run_id = "manual-run"
    if "--run_id" in sys.argv:
        run_id = getResolvedOptions(sys.argv, ["run_id"])["run_id"]

    source_path = f"s3://{args['SOURCE_BUCKET']}/raw/"
    output_path = f"s3://{args['OUTPUT_BUCKET']}/processed/{run_id}/"

    logger.info("Reading from %s", source_path)
    df = spark.read.option("header", "true").option("inferSchema", "true").csv(source_path)

    df_transformed = (
        df.withColumn("numeric_value", F.col("value").cast("double"))
        .withColumn("processed_at", F.current_timestamp())
        .groupBy("category")
        .agg(
            F.avg("numeric_value").alias("avg_value"),
            F.sum("numeric_value").alias("total_value"),
            F.count("*").alias("record_count"),
        )
    )

    summary = aggregate_by_key(
        [{"category": row["category"], "value": row["total_value"]} for row in df_transformed.collect()],
        "category",
        "value",
    )
    logger.info("Aggregation summary: %s", summary)

    logger.info("Writing to %s", output_path)
    df_transformed.coalesce(1).write.mode("overwrite").option("header", "true").csv(output_path)

    logger.info("Run %s completed. DynamoDB table: %s", run_id, args["DYNAMODB_TABLE"])

    job.commit()
    logger.info("Glue automation job completed.")


if __name__ == "__main__":
    main()
