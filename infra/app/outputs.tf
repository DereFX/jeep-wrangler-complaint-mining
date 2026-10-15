output "api_url" {
  value = aws_apigatewayv2_api.claims.api_endpoint
}

output "dashboard_url" {
  value = "https://${aws_apprunner_service.dashboard.service_url}"
}

output "raw_bucket" {
  value = aws_s3_bucket.raw.bucket
}

output "claims_table" {
  value = aws_dynamodb_table.claims.name
}

output "bulk_loader_function" {
  value = aws_lambda_function.bulk_loader.function_name
}

output "worker_failure_queue" {
  value = aws_sqs_queue.worker_failures.name
}
