resource "aws_s3_bucket" "raw" {
  bucket = "${var.project_name}-raw-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_dynamodb_table" "claims" {
  name         = "${var.project_name}-claims"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "complaint_id"

  attribute {
    name = "complaint_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_sqs_queue" "worker_failures" {
  name                      = "${var.project_name}-worker-failures"
  message_retention_seconds = 1209600
}
