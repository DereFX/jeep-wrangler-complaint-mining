terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

variable "aws_region" {
  type = string
}

variable "project_name" {
  type    = string
  default = "wrangler-claims"
}

variable "backend_image_uri" {
  type        = string
  description = "Pushed private ECR backend image URI, preferably with an immutable tag"
}

variable "dashboard_image_uri" {
  type        = string
  description = "Pushed private ECR Streamlit image URI, preferably with an immutable tag"
}

variable "gemini_model" {
  type    = string
  default = "gemini-3.8-flash"
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_secretsmanager_secret" "gemini" {
  name = "${var.project_name}/gemini-api-key"
}

data "aws_secretsmanager_secret" "api_token" {
  name = "${var.project_name}/api-bearer-token"
}
