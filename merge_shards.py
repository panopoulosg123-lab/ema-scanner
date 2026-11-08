"""Combine all available shard results and preserve previous valid data."""
import glob
import json
from datetime import datetime, timezone
from pathlib import Path

parts = [json.loads(Path(path).read_text(encoding="utf-8")) for path in glob.glob("shards/shard-*.json")]
if not parts:
    raise SystemExit("No worker results; preserving previous snapshot")
target = Path("data/latest.json")
old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
now = datetime.now(timezone.utc)
merged = {}
for row in old.get("rows", []):
    try:
        if (now-datetime.fromisoformat(row["ScannedAt"].replace("Z","+00:00"))).total_seconds() <= 48*3600:
            merged[row["Ticker"]] = row
    except (ValueError, TypeError, KeyError):
        pass
new = 0
for part in parts:
    for row in part["rows"]:
        merged[row["Ticker"]] = row
        new += 1
if not new:
    raise SystemExit("No successful data downloads; preserving previous snapshot")
expected = 18
result = {"updated_at":now.isoformat(),"total":max(p["total"] for p in parts),"successful":len(merged),
          "batch_successful":new,"batch_total":sum(p["batch_total"] for p in parts),
          "workers_completed":len(parts),"workers_expected":expected,
          "rows":sorted(merged.values(),key=lambda r:r["Distance"]),
          "errors":[e for p in parts for e in p["errors"]]}
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding="utf-8")
print(f"Merged {len(parts)}/{expected} workers, {new} successful asset scans")
