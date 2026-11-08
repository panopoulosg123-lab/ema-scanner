"""Send one Telegram notification per asset/date/crossover after a completed scan.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub Actions secrets.
Only successfully delivered alerts are added to the deduplication state.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

snapshot = Path("data/latest.json")
state_path = Path("data/telegram_sent.json")
token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
if not token or not chat_id:
    print("Telegram not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets.")
    raise SystemExit(0)
if not snapshot.exists():
    raise SystemExit("No snapshot found")

data = json.loads(snapshot.read_text(encoding="utf-8"))
previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
sent = previous.get("sent", {})
cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).date().isoformat()
sent = {key: value for key, value in sent.items() if value >= cutoff}
now = datetime.now(timezone.utc)
candidates = []
for row in data.get("rows", []):
    cross = row.get("Cross")
    if cross not in ("Bullish crossover", "Bearish crossover"):
        continue
    date = str(row.get("Date", ""))
    ticker = str(row.get("Ticker", ""))
    try:
        scanned_at = datetime.fromisoformat(row["ScannedAt"].replace("Z", "+00:00"))
        if (now - scanned_at).total_seconds() > 3 * 3600:
            continue
        # Prevent a backlog of historical alerts when first enabled.
        if (now.date() - datetime.fromisoformat(date).date()).days > 4:
            continue
    except (KeyError, ValueError, TypeError):
        continue
    key = f"{ticker}|{date}|{cross}"
    if key not in sent:
        candidates.append((key, row))
print(f"New EMA crossover alerts: {len(candidates)}")
failures = 0
for key, row in candidates:
    direction = "🟢 LONG / ανοδική" if row["Cross"] == "Bullish crossover" else "🔴 SHORT / καθοδική"
    message = (f"📊 EMA 8/21 CROSSOVER\n"
               f"{direction}\n"
               f"Asset: {row['Name']} ({row['Ticker']})\n"
               f"Αγορά: {row['Market']}\n"
               f"Ημερομηνία ημερήσιου κεριού: {row['Date']}\n"
               f"EMA8: {row['EMA8']:.4f} | EMA21: {row['EMA21']:.4f}\n"
               f"Απόσταση: {row['Distance']:.4f}%\n"
               f"Ενημέρωση: όχι επενδυτική σύσταση.")
    payload = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise ValueError("Telegram rejected message")
        sent[key] = row["Date"]
        time.sleep(0.15)
    except Exception:
        failures += 1
        print(f"Telegram delivery failed for {row['Ticker']} (details hidden)")
state_path.parent.mkdir(exist_ok=True)
state_path.write_text(json.dumps({"sent": sent}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Telegram: delivered {len(candidates)-failures}, failed {failures}")
if failures:
    raise SystemExit("Some Telegram messages failed; successful sends were recorded locally")
