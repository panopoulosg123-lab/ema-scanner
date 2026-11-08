import streamlit as st
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="EMA 8/21 Scanner", layout="wide")
st.title("EMA 8/21 Scanner")
st.caption("Daily · Yahoo Finance data (may be delayed)")

UNIVERSES = {
    "US Stocks": {"Apple":"AAPL","Microsoft":"MSFT","Nvidia":"NVDA","Amazon":"AMZN","Alphabet":"GOOGL","Tesla":"TSLA","Meta":"META","AMD":"AMD","Netflix":"NFLX","Palantir":"PLTR","SPY ETF":"SPY","QQQ ETF":"QQQ"},
    "Greek Stocks": {"Alpha Bank":"ALPHA.AT","Eurobank":"EUROB.AT","National Bank":"ETE.AT","Piraeus":"TPEIR.AT","OPAP":"OPAP.AT","OTE":"HTO.AT","Metlen":"METLEN.AT","Jumbo":"BELA.AT"},
    "Crypto": {"Bitcoin":"BTC-USD","Ethereum":"ETH-USD","Solana":"SOL-USD","XRP":"XRP-USD","Cardano":"ADA-USD","Dogecoin":"DOGE-USD"},
    "Commodities": {"Gold":"GC=F","Silver":"SI=F","Copper":"HG=F","Platinum":"PL=F","Palladium":"PA=F","WTI Oil":"CL=F","Brent Oil":"BZ=F","Natural Gas":"NG=F","Corn":"ZC=F","Wheat":"ZW=F","Soybeans":"ZS=F","Coffee":"KC=F","Sugar":"SB=F","Cocoa":"CC=F","Cotton":"CT=F"}
}

@st.cache_data(ttl=900, show_spinner=False)
def fetch(ticker):
    frame = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False)
    if frame.empty:
        return None
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if len(close) < 50:
        return None
    e8 = close.ewm(span=8, adjust=False).mean()
    e21 = close.ewm(span=21, adjust=False).mean()
    if e21.iloc[-1] == 0:
        return None
    distance = abs(e8.iloc[-1] - e21.iloc[-1]) / abs(e21.iloc[-1]) * 100
    previous = e8.iloc[-2] - e21.iloc[-2]
    current = e8.iloc[-1] - e21.iloc[-1]
    cross = "Bullish crossover" if previous <= 0 < current else "Bearish crossover" if previous >= 0 > current else "—"
    return {"Price":float(close.iloc[-1]),"EMA8":float(e8.iloc[-1]),"EMA21":float(e21.iloc[-1]),"Distance":float(distance),"Direction":"LONG" if current>0 else "SHORT" if current<0 else "NEUTRAL","Cross":cross,"Date":str(close.index[-1].date())}

categories = st.multiselect("Αγορές", list(UNIVERSES), default=list(UNIVERSES))
limit = st.number_input("Μέγιστη απόσταση (%)", min_value=0.0, max_value=10.0, value=0.10, step=0.01, format="%.2f")
warning = st.number_input("Όριο προειδοποίησης (%)", min_value=0.0, max_value=10.0, value=0.15, step=0.01, format="%.2f")
show_all = st.checkbox("Εμφάνιση και assets εκτός ορίου", value=True)

if st.button("Σάρωση τώρα", type="primary"):
    items = [(category,name,ticker) for category in categories for name,ticker in UNIVERSES[category].items()]
    rows, errors = [], []
    with st.spinner("Λήψη ημερήσιων δεδομένων…"):
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(fetch,ticker):(category,name,ticker) for category,name,ticker in items}
            for future in as_completed(futures):
                category,name,ticker = futures[future]
                try:
                    data = future.result()
                    if data:
                        rows.append({"Market":category,"Name":name,"Ticker":ticker,**data})
                    else:
                        errors.append(ticker)
                except Exception:
                    errors.append(ticker)
    if rows:
        df = pd.DataFrame(rows).sort_values("Distance")
        df["Status"] = df.Distance.apply(lambda d: "MATCH" if d <= limit else "NEAR" if d <= warning else "OUT")
        st.metric("Εντός ορίου", int((df.Status=="MATCH").sum()))
        st.metric("Πλησιάζουν", int((df.Status=="NEAR").sum()))
        visible = df if show_all else df[df.Status!="OUT"]
        st.caption(f"Επιτυχής λήψη: {len(df)} από {len(items)} assets · Ελάχιστη απόσταση: {df.Distance.min():.4f}%")
        st.dataframe(visible, hide_index=True, use_container_width=True, column_config={"Distance":st.column_config.NumberColumn("EMA distance %",format="%.4f"),"Price":st.column_config.NumberColumn(format="%.4f"),"EMA8":st.column_config.NumberColumn(format="%.4f"),"EMA21":st.column_config.NumberColumn(format="%.4f")})
        st.download_button("Λήψη CSV", df.to_csv(index=False).encode("utf-8-sig"), "ema_scan.csv", "text/csv")
        st.info("LONG/SHORT only indicates relative EMA position, not a trading recommendation. Alerts appear only when you run a scan; no background notifications.")
    else:
        st.warning("Δεν βρέθηκαν διαθέσιμα δεδομένα.")
    if errors:
        st.warning("Αδυναμία λήψης: "+", ".join(errors))
