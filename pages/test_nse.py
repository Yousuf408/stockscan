import streamlit as st
import requests
import json

st.title("NSE Connection Test")

if st.button("Test NSE — RELIANCE"):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.nseindia.com",
            "Connection": "keep-alive",
        }

        session = requests.Session()

        # Step 1 — hit homepage to get cookies
        r1 = session.get("https://www.nseindia.com", headers=headers, timeout=10)
        st.write(f"Homepage status: {r1.status_code}")

        # Step 2 — fetch stock data
        r2 = session.get(
            "https://www.nseindia.com/api/quote-equity?symbol=RELIANCE",
            headers=headers,
            timeout=10
        )
        st.write(f"Stock API status: {r2.status_code}")
        st.write(f"Response: {r2.text[:500]}")

        if r2.status_code == 200:
            data = r2.json()
            ltp = data.get("priceInfo", {}).get("lastPrice")
            st.success(f"✅ NSE WORKS! RELIANCE LTP = ₹{ltp}")
        else:
            st.error(f"❌ NSE blocked — status {r2.status_code}")

    except Exception as e:
        st.error(f"❌ Error: {e}")
