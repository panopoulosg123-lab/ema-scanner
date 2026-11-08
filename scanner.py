"""Hourly EMA scanner; writes data/latest.json for the Streamlit dashboard."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

UNIVERSES = {
 "US Stocks": {"Apple":"AAPL","Microsoft":"MSFT","Nvidia":"NVDA","Amazon":"AMZN","Alphabet":"GOOGL","Tesla":"TSLA","Meta":"META","AMD":"AMD","Netflix":"NFLX","Palantir":"PLTR","SPY ETF":"SPY","QQQ ETF":"QQQ","Broadcom":"AVGO","Costco":"COST","Walmart":"WMT","JPMorgan":"JPM","Visa":"V","Mastercard":"MA","Berkshire":"BRK-B","Exxon":"XOM","Chevron":"CVX","Coca-Cola":"KO","Pepsi":"PEP","Intel":"INTC","Qualcomm":"QCOM","Salesforce":"CRM","Oracle":"ORCL","Uber":"UBER","Disney":"DIS","Boeing":"BA","Caterpillar":"CAT","Goldman Sachs":"GS","Morgan Stanley":"MS","Bank of America":"BAC","Pfizer":"PFE","Eli Lilly":"LLY","Johnson & Johnson":"JNJ","Procter & Gamble":"PG","Home Depot":"HD","McDonald's":"MCD","Nike":"NKE","IBM":"IBM","Cisco":"CSCO","Adobe":"ADBE","Shopify":"SHOP","Coinbase":"COIN","Robinhood":"HOOD","Micron":"MU","Applied Materials":"AMAT","Texas Instruments":"TXN"},
 "Greek Stocks": {"Alpha Bank":"ALPHA.AT","Eurobank":"EUROB.AT","National Bank":"ETE.AT","Piraeus":"TPEIR.AT","OPAP":"OPAP.AT","OTE":"HTO.AT","Metlen":"METLEN.AT","Jumbo":"BELA.AT","PPC":"PPC.AT","Motor Oil":"MOH.AT","Hellenic Energy":"ELPE.AT","GEK Terna":"GEKTERNA.AT","Terna Energy":"TENERGY.AT","Aegean":"AEGN.AT","Titan":"TITC.AT","Viohalco":"VIO.AT","Cenergy":"CENER.AT","Lamda":"LAMDA.AT","Autohellas":"OTOEL.AT"},
 "Crypto": {"Bitcoin":"BTC-USD","Ethereum":"ETH-USD","Solana":"SOL-USD","XRP":"XRP-USD","Cardano":"ADA-USD","Dogecoin":"DOGE-USD","Avalanche":"AVAX-USD","Chainlink":"LINK-USD","Polkadot":"DOT-USD","Litecoin":"LTC-USD","Bitcoin Cash":"BCH-USD","Stellar":"XLM-USD","Uniswap":"UNI-USD","Aave":"AAVE-USD"},
 "Commodities": {"Gold":"GC=F","Silver":"SI=F","Copper":"HG=F","Platinum":"PL=F","Palladium":"PA=F","WTI Oil":"CL=F","Brent Oil":"BZ=F","Natural Gas":"NG=F","Corn":"ZC=F","Wheat":"ZW=F","Soybeans":"ZS=F","Coffee":"KC=F","Sugar":"SB=F","Cocoa":"CC=F","Cotton":"CT=F","Oats":"ZO=F","Soybean Oil":"ZL=F","Soybean Meal":"ZM=F","Live Cattle":"LE=F","Lean Hogs":"HE=F"}
}

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

def scan():
    items = [(market,name,ticker) for market,names in UNIVERSES.items() for name,ticker in names.items()]
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(fetch_one, items):
            row, error = result
            if row:
                rows.append(row)
            if error:
                errors.append(error)
    rows.sort(key=lambda x: x["Distance"])
    return {"updated_at":datetime.now(timezone.utc).isoformat(),"total":len(items),"successful":len(rows),"rows":rows,"errors":errors}

if __name__ == "__main__":
    result = scan()
    target = Path(__file__).parent / "data" / "latest.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    if result["successful"] == 0:
        raise SystemExit("No data downloaded; preserve previous snapshot")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(f"Updated {result['successful']}/{result['total']} assets")
