resource "aws_apprunner_auto_scaling_configuration_version" "dashboard" {
  auto_scaling_configuration_name = "${var.project_name}-dashboard"
  max_concurrency                 = 20
  max_size                        = 1
  min_size                        = 1
}

resource "aws_apprunner_service" "dashboard" {
  service_name                   = "${var.project_name}-dashboard"
  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.dashboard.arn

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr.arn
    }
    auto_deployments_enabled = false
    image_repository {
      image_identifier      = var.dashboard_image_uri
      image_repository_type = "ECR"
      image_configuration {
        port = "8501"
        runtime_environment_variables = {
          API_BASE_URL = aws_apigatewayv2_api.claims.api_endpoint
        }
        runtime_environment_secrets = {
          API_BEARER_TOKEN = data.aws_secretsmanager_secret.api_token.arn
        }
      }
    }
  }

  instance_configuration {
    cpu               = "1024"
    memory            = "2048"
    instance_role_arn = aws_iam_role.apprunner_instance.arn
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = "/_stcore/health"
  }

  depends_on = [aws_iam_role_policy_attachment.apprunner_ecr, aws_iam_role_policy.apprunner_secret]
}
