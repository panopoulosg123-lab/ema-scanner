# EMA 8/21 Scanner

Streamlit web scanner for selected US and Greek stocks, crypto, and commodity futures.

## Deploy
1. Open https://share.streamlit.io/ and sign in with GitHub.
2. Create app from repository `panopoulosg123-lab/ema-scanner`, branch `main`, entrypoint `app.py`.
3. Click Deploy.

Uses daily Yahoo Finance data via yfinance; feeds may be delayed, incomplete or rate limited. Displays EMA 8/21 distance, crossovers, and near-threshold status after manual scanning. No push notifications or background monitoring. Not investment advice.
