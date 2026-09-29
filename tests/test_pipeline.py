import io
import json
import os
import unittest
from unittest.mock import patch

from cloud.ai import GeminiClassifier, MockClassifier, classify_claim
from cloud.core import ClaimValidationError, clean_narrative, normalize_claim
from cloud.pipeline import process_claim
from cloud import aws_handlers


CLAIM = {
    "complaint_id": "TEST-001",
    "received_date": "2025-10-12",
    "model_year": 2024,
    "component": "ELECTRICAL SYSTEM",
    "complaint_source_code": "CUSTOMER",
    "narrative": "After a software update, the vehicle shut down while driving and had to be restarted.",
}


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)]), "ETag": '"demo-etag"'}


class FakeTable:
    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        item = self.items.get(Key["complaint_id"])
        return {"Item": item} if item else {}

    def put_item(self, Item, **kwargs):
        self.items[Item["complaint_id"]] = Item

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}


class FakeBoto3:
    def __init__(self):
        self.s3 = FakeS3()
        self.table = FakeTable()

    def client(self, service):
        if service == "s3":
            return self.s3
        raise AssertionError(service)

    def resource(self, service):
        if service == "dynamodb":
            return self
        raise AssertionError(service)

    def Table(self, name):
        return self.table


class FakeGemini:
    name = "gemini"
    model = "test-gemini"

    def __init__(self, api_key):
        assert api_key == "test-key"

    def classify(self, text):
        return {
            "issue_family": "shutdown_restart",
            "component": "Electrical system",
            "symptom_summary": "Unexpected shutdown after an update",
            "needs_human_review": False,
        }


class PipelineTests(unittest.TestCase):
    def test_schema_and_redaction(self):
        nested = {"text": CLAIM["narrative"], "metadata": {key: value for key, value in CLAIM.items() if key != "narrative"}}
        self.assertEqual(normalize_claim(nested)["complaint_id"], "TEST-001")
        self.assertIn("[EMAIL]", clean_narrative("Contact test@example.com about the failed battery."))
        with self.assertRaises(ClaimValidationError):
            normalize_claim({**CLAIM, "complaint_id": "../bad"})

    def test_mock_pipeline_explicitly_marks_provider(self):
        item = process_claim(CLAIM, MockClassifier())
        self.assertEqual(item["issue_family"], "shutdown_restart")
        self.assertEqual(item["ai_provider"], "mock")

    def test_gemini_boundary_parses_structured_json(self):
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(FakeGemini("test-key").classify("x"))}]}}]}
        def fake_urlopen(request, timeout):
            self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
            body = json.loads(request.data)
            self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["mimeType"], "application/json")
            return io.BytesIO(json.dumps(response).encode("utf-8"))
        with patch("cloud.ai.urlopen", fake_urlopen):
            result = classify_claim(CLAIM["narrative"], GeminiClassifier("test-key", model="gemini-test"))
        self.assertEqual(result["issue_family"], "shutdown_restart")

    def test_aws_adapters_ingest_process_and_query(self):
        fake = FakeBoto3()
        env = {"API_BEARER_TOKEN": "test-token", "RAW_BUCKET": "test-bucket", "CLAIMS_TABLE": "claims", "GEMINI_SECRET_ARN": "demo-secret"}
        event = {
            "requestContext": {"http": {"method": "POST"}}, "rawPath": "/claims",
            "headers": {"authorization": "Bearer test-token"}, "body": json.dumps(CLAIM),
        }
        with patch.dict(os.environ, env), patch.object(aws_handlers, "_boto3", return_value=fake), patch.object(aws_handlers, "_secret", return_value="test-key"), patch.object(aws_handlers, "GeminiClassifier", FakeGemini):
            accepted = aws_handlers.api_handler(event, None)
            self.assertEqual(accepted["statusCode"], 202)
            processed = aws_handlers.process_handler({"Records": [{"s3": {"bucket": {"name": "test-bucket"}, "object": {"key": "raw/TEST-001.json"}}}]}, None)
            self.assertEqual(processed["processed"], 1)
            duplicate = aws_handlers.process_handler({"Records": [{"s3": {"bucket": {"name": "test-bucket"}, "object": {"key": "raw/TEST-001.json"}}}]}, None)
            self.assertEqual(duplicate["skipped"], 1)
            summary = aws_handlers.api_handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/summary", "headers": event["headers"]}, None)
            self.assertEqual(json.loads(summary["body"])["total_claims"], 1)
            unauthorized = aws_handlers.api_handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/summary"}, None)
            self.assertEqual(unauthorized["statusCode"], 401)


if __name__ == "__main__":
    unittest.main()
