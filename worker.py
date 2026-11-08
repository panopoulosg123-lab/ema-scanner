"""One independent GitHub Actions runner scans a deterministic slice."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from scanner import expanded_universe, fetch_one

index = int(os.environ["SHARD_INDEX"])
count = int(os.environ.get("SHARD_COUNT","8"))
limit = int(os.environ.get("SCAN_TARGET","2000"))
assert 0 <= index < count
items = expanded_universe()[:limit]
batch = items[index::count]
rows, errors = [], []
with ThreadPoolExecutor(max_workers=4) as pool:
    for row, error in pool.map(fetch_one, batch):
        if row:
            row["ScannedAt"] = datetime.now(timezone.utc).isoformat()
            rows.append(row)
        if error:
            errors.append(error)
out = Path("shards") / f"shard-{index}.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"index":index,"count":count,"total":len(items),"batch_total":len(batch),"rows":rows,"errors":errors},ensure_ascii=False,allow_nan=False),encoding="utf-8")
print(f"Shard {index}: {len(rows)}/{len(batch)} succeeded")
