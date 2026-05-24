output "bucket_names" {
  description = "Nomes dos buckets criados."
  value = {
    source    = aws_s3_bucket.source.bucket
    output    = aws_s3_bucket.output.bucket
    artifacts = aws_s3_bucket.artifacts.bucket
  }
}

output "bucket_arns" {
  description = "ARNs dos buckets criados."
  value = {
    source    = aws_s3_bucket.source.arn
    output    = aws_s3_bucket.output.arn
    artifacts = aws_s3_bucket.artifacts.arn
  }
}
