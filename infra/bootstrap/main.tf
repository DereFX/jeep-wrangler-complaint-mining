terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type = string
}

variable "project_name" {
  type    = string
  default = "wrangler-claims"
}

resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "dashboard" {
  name                 = "${var.project_name}-dashboard"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

data "aws_iam_policy_document" "lambda_ecr" {
  statement {
    sid     = "LambdaImageRetrievalPolicy"
    actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_ecr_repository_policy" "backend_lambda" {
  repository = aws_ecr_repository.backend.name
  policy     = data.aws_iam_policy_document.lambda_ecr.json
}

resource "aws_secretsmanager_secret" "gemini" {
  name = "${var.project_name}/gemini-api-key"
}

resource "aws_secretsmanager_secret" "api_token" {
  name = "${var.project_name}/api-bearer-token"
}

output "backend_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "dashboard_repository_url" {
  value = aws_ecr_repository.dashboard.repository_url
}

output "gemini_secret_arn" {
  value = aws_secretsmanager_secret.gemini.arn
}

output "api_token_secret_arn" {
  value = aws_secretsmanager_secret.api_token.arn
}
