resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.project_name}-api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.project_name}-worker"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "bulk_loader" {
  name              = "/aws/lambda/${var.project_name}-bulk-loader"
  retention_in_days = 14
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project_name}-api"
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = var.backend_image_uri
  timeout       = 20
  memory_size   = 512

  image_config {
    command = ["cloud.aws_handlers.api_handler"]
  }

  environment {
    variables = {
      RAW_BUCKET           = aws_s3_bucket.raw.bucket
      CLAIMS_TABLE         = aws_dynamodb_table.claims.name
      API_TOKEN_SECRET_ARN = data.aws_secretsmanager_secret.api_token.arn
    }
  }

  depends_on = [aws_iam_role_policy_attachment.api_logs, aws_cloudwatch_log_group.api]
}

resource "aws_lambda_function" "worker" {
  function_name = "${var.project_name}-worker"
  role          = aws_iam_role.worker.arn
  package_type  = "Image"
  image_uri     = var.backend_image_uri
  timeout       = 120
  memory_size   = 1024

  image_config {
    command = ["cloud.aws_handlers.process_handler"]
  }

  environment {
    variables = {
      CLAIMS_TABLE      = aws_dynamodb_table.claims.name
      GEMINI_SECRET_ARN = data.aws_secretsmanager_secret.gemini.arn
      GEMINI_MODEL      = var.gemini_model
    }
  }

  depends_on = [aws_iam_role_policy_attachment.worker_logs, aws_cloudwatch_log_group.worker]
}

resource "aws_lambda_function" "bulk_loader" {
  function_name = "${var.project_name}-bulk-loader"
  role          = aws_iam_role.bulk_loader.arn
  package_type  = "Image"
  image_uri     = var.backend_image_uri
  timeout       = 300
  memory_size   = 512

  image_config {
    command = ["cloud.aws_handlers.bulk_import_handler"]
  }

  environment {
    variables = {
      BULK_BUCKET  = aws_s3_bucket.raw.bucket
      BULK_KEY     = "datasets/complaints.csv"
      CLAIMS_TABLE = aws_dynamodb_table.claims.name
    }
  }

  depends_on = [aws_iam_role_policy_attachment.bulk_loader_logs, aws_cloudwatch_log_group.bulk_loader]
}

resource "aws_lambda_function_event_invoke_config" "worker" {
  function_name                = aws_lambda_function.worker.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600
  destination_config {
    on_failure {
      destination = aws_sqs_queue.worker_failures.arn
    }
  }
}

resource "aws_lambda_permission" "s3_worker" {
  statement_id  = "AllowRawBucketEvents"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.worker.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.raw.arn
}

resource "aws_s3_bucket_notification" "raw" {
  bucket = aws_s3_bucket.raw.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.worker.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = ".json"
  }
  depends_on = [aws_lambda_permission.s3_worker]
}

resource "aws_apigatewayv2_api" "claims" {
  name          = "${var.project_name}-http"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.claims.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post_claims" {
  api_id    = aws_apigatewayv2_api.claims.id
  route_key = "POST /claims"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "get_claims" {
  api_id    = aws_apigatewayv2_api.claims.id
  route_key = "GET /claims"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "get_claim" {
  api_id    = aws_apigatewayv2_api.claims.id
  route_key = "GET /claims/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "summary" {
  api_id    = aws_apigatewayv2_api.claims.id
  route_key = "GET /summary"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.claims.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.claims.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.claims.execution_arn}/*/*"
}
