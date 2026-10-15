variable "github_repository" {
  type        = string
  description = "GitHub repository allowed to build and push deployment images"
  default     = "DereFX/jeep-wrangler-complaint-mining"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use the owner/repository format."
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  client_id_list = [
    "sts.amazonaws.com",
  ]
}

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_ecr" {
  name               = "${var.project_name}-github-ecr"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json
}

data "aws_iam_policy_document" "github_ecr" {
  statement {
    sid       = "EcrLogin"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushProjectImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [
      aws_ecr_repository.backend.arn,
      aws_ecr_repository.dashboard.arn,
    ]
  }
}

resource "aws_iam_role_policy" "github_ecr" {
  name   = "${var.project_name}-github-ecr"
  role   = aws_iam_role.github_ecr.id
  policy = data.aws_iam_policy_document.github_ecr.json
}

output "github_actions_role_arn" {
  description = "Set this value as the GitHub Actions repository variable AWS_ROLE_ARN"
  value       = aws_iam_role.github_ecr.arn
}
