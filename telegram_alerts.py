"""Send one compact Telegram digest per scan, not one message per asset."""
import json
import os
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
    try:
        scanned_at = datetime.fromisoformat(row["ScannedAt"].replace("Z", "+00:00"))
        if (now - scanned_at).total_seconds() > 3 * 3600:
            continue
    except (KeyError, ValueError, TypeError):
        continue
    for timeframe, prefix in (("1D", ""), ("1W", "Weekly")):
        cross = row.get(prefix + "Cross")
        if cross not in ("Bullish crossover", "Bearish crossover"):
            continue
        date = str(row.get(prefix + "Date", ""))
        try:
            if (now.date() - datetime.fromisoformat(date).date()).days > (4 if timeframe == "1D" else 10):
                continue
        except ValueError:
            continue
        key = f"{row['Ticker']}|{timeframe}|{date}|{cross}"
        if key not in sent:
            candidates.append((key, row, timeframe, cross, date))

print(f"New EMA crossover alerts: {len(candidates)}")
if candidates:
    bullish = sorted((c for c in candidates if c[3] == "Bullish crossover"), key=lambda c: (c[2], c[1]["Ticker"]))
    bearish = sorted((c for c in candidates if c[3] == "Bearish crossover"), key=lambda c: (c[2], c[1]["Ticker"]))
    lines = [
        "📊 EMA 8/21 — Νέες διασταυρώσεις 1D / 1W",
        f"🟢 LONG: {len(bullish)} | 🔴 SHORT: {len(bearish)}",
        "",
    ]
    # Telegram sendMessage supports at most 4096 characters.
    # Keep one message per scan, with a total count when the list is long.
    shown = 0
    for heading, rows in (("🟢 LONG", bullish), ("🔴 SHORT", bearish)):
        if not rows:
            continue
        if len("\n".join(lines + [heading])) > 3650:
            break
        lines.append(heading)
        for _, row, timeframe, _, date in rows:
            entry = f"• [{timeframe}] {row['Ticker']} — {row['Name']} ({date})"
            if len("\n".join(lines + [entry])) > 3650:
                break
            lines.append(entry)
            shown += 1
        lines.append("")
    if shown < len(candidates):
        lines.append(f"…και {len(candidates) - shown} ακόμη διασταυρώσεις.")
    lines.append("Δεν αποτελεί επενδυτική σύσταση.")
    message = "\n".join(lines)
    payload = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise ValueError("Telegram rejected digest")
    except Exception:
        print("Telegram digest delivery failed (details hidden)")
        raise SystemExit("Telegram notification failed; alerts remain eligible for retry")
    for key, row, timeframe, cross, date in candidates:
        sent[key] = date
    print(f"Telegram: sent one digest for {len(candidates)} new crossovers")
else:
    print("Telegram: no new crossovers; no message sent")

state_path.parent.mkdir(exist_ok=True)
state_path.write_text(json.dumps({"sent": sent}, ensure_ascii=False, indent=2), encoding="utf-8")
