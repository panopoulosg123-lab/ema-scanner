"""Scan one slice of a shared asset manifest on an independent runner."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from scanner import fetch_one

index = int(os.environ["SHARD_INDEX"])
count = int(os.environ.get("SHARD_COUNT", "18"))
assert 0 <= index < count
items = json.loads(Path("manifest/assets.json").read_text(encoding="utf-8"))
batch = items[index::count]
rows, errors = [], []
with ThreadPoolExecutor(max_workers=2) as pool:
    for row, error in pool.map(fetch_one, batch):
        if row:
            row["ScannedAt"] = datetime.now(timezone.utc).isoformat()
            rows.append(row)
        if error:
            errors.append(error)
out = Path("shards") / f"shard-{index}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"index":index,"count":count,"total":len(items),"batch_total":len(batch),"rows":rows,"errors":errors},ensure_ascii=False,allow_nan=False),encoding="utf-8")
print(f"Worker {index}: {len(rows)}/{len(batch)} assets successful")
