# Build and deploy

The local flow is ready. The live deployment uses AWS API Gateway, Lambda, S3, DynamoDB, SQS, Secrets Manager, ECR, CloudWatch, and App Runner. It needs an AWS account, a Gemini API key, AWS CLI credentials, Terraform, and an AWS region where Lambda and App Runner are available. Docker Desktop is optional because GitHub Actions can build both deployment images. Do not paste the Gemini key or API bearer token into this repository or a chat. Create an [AWS cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html) before deploying; App Runner runs a web service continuously.

## 1. Verify locally

From the project root, run:

```powershell
python -m unittest discover -s tests -v
python -m cloud.local_server
```

In another terminal, submit a small batch:

```powershell
$env:API_BEARER_TOKEN = 'local-demo-token'
python backfill.py --limit 20
```

The local API is `http://127.0.0.1:8080`. In this workspace it writes JSON to the workspace `work/local_data` directory and explicitly uses a mock classifier. The Streamlit dashboard can run locally after installing `requirements-dashboard.txt` and setting `API_BASE_URL` and `API_BEARER_TOKEN`. It asks the viewer to enter the same token before showing complaint data.

## 2. Create AWS and Gemini credentials

Create an AWS account and configure AWS CLI access using an IAM Identity Center or other suitable non-root identity. Pick one AWS region and use it consistently. Obtain a Gemini API key from [Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key). The default model is configurable through Terraform's `gemini_model` variable.

## 3. Bootstrap ECR and secrets with Terraform

Run Terraform in `infra/bootstrap` with `aws_region` set to the chosen region:

```powershell
cd infra/bootstrap
terraform init
terraform apply -var="aws_region=ap-south-1"
terraform output
cd ../..
```

Replace `ap-south-1` with the region you selected and use it throughout. The outputs provide two private ECR repository URLs and two Secrets Manager ARNs. Add **plain text** secret values in the AWS Secrets Manager console: the Gemini API key in `gemini-api-key`, and a long random bearer token in `api-bearer-token`. Terraform deliberately does not manage secret values, so they are not written to Terraform state. Keep Terraform state private because it still contains infrastructure identifiers.

## 4. Build and push two containers

### Option A: GitHub Actions, without Docker Desktop

The repository includes `.github/workflows/build-images.yml`. It uses GitHub's hosted Linux runner to build the backend and dashboard images and push them to ECR, so Docker Desktop is not required on the developer machine.

The bootstrap stack creates a least-privilege GitHub OIDC role restricted to the `main` branch of `github_repository`. Apply the bootstrap stack with the repository name when it differs from the default:

```powershell
terraform -chdir=infra/bootstrap apply -var="aws_region=ap-south-1" -var="github_repository=OWNER/REPOSITORY"
```

After the bootstrap apply, configure these GitHub Actions repository variables:

```powershell
$roleArn = terraform -chdir=infra/bootstrap output -raw github_actions_role_arn
gh variable set AWS_ROLE_ARN --body $roleArn
gh variable set AWS_REGION --body 'ap-south-1'
```

Push the workflow to the repository's `main` branch, then run it:

```powershell
gh workflow run build-images.yml --ref main
gh run watch
```

The workflow summary prints immutable backend and dashboard image addresses tagged with the Git commit SHA. Use those addresses for the application Terraform variables in step 5.

The workflow uses temporary OIDC credentials. Do not add AWS access keys to GitHub secrets.

### Option B: local Docker Desktop

From the project root, build the backend and dashboard with the repository URLs from the bootstrap output. Use an immutable image tag for each deployment, such as a Git commit ID. On Windows, Docker Desktop must be running with Linux containers. AWS documents `--platform linux/amd64 --provenance=false` for Lambda container builds. [Lambda container image guide](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html)

```powershell
docker buildx build --platform linux/amd64 --provenance=false -f Dockerfile.backend -t <BACKEND_ECR_URI>:<TAG> --load .
docker buildx build --platform linux/amd64 --provenance=false -f Dockerfile.dashboard -t <DASHBOARD_ECR_URI>:<TAG> --load .
```

Use the bootstrap outputs for the image URIs, authenticate Docker, and push both tags:

```powershell
$region = 'ap-south-1'
$account = aws sts get-caller-identity --query Account --output text
$registry = "$account.dkr.ecr.$region.amazonaws.com"
aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry
docker push <BACKEND_ECR_URI>:<TAG>
docker push <DASHBOARD_ECR_URI>:<TAG>
```

## 5. Apply the application stack

Run Terraform in `infra/app`, passing the same `aws_region` and both image URIs from the GitHub workflow:

```powershell
cd infra/app
terraform init
terraform apply -var="aws_region=ap-south-1" -var="backend_image_uri=<BACKEND_ECR_URI>:<TAG>" -var="dashboard_image_uri=<DASHBOARD_ECR_URI>:<TAG>"
terraform output
cd ../..
```

The outputs are the REST API URL, Streamlit App Runner URL, raw bucket, DynamoDB table, and failed-event queue. App Runner receives the API token from Secrets Manager, and the worker reads the Gemini key from Secrets Manager at runtime. The dashboard requires the viewer to enter the shared token. [App Runner ECR access](https://docs.aws.amazon.com/apprunner/latest/dg/service-source-image.html) · [App Runner secrets](https://docs.aws.amazon.com/apprunner/latest/dg/env-variable.html)

## 6. Smoke test and seed carefully

Check `GET /health`, submit one non-sensitive test claim to `POST /claims`, and verify that it appears in `GET /summary` and the dashboard. Inspect CloudWatch logs and the worker failure queue if it does not. Set `API_BASE_URL` and `API_BEARER_TOKEN` in a local terminal, then use `python backfill.py --limit 20` for a small sample. `--all` submits all 1,578 reports and will trigger Gemini calls and AWS charges.

## 7. Publish the code to GitHub

Create a repository and push this source tree after reviewing `git status`. The `.gitignore` excludes raw narrative CSVs, model artifacts, local files, Terraform state, variables, and environment files. The included GitHub Actions workflow checks Python tests, syntax, and Terraform formatting on pushes and pull requests. Keep the official source URLs and preparation script in the repository so the data can be reproduced without publishing personal information. A deployment workflow can be added after the repository and AWS account exist, using [GitHub OIDC for AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) rather than long-lived AWS keys.

## Review constraints

The Terraform files have been formatted, but a live `terraform validate` and `apply` require the AWS provider download and an account. Container builds require Docker Desktop. Gemini's structured response contract has a mocked test; a live inference call needs the user's API key. The local REST flow was exercised with 20 records and the mock provider.
