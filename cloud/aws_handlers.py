"""Thin AWS event adapters. Core processing stays in cloud.pipeline."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
from decimal import Decimal
from functools import lru_cache
from urllib.parse import unquote_plus

from .ai import GeminiClassifier
from .core import ClaimValidationError
from .pipeline import prepare_raw_claim, process_claim
from .queries import claim_view, summarize


def _boto3():
    import boto3  # Installed in the backend container; imported only by AWS adapters.

    return boto3


@lru_cache(maxsize=4)
def _secret(arn: str) -> str:
    return _boto3().client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]


def _api_token() -> str:
    local = os.environ.get("API_BEARER_TOKEN")
    if local:
        return local
    return _secret(os.environ["API_TOKEN_SECRET_ARN"])


def _authorized(event: dict) -> bool:
    headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
    supplied = headers.get("authorization", "")
    expected = "Bearer " + _api_token()
    return hmac.compare_digest(supplied, expected)


def _native(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    if isinstance(value, list):
        return [_native(item) for item in value]
    if isinstance(value, dict):
        return {key: _native(item) for key, item in value.items()}
    return value


def _response(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(_native(body))}


def _table():
    return _boto3().resource("dynamodb").Table(os.environ["CLAIMS_TABLE"])


def _all_records(table) -> list[dict]:
    records = []
    args = {}
    while True:
        result = table.scan(**args)
        records.extend(result.get("Items", []))
        if "LastEvaluatedKey" not in result:
            return records
        args["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def api_handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod") or "").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    if method == "GET" and path == "/health":
        return _response(200, {"status": "ok"})
    if not _authorized(event):
        return _response(401, {"error": "Unauthorized"})

    if method == "POST" and path == "/claims":
        try:
            raw_body = event.get("body") or ""
            if event.get("isBase64Encoded"):
                raw_body = base64.b64decode(raw_body).decode("utf-8")
            if len(raw_body.encode("utf-8")) > 100_000:
                return _response(413, {"error": "Claim exceeds 100 KB"})
            claim = prepare_raw_claim(json.loads(raw_body))
        except (ValueError, UnicodeDecodeError, binascii.Error, ClaimValidationError) as error:
            return _response(400, {"error": str(error)[:200]})
        key = f"raw/{claim['complaint_id']}.json"
        _boto3().client("s3").put_object(
            Bucket=os.environ["RAW_BUCKET"], Key=key,
            Body=json.dumps(claim, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return _response(202, {"complaint_id": claim["complaint_id"], "status": "accepted", "raw_key": key})

    if method == "GET" and path == "/summary":
        records = _all_records(_table())
        return _response(200, summarize(_native(records)))

    if method == "GET" and path == "/claims":
        params = event.get("queryStringParameters") or {}
        try:
            limit = max(1, min(int(params.get("limit", "100")), 200))
            start = json.loads(base64.urlsafe_b64decode(params["cursor"] + "===").decode("utf-8")) if params.get("cursor") else None
        except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
            return _response(400, {"error": "Invalid pagination parameters"})
        scan_args = {"Limit": limit}
        if start:
            scan_args["ExclusiveStartKey"] = start
        result = _table().scan(**scan_args)
        cursor = None
        if result.get("LastEvaluatedKey"):
            encoded = json.dumps(_native(result["LastEvaluatedKey"])).encode("utf-8")
            cursor = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
        items = [claim_view(_native(item)) for item in result.get("Items", []) if item.get("processing_status") == "processed"]
        return _response(200, {"items": items, "next_cursor": cursor})

    if method == "GET" and path.startswith("/claims/"):
        complaint_id = path.removeprefix("/claims/")
        if not complaint_id or "/" in complaint_id:
            return _response(404, {"error": "Not found"})
        item = _table().get_item(Key={"complaint_id": complaint_id}).get("Item")
        if not item:
            return _response(404, {"error": "Not found"})
        return _response(200, claim_view(_native(item)))

    return _response(404, {"error": "Not found"})


def process_handler(event, context):
    s3 = _boto3().client("s3")
    table = _table()
    classifier = GeminiClassifier(api_key=_secret(os.environ["GEMINI_SECRET_ARN"]))
    processed = 0
    skipped = 0
    for entry in event.get("Records", []):
        bucket = entry["s3"]["bucket"]["name"]
        key = unquote_plus(entry["s3"]["object"]["key"])
        if not key.startswith("raw/") or not key.endswith(".json"):
            continue
        source = s3.get_object(Bucket=bucket, Key=key)
        etag = source.get("ETag", "").strip('"')
        payload = json.loads(source["Body"].read().decode("utf-8"))
        claim = prepare_raw_claim(payload)
        existing = table.get_item(Key={"complaint_id": claim["complaint_id"]}).get("Item")
        if existing and existing.get("source_etag") == etag and existing.get("processing_status") == "processed":
            skipped += 1
            continue
        item = process_claim(claim, classifier)
        item.update({"raw_s3_key": key, "source_etag": etag, "ai_model": classifier.model})
        try:
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(complaint_id) OR source_etag <> :etag",
                ExpressionAttributeValues={":etag": etag},
            )
        except Exception as error:
            code = getattr(error, "response", {}).get("Error", {}).get("Code")
            if code == "ConditionalCheckFailedException":
                skipped += 1
                continue
            raise
        processed += 1
    return {"processed": processed, "skipped": skipped}
