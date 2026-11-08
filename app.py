import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
from scanner import UNIVERSES, scan

st.set_page_config(page_title="EMA 8/21 Scanner", layout="wide")
st.title("EMA 8/21 Scanner")
st.caption("Daily · EMA 8/21 · hourly cloud snapshots · Yahoo Finance data may be delayed")
SNAPSHOT_URL = "https://raw.githubusercontent.com/panopoulosg123-lab/ema-scanner/main/data/latest.json"

@st.cache_data(ttl=120, show_spinner=False)
def load_snapshot():
    try:
        response = requests.get(SNAPSHOT_URL, timeout=12, headers={"Cache-Control":"no-cache"})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data.get("rows"),list):
            raise ValueError("Invalid snapshot")
        return data
    except Exception:
        local = Path(__file__).parent / "data" / "latest.json"
        if local.exists():
            return json.loads(local.read_text(encoding="utf-8"))
        return None

categories = st.multiselect("Αγορές", list(UNIVERSES), default=list(UNIVERSES))
limit = st.number_input("Μέγιστη απόσταση (%)", min_value=0.0, max_value=10.0, value=0.10, step=0.01, format="%.2f")
warning = st.number_input("Όριο προειδοποίησης (%)", min_value=0.0, max_value=10.0, value=0.15, step=0.01, format="%.2f")
direction = st.selectbox("Κατεύθυνση", ["ALL","LONG","SHORT"])
show_all = st.checkbox("Εμφάνιση και assets εκτός ορίου", value=True)
force = st.button("Νέα σάρωση τώρα", type="primary")
refresh = st.button("Ανανέωση αποθηκευμένων αποτελεσμάτων")

if refresh:
    load_snapshot.clear()
if force:
    with st.spinner("Εκτελείται νέα σάρωση στον server…"):
        data = scan()
    if not data["rows"]:
        st.error("Η ζωντανή σάρωση απέτυχε. Δοκίμασε τα αποθηκευμένα αποτελέσματα.")
        data = load_snapshot()
    else:
        st.success("Η νέα σάρωση ολοκληρώθηκε. Τα αποτελέσματα αυτής της σάρωσης δεν αποθηκεύονται στο GitHub.")
else:
    data = load_snapshot()

if data is None:
    st.warning("Δεν υπάρχει ακόμη αποθηκευμένη σάρωση. Η πρώτη εκτέλεση του GitHub Actions μπορεί να γίνει χειροκίνητα από την καρτέλα Actions. Μπορείς επίσης να πατήσεις «Νέα σάρωση τώρα».")
else:
    stamp = datetime.fromisoformat(data["updated_at"].replace("Z","+00:00"))
    age = (datetime.now(timezone.utc)-stamp).total_seconds()/3600
    st.caption(f"Τελευταία σάρωση: {stamp.strftime('%Y-%m-%d %H:%M UTC')} · {data['successful']}/{data['total']} assets · {age:.1f} ώρες πριν")
    if age > 2:
        st.warning("Τα αποθηκευμένα δεδομένα είναι παλαιότερα από 2 ώρες. Έλεγξε την καρτέλα GitHub Actions ή πάτησε «Νέα σάρωση τώρα».")
    if data.get("errors"):
        st.info(f"Αδυναμία λήψης για {len(data['errors'])} assets. Δεν εμφανίζονται ως μηδενικά σήματα.")
    if data["rows"]:
        df = pd.DataFrame(data["rows"])
        df = df[df.Market.isin(categories)]
        if direction != "ALL":
            df = df[df.Direction == direction]
        df = df.sort_values("Distance")
        df["Status"] = df.Distance.apply(lambda d: "MATCH" if d <= limit else "NEAR" if d <= warning else "OUT")
        c1,c2,c3 = st.columns(3)
        c1.metric("Εντός ορίου",int((df.Status=="MATCH").sum()))
        c2.metric("Πλησιάζουν",int((df.Status=="NEAR").sum()))
        c3.metric("Συνολικά διαθέσιμα",len(df))
        visible = df if show_all else df[df.Status!="OUT"]
        st.dataframe(visible,hide_index=True,use_container_width=True,column_config={"Distance":st.column_config.NumberColumn("EMA distance %",format="%.4f"),"EMA8":st.column_config.NumberColumn(format="%.4f"),"EMA21":st.column_config.NumberColumn(format="%.4f"),"Price":st.column_config.NumberColumn(format="%.4f")})
        st.download_button("Λήψη CSV",df.to_csv(index=False).encode("utf-8-sig"),"ema_scan.csv","text/csv")
        st.info("Οι ενδείξεις MATCH/NEAR εμφανίζονται στην εφαρμογή, δεν αποστέλλονται ως push/email. LONG/SHORT είναι μόνο η σχετική θέση των EMA, όχι επενδυτική σύσταση.")
