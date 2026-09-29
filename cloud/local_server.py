"""Local REST demo using JSON files and the explicit mock classifier.

Run: python -m cloud.local_server
This is for development only. AWS uses API Gateway, S3, Lambda, and DynamoDB.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .ai import MockClassifier
from .core import ClaimValidationError
from .pipeline import prepare_raw_claim, process_claim
from .queries import claim_view, summarize


class LocalStore:
    def __init__(self, root: Path):
        self.raw = root / "raw"
        self.processed = root / "processed"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)

    def put(self, claim: dict) -> None:
        claim_id = claim["complaint_id"]
        self._write(self.raw / f"{claim_id}.json", claim)
        self._write(self.processed / f"{claim_id}.json", process_claim(claim, MockClassifier()))

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    def all(self) -> list[dict]:
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.processed.glob("*.json")]

    def get(self, claim_id: str) -> dict | None:
        path = self.processed / f"{claim_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class Handler(BaseHTTPRequestHandler):
    store: LocalStore
    token: str

    def _json(self, status: int, value: dict) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.token}"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._json(200, {"status": "ok", "mode": "local-mock"})
        if not self._authorized():
            return self._json(401, {"error": "Unauthorized"})
        if parsed.path == "/summary":
            return self._json(200, summarize(self.store.all()))
        if parsed.path == "/claims":
            params = parse_qs(parsed.query)
            try:
                limit = max(1, min(int(params.get("limit", ["100"])[0]), 200))
                offset = max(0, int(params.get("cursor", ["0"])[0]))
            except ValueError:
                return self._json(400, {"error": "Invalid pagination parameters"})
            records = sorted(self.store.all(), key=lambda row: (row["received_date"], row["complaint_id"]), reverse=True)
            page = records[offset:offset + limit]
            next_cursor = str(offset + limit) if offset + limit < len(records) else None
            return self._json(200, {"items": [claim_view(row) for row in page], "next_cursor": next_cursor})
        if parsed.path.startswith("/claims/"):
            claim_id = parsed.path.removeprefix("/claims/")
            if not claim_id or "/" in claim_id or ".." in claim_id:
                return self._json(404, {"error": "Not found"})
            record = self.store.get(claim_id)
            return self._json(200, claim_view(record)) if record else self._json(404, {"error": "Not found"})
        return self._json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/claims":
            return self._json(404, {"error": "Not found"})
        if not self._authorized():
            return self._json(401, {"error": "Unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 100_000:
                return self._json(413, {"error": "Claim must be at most 100 KB"})
            claim = prepare_raw_claim(json.loads(self.rfile.read(length)))
        except (ValueError, ClaimValidationError, UnicodeDecodeError) as error:
            return self._json(400, {"error": str(error)[:200]})
        self.store.put(claim)
        return self._json(202, {"complaint_id": claim["complaint_id"], "status": "accepted"})


def main() -> None:
    host = "127.0.0.1"
    port = int(os.environ.get("LOCAL_API_PORT", "8080"))
    project = Path(__file__).resolve().parents[1]
    scratch = project.parent.parent / "work" if project.parent.name == "outputs" else project / "work"
    Handler.store = LocalStore(Path(os.environ.get("LOCAL_DATA_DIR", str(scratch / "local_data"))))
    Handler.token = os.environ.get("LOCAL_API_TOKEN", "local-demo-token")
    print(f"Local mock API at http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
