"""Validate every PBIR file in the report against the JSON schema it declares ($schema).

Schemas are downloaded once into .schema-cache/. Exit code 1 on any violation.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".schema-cache"


def schema(url: str) -> dict:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / (url.split("/definition/")[-1].replace("/", "_") if "/definition/" in url
                    else url.rsplit("/", 3)[-3] + ".json")
    if not path.exists():
        with urllib.request.urlopen(url, timeout=30) as r:
            path.write_bytes(r.read())
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    files = sorted((ROOT / "MarketingPerformance.Report").rglob("*.json")) + \
        sorted((ROOT / "MarketingPerformance.Report").glob("*.pbir"))
    errors = 0
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        url = doc.get("$schema")
        if not url:
            print(f"no $schema: {f}")
            errors += 1
            continue
        for e in Draft7Validator(schema(url)).iter_errors(doc):
            print(f"{f.relative_to(ROOT)}: {'/'.join(map(str, e.path))}: {e.message[:200]}")
            errors += 1
    print(f"{len(files)} files checked, {errors} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
