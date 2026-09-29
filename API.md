# REST contract

The public HTTP shape is standard JSON over HTTPS. API Gateway is the AWS entry point; clients do not need an AWS SDK. All routes except `/health` require `Authorization: Bearer <token>`. The token is stored in AWS Secrets Manager for deployment.

## POST `/claims`

Submit one complaint. The body accepts the current cleaned dataset schema:

```json
{
  "complaint_id": "DEMO-001",
  "received_date": "2025-10-12",
  "model_year": 2024,
  "component": "ELECTRICAL SYSTEM",
  "complaint_source_code": "DEALER",
  "narrative": "After a software update, the vehicle shut down while driving and needed a restart."
}
```

`complaint_source_code` can be `DEALER`, `CUSTOMER`, or a source code from the NHTSA file. The body can alternatively contain `text` and a `metadata` JSON object with the remaining fields. Required values are complaint ID, received date, model year, and text. IDs may contain letters, digits, underscores, and hyphens. Text must contain 30–20,000 characters.

Response: `202 {"complaint_id":"DEMO-001","status":"accepted","raw_key":"raw/DEMO-001.json"}`. Processing is asynchronous on AWS after S3 receives the JSON object. The local development server processes immediately using an explicitly labeled mock classifier.

## GET `/summary`

Returns total processed claims, counts by issue family and model year, monthly counts by issue, and a human-review count. This endpoint scans the demonstration-sized DynamoDB table; a larger production system should maintain aggregates.

## GET `/claims?limit=100&cursor=...`

Returns processed claims and `next_cursor`. Maximum page size is 200. The cursor is opaque to clients.

## GET `/claims/{complaint_id}`

Returns one processed claim with its sanitized narrative and AI label.

## GET `/health`

Returns `{"status":"ok"}` without authentication.

## AI labels

The issue taxonomy began with the eight text clusters in `CLUSTER_REVIEW.md`. Gemini assigns new complaints to one family, or `other`, through `classify_claim()`. This is a classification into previously discovered themes, not a fresh unsupervised clustering run on each new claim. Human review is required before treating labels as defect findings.
