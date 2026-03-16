import streamlit as st
import pandas as pd
import pandas_ta as ta
from dhanhq import dhanhq
from datetime import datetime, timedelta
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Bhamu Algo-Trader", layout="wide")
client_id = "1104670793"
access_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzczNzI2Njk4LCJpYXQiOjE3NzM2NDAyOTgsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA0NjcwNzkzIn0.A8HYN4xm_0Zov7yixpc8VQo7BORcWDeY82EZ7pPF8dXXr_-7TXNRwZCZN4IN5sdf48IMnpNTwp6Z_CKUskdUiA"
dhan = dhanhq(client_id, access_token)

# --- SESSION STATE (Memory for Trade) ---
if 'trade' not in st.session_state:
    st.session_state.trade = {"active": False, "type": "", "entry": 0, "tgt": 0, "sl": 0, "time": ""}

# --- FUNCTIONS ---
def get_data():
    # Nifty Future ID (Using fixed for demo, can use auto-fetch function here)
    sec_id = "51714" 
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        req = dhan.intraday_minute_data(sec_id, "NSE_FNO", "FUTIDX", from_date, to_date)
        df = pd.DataFrame(req['data'])
        df['Time'] = pd.to_datetime(df['timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
        df.set_index('Time', inplace=True)
        # EMA Calculations
        df['EMA_H'] = ta.ema(df['high'], length=9)
        df['EMA_L'] = ta.ema(df['low'], length=9)
        return df
    except: return None

# --- UI LAYOUT ---
st.title("🚀 Bhamu Algo-Trader Dashboard")
placeholder = st.empty()

while True:
    df = get_data()
    if df is not None:
        live_p = df['close'].iloc[-1]
        ema_h = round(df['EMA_H'].iloc[-1], 2)
        ema_l = round(df['EMA_L'].iloc[-1], 2)
        
        with placeholder.container():
            # 1. METRICS ROW
            col1, col2, col3 = st.columns(3)
            col1.metric("Nifty Live Price", f"₹{live_p}", delta=round(live_p - df['close'].iloc[-2], 2))
            col2.metric("9 EMA High", f"{ema_h}")
            col3.metric("9 EMA Low", f"{ema_l}")

            st.divider()

            # 2. TRADE STATUS & PnL
            if not st.session_state.trade["active"]:
                st.info("ℹ️ **Status:** No Open Trade. Waiting for 45-min candle crossover.")
            else:
                t = st.session_state.trade
                pnl = (live_p - t['entry']) * 25 if t['type'] == "BUY" else (t['entry'] - live_p) * 25
                color = "green" if pnl >= 0 else "red"
                
                st.subheader(f"🔔 Active Position: {t['type']}")
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"**Entry:** {t['entry']}")
                c2.write(f"**Target:** {t['tgt']}")
                c3.write(f"**SL:** {t['sl']}")
                c4.markdown(f"**Live PnL:** <h2 style='color:{color};'>₹{pnl:.2f}</h2>", unsafe_allow_html=True)

            # 3. RECENT DATA (Last 5 Mins)
            st.subheader("📊 Recent 5-Min Price Action")
            st.table(df[['close', 'high', 'low']].tail(5))

    time.sleep(10) # Har 10 sec mein refresh hoga
    st.rerun()
