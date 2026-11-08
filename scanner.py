"""Hourly EMA scanner; writes data/latest.json for the Streamlit dashboard."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
import requests
from io import StringIO

UNIVERSES = {
 "US Stocks": {"Apple":"AAPL","Microsoft":"MSFT","Nvidia":"NVDA","Amazon":"AMZN","Alphabet":"GOOGL","Tesla":"TSLA","Meta":"META","AMD":"AMD","Netflix":"NFLX","Palantir":"PLTR","SPY ETF":"SPY","QQQ ETF":"QQQ","Broadcom":"AVGO","Costco":"COST","Walmart":"WMT","JPMorgan":"JPM","Visa":"V","Mastercard":"MA","Berkshire":"BRK-B","Exxon":"XOM","Chevron":"CVX","Coca-Cola":"KO","Pepsi":"PEP","Intel":"INTC","Qualcomm":"QCOM","Salesforce":"CRM","Oracle":"ORCL","Uber":"UBER","Disney":"DIS","Boeing":"BA","Caterpillar":"CAT","Goldman Sachs":"GS","Morgan Stanley":"MS","Bank of America":"BAC","Pfizer":"PFE","Eli Lilly":"LLY","Johnson & Johnson":"JNJ","Procter & Gamble":"PG","Home Depot":"HD","McDonald's":"MCD","Nike":"NKE","IBM":"IBM","Cisco":"CSCO","Adobe":"ADBE","Shopify":"SHOP","Coinbase":"COIN","Robinhood":"HOOD","Micron":"MU","Applied Materials":"AMAT","Texas Instruments":"TXN"},
 "Greek Stocks": {"Alpha Bank":"ALPHA.AT","Eurobank":"EUROB.AT","National Bank":"ETE.AT","Piraeus":"TPEIR.AT","OPAP":"OPAP.AT","OTE":"HTO.AT","Metlen":"METLEN.AT","Jumbo":"BELA.AT","PPC":"PPC.AT","Motor Oil":"MOH.AT","Hellenic Energy":"ELPE.AT","GEK Terna":"GEKTERNA.AT","Terna Energy":"TENERGY.AT","Aegean":"AEGN.AT","Titan":"TITC.AT","Viohalco":"VIO.AT","Cenergy":"CENER.AT","Lamda":"LAMDA.AT","Autohellas":"OTOEL.AT"},
 "Crypto": {"Bitcoin":"BTC-USD","Ethereum":"ETH-USD","Solana":"SOL-USD","XRP":"XRP-USD","Cardano":"ADA-USD","Dogecoin":"DOGE-USD","Avalanche":"AVAX-USD","Chainlink":"LINK-USD","Polkadot":"DOT-USD","Litecoin":"LTC-USD","Bitcoin Cash":"BCH-USD","Stellar":"XLM-USD","Uniswap":"UNI-USD","Aave":"AAVE-USD"},
 "Commodities": {"Gold":"GC=F","Silver":"SI=F","Copper":"HG=F","Platinum":"PL=F","Palladium":"PA=F","WTI Oil":"CL=F","Brent Oil":"BZ=F","Natural Gas":"NG=F","Corn":"ZC=F","Wheat":"ZW=F","Soybeans":"ZS=F","Coffee":"KC=F","Sugar":"SB=F","Cocoa":"CC=F","Cotton":"CT=F","Oats":"ZO=F","Soybean Oil":"ZL=F","Soybean Meal":"ZM=F","Live Cattle":"LE=F","Lean Hogs":"HE=F"}
}

NASDAQ_URLS = [
 ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt", "Symbol", "Security Name", "Test Issue"),
 ("https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt", "ACT Symbol", "Security Name", "Test Issue"),
]

def expanded_universe():
    """Load US-listed securities from Nasdaq Trader's public symbol directories."""
    items = [(market, name, ticker) for market, names in UNIVERSES.items() for name, ticker in names.items()]
    seen = {ticker for _, _, ticker in items}
    for url, symbol_col, name_col, test_col in NASDAQ_URLS:
        try:
            response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 EMA research scanner"})
            response.raise_for_status()
            directory = pd.read_csv(StringIO(response.text), sep="|", dtype=str, on_bad_lines="skip").fillna("")
            for _, row in directory.iterrows():
                ticker = row.get(symbol_col, "").strip()
                name = row.get(name_col, "").strip()
                if not ticker or ticker.startswith("File Creation") or row.get(test_col, "") == "Y":
                    continue
                # Exclude warrants, units, preferred issues and other non-common securities.
                low = name.lower()
                if any(word in low for word in (" warrant", " warrants", " unit ", " units ", " preferred", " preference", " right ", " rights ", " notes due", " bond", " depositary")):
                    continue
                ticker = ticker.replace(".", "-").replace("$", "-")
                if not all(ch.isalnum() or ch == "-" for ch in ticker) or ticker in seen:
                    continue
                seen.add(ticker)
                market = "US ETFs" if "etf" in low or "exchange traded fund" in low else "US Stocks"
                items.append((market, name or ticker, ticker))
        except Exception as exc:
            print(f"Symbol directory unavailable: {url}: {exc}")
    # Stable ordering ensures cursor progress across hourly scans.
    return sorted(items, key=lambda item: (item[0], item[2]))

def fetch_one(item):
    market, name, ticker = item
    for attempt in range(2):
        try:
            frame = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False, timeout=15)
            if frame.empty:
                raise ValueError("empty")
            close = frame["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            if len(close) < 50:
                raise ValueError("insufficient history")
            e8 = close.ewm(span=8, adjust=False).mean()
            e21 = close.ewm(span=21, adjust=False).mean()
            a, b = float(e8.iloc[-1]), float(e21.iloc[-1])
            distance = abs(a-b)/abs(b)*100
            prior = float(e8.iloc[-2]-e21.iloc[-2])
            delta = a-b
            cross = "Bullish crossover" if prior <= 0 < delta else "Bearish crossover" if prior >= 0 > delta else "—"
            return {"Market":market,"Name":name,"Ticker":ticker,"Price":float(close.iloc[-1]),"EMA8":a,"EMA21":b,"Distance":distance,"Direction":"LONG" if delta>0 else "SHORT" if delta<0 else "NEUTRAL","Cross":cross,"Date":str(close.index[-1].date())}, None
        except Exception as exc:
            if attempt == 0:
                time.sleep(1)
            else:
                return None, f"{ticker}: {str(exc)[:120]}"

def scan(max_items=2000, previous=None):
    """Scan one rotating batch and preserve recent successful results."""
    items = expanded_universe()
    previous = previous or {}
    cursor = int(previous.get("next_cursor", 0)) % max(len(items), 1)
    batch = [items[(cursor + i) % len(items)] for i in range(min(max_items, len(items)))]
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for row, error in pool.map(fetch_one, batch):
            if row:
                row["ScannedAt"] = datetime.now(timezone.utc).isoformat()
                rows.append(row)
            if error:
                errors.append(error)
    now = datetime.now(timezone.utc)
    merged = {}
    for row in previous.get("rows", []):
        try:
            if (now - datetime.fromisoformat(row["ScannedAt"].replace("Z","+00:00"))).total_seconds() <= 48*3600:
                merged[row["Ticker"]] = row
        except (KeyError, ValueError, TypeError):
            pass
    for row in rows:
        merged[row["Ticker"]] = row
    return {"updated_at":now.isoformat(),"total":len(items),"successful":len(merged),
            "batch_successful":len(rows),"batch_total":len(batch),
            "next_cursor":(cursor+len(batch)) % max(len(items),1),
            "rows":sorted(merged.values(),key=lambda x:x["Distance"]),"errors":errors}

if __name__ == "__main__":
    target = Path(__file__).parent / "data" / "latest.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
    result = scan(previous=previous)
    if result["batch_successful"] == 0:
        raise SystemExit("No data downloaded this hour; preserve previous snapshot")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(f"Batch: {result['batch_successful']}/{result['batch_total']}; cached {result['successful']} of {result['total']} discovered")
