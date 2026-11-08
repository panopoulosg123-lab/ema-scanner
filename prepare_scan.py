"""Prepare a single stable list of assets for all workers."""
import json
import os
from pathlib import Path
from scanner import expanded_universe

limit = max(1, int(os.environ.get("SCAN_TARGET", "2000")))
items = expanded_universe()[:limit]
if not items:
    raise SystemExit("No assets available for this scan")
path = Path("manifest") / "assets.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
print(f"Prepared {len(items)} assets for 18 workers")
