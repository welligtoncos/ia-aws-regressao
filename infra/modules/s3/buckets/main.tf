locals {
  bucket_suffix = "${var.project_name}-${var.environment}"
}

resource "aws_s3_bucket" "source" {
  bucket        = "${local.bucket_suffix}-source"
  force_destroy = var.force_destroy

  tags = merge(var.tags, { Name = "${local.bucket_suffix}-source", Purpose = "input" })
}

resource "aws_s3_bucket" "output" {
  bucket        = "${local.bucket_suffix}-output"
  force_destroy = var.force_destroy

  tags = merge(var.tags, { Name = "${local.bucket_suffix}-output", Purpose = "output" })
}

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${local.bucket_suffix}-artifacts"
  force_destroy = var.force_destroy

  tags = merge(var.tags, { Name = "${local.bucket_suffix}-artifacts", Purpose = "artifacts" })
}

resource "aws_s3_bucket_versioning" "source" {
  bucket = aws_s3_bucket.source.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "output" {
  bucket = aws_s3_bucket.output.id

  versioning_configuration {
    status = "Enabled"
  }
}
