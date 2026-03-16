import time
import requests
from datetime import datetime, timedelta
import pandas as pd
import pandas_ta as ta
from dhanhq import dhanhq
import warnings
warnings.filterwarnings('ignore')

# ==========================================
# 1. API & TELEGRAM CREDENTIALS
# ==========================================
client_id = "1104670793"       
access_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzczNzI2Njk4LCJpYXQiOjE3NzM2NDAyOTgsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA0NjcwNzkzIn0.A8HYN4xm_0Zov7yixpc8VQo7BORcWDeY82EZ7pPF8dXXr_-7TXNRwZCZN4IN5sdf48IMnpNTwp6Z_CKUskdUiA"        
TELEGRAM_TOKEN = "8527939153:AAG6wM9V_lFlK5TIQKK3TPPYQh4HiBQN3a4"  
TELEGRAM_CHAT_ID = "556028149"       

dhan = dhanhq(client_id, access_token)

# ==========================================
# 2. STRATEGY SETTINGS
# ==========================================
TARGET_POINTS = 170
STOP_LOSS_POINTS = 90
EMA_LENGTH = 9
LOT_SIZE = 25 # Nifty 1 Lot

# --- TRADE TRACKING VARIABLES ---
is_trade_active = False
entry_price = 0
trade_type = "" # "BUY" ya "SELL"
target_price = 0
sl_price = 0

CANDLE_CLOSE_TIMES = ["10:00", "10:45", "11:30", "12:15", "13:00", "13:45", "14:30", "15:15"]
ALERT_TIMES = ["09:58", "10:43", "11:28", "12:13", "12:58", "13:43", "14:28", "15:13"]

# ==========================================
# 3. HELPER FUNCTIONS (Telegram & Data)
# ==========================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except: pass

def get_real_future_id():
    url = "https://images.dhan.co/api-data/api-scrip-master.csv"
    try:
        df = pd.read_csv(url, low_memory=False)
        df['SEM_TRADING_SYMBOL'] = df['SEM_TRADING_SYMBOL'].astype(str).str.strip().str.upper()
        df['SEM_INSTRUMENT_NAME'] = df['SEM_INSTRUMENT_NAME'].astype(str).str.strip().str.upper()
        nifty_futs = df[(df['SEM_TRADING_SYMBOL'].str.startswith('NIFTY')) & (df['SEM_INSTRUMENT_NAME'] == 'FUTIDX')].copy()
        nifty_futs['SEM_EXPIRY_DATE'] = pd.to_datetime(nifty_futs['SEM_EXPIRY_DATE'])
        current_fut = nifty_futs.sort_values('SEM_EXPIRY_DATE').iloc[0]
        return str(current_fut['SEM_SMST_SECURITY_ID'])
    except: return "13"

def get_nifty_data(security_id):
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    try:
        req = dhan.intraday_minute_data(security_id=security_id, exchange_segment=dhan.NSE_FNO, instrument_type='FUTIDX', from_date=from_date, to_date=to_date)
        if req and req.get('status') == 'success' and req.get('data'):
            data = req['data']
            timestamps = data.get('timestamp', data.get('start_Time'))
            time_index = pd.to_datetime(timestamps, unit='s', utc=True).tz_convert('Asia/Kolkata').tz_localize(None)
            df = pd.DataFrame({'Time': time_index, 'Open': data['open'], 'High': data['high'], 'Low': data['low'], 'Close': data['close']})
            df.set_index('Time', inplace=True)
            live_price = df['Close'].iloc[-1]
            df_45m = df.resample('45min', offset='15min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
            df_45m['EMA_High'] = ta.ema(df_45m['High'], length=EMA_LENGTH)
            df_45m['EMA_Low'] = ta.ema(df_45m['Low'], length=EMA_LENGTH)
            return round(live_price, 2), round(df_45m['EMA_High'].iloc[-2], 2), round(df_45m['EMA_Low'].iloc[-2], 2), round(df_45m['Close'].iloc[-2], 2)
    except: pass
    return None, None, None, None

# ==========================================
# 4. PnL & EXIT MONITORING
# ==========================================
def monitor_pnl(current_price):
    global is_trade_active, entry_price, trade_type, target_price, sl_price
    
    # Calculate PnL in Points and Rupees
    if trade_type == "BUY":
        pnl_points = current_price - entry_price
    else:
        pnl_points = entry_price - current_price
        
    pnl_rupees = pnl_points * LOT_SIZE
    print(f"---> [ACTIVE TRADE] {trade_type} | PnL Points: {pnl_points:.2f} | PnL Cash: ₹{pnl_rupees:.2f}")

    # Check for Exit Conditions
    hit_target = (trade_type == "BUY" and current_price >= target_price) or (trade_type == "SELL" and current_price <= target_price)
    hit_sl = (trade_type == "BUY" and current_price <= sl_price) or (trade_type == "SELL" and current_price >= sl_price)

    if hit_target or hit_sl:
        reason = "🎯 TARGET HIT" if hit_target else "🛑 STOP LOSS HIT"
        msg = f"🔔 *TRADE EXIT: {reason}*\n\nPrice: {current_price}\nTotal PnL: ₹{pnl_rupees:.2f}"
        print(msg)
        send_telegram(msg)
        # Reset for next trade
        is_trade_active = False

# ==========================================
# 5. MAIN ENGINE
# ==========================================
def run_strategy(future_id):
    global is_trade_active, entry_price, trade_type, target_price, sl_price
    now = datetime.now().strftime("%H:%M") 
    live_price, ema_high, ema_low, last_45_close = get_nifty_data(future_id)
    
    if live_price is None: return

    # --- 1. Agar trade active hai, toh PnL monitor karo ---
    if is_trade_active:
        print(f"[{now}] LIVE: {live_price} (Watching Target/SL...)")
        monitor_pnl(live_price)
    else:
        # --- 2. Agar trade active nahi hai, toh Entry dhundho ---
        print(f"[{now}] LIVE: Nifty = {live_price} | EMA High = {ema_high} | EMA Low = {ema_low}")

        if now in ALERT_TIMES:
            msg = ""
            if live_price > ema_high: msg = f"⚠️ *BUY ALERT*\nNifty EMA High ke upar hai."
            elif live_price < ema_low: msg = f"⚠️ *SELL ALERT*\nNifty EMA Low ke niche hai."
            if msg: send_telegram(msg)
            
        elif now in CANDLE_CLOSE_TIMES:
            if last_45_close > ema_high:
                is_trade_active = True
                trade_type = "BUY"
                entry_price = live_price
                target_price = entry_price + TARGET_POINTS
                sl_price = entry_price - STOP_LOSS_POINTS
                send_telegram(f"🚀 *ENTRY BUY*\nPrice: {entry_price}\nTgt: {target_price}\nSL: {sl_price}")
            
            elif last_45_close < ema_low:
                is_trade_active = True
                trade_type = "SELL"
                entry_price = live_price
                target_price = entry_price - TARGET_POINTS
                sl_price = entry_price + STOP_LOSS_POINTS
                send_telegram(f"📉 *ENTRY SELL*\nPrice: {entry_price}\nTgt: {target_price}\nSL: {sl_price}")

if __name__ == "__main__":
    print("Auto-Trader Bot with PnL Tracking started...")
    REAL_FUTURE_ID = get_real_future_id()
    while True:
        curr_t = datetime.now().time()
        if datetime.strptime("09:15","%H:%M").time() <= curr_t <= datetime.strptime("15:30","%H:%M").time():
            run_strategy(REAL_FUTURE_ID)
        time.sleep(60)