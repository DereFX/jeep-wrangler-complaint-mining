"""Submit existing cleaned complaints to the REST API in small, explicit batches.

Run: API_BASE_URL=http://127.0.0.1:8080 API_BEARER_TOKEN=local-demo-token \
     python backfill.py --limit 20

Use --all only when the destination and Gemini cost are intended.
"""

import argparse
import csv
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "complaints.csv")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--all", action="store_true", help="Submit every input row; may incur Gemini and AWS charges")
    args = parser.parse_args()
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    token = os.environ.get("API_BEARER_TOKEN")
    if not token:
        parser.error("API_BEARER_TOKEN is required")
    if args.limit < 1:
        parser.error("--limit must be positive")
    accepted = 0
    with args.input.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if not args.all and accepted >= args.limit:
                break
            claim = {key: row[key] for key in (
                "complaint_id", "received_date", "model_year", "component",
                "complaint_source_code", "narrative",
            )}
            claim["model_year"] = int(claim["model_year"])
            request = Request(
                base + "/claims",
                data=json.dumps(claim, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
                method="POST",
            )
            with urlopen(request, timeout=30) as response:
                if response.status != 202:
                    raise RuntimeError(f"Unexpected status {response.status}")
            accepted += 1
    print(f"Submitted {accepted} claims to {base}")


if __name__ == "__main__":
    main()
