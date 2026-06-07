import os
import json
import time
import requests
import pandas as pd
import yfinance as yf
import websocket  # Synchronous client bypassing the GitHub event loop bug
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURATION & ALL 31 TARGET ASSETS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STANDARD_PAIRS = [
    # Forex Majors
    'EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'USDCHF=X', 'USDCAD=X', 'NZDUSD=X',
    # Global Indices (SPX, Nth, Jp225, Uk100, Nasdaq, GER, FRA)
    '^GSPC', '^AEX', '^N225', '^FTSE', '^IXIC', '^GDAXI', '^FCHI'
]

DERIV_PAIRS = [
    # Standard Volatility Indices
    'R_10', 'R_25', 'R_50', 'R_75', 'R_90', 'R_100',
    # 1s Volatility Indices
    '1HZ10V', '1HZ25V', '1HZ50V', '1HZ75V', '1HZ90V', '1HZ100V',
    # Jump Indices
    'JD10', 'JD25',
    # Boom Indices
    'BOOM300', 'BOOM900', 'BOOM1000',
    # Step Indices
    'STP', 'STP200', 'STP300', 'STP400', 'STP500'
]

def send_telegram_alert(message):
    token = str(TELEGRAM_BOT_TOKEN).strip()
    if token.lower().startswith("bot"):
        token = token[3:]  # Safely strip prefix without altering the inner hash
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": str(TELEGRAM_CHAT_ID).strip(), "text": message, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"Telegram Error Output: {res.text}")
    except Exception as e:
        print(f"Telegram dispatch failure: {e}")

# ==========================================
# 2. TIME ENGINE & QUARTERLY THEORY (LAGOS)
# ==========================================
def get_market_context():
    lagos_now = datetime.utcnow() + timedelta(hours=1)
    timestamp_str = lagos_now.strftime("%Y-%m-%d %H:%M")
    is_weekend = lagos_now.weekday() >= 5 

    time_float = lagos_now.hour + (lagos_now.minute / 60.0)
    
    is_london_q2 = (10.5 <= time_float < 12.0)  
    is_london_q3 = (12.0 <= time_float < 13.5)  
    is_ny_q2     = (15.5 <= time_float < 17.0)  
    is_ny_q3     = (17.0 <= time_float < 18.5)  

    if is_london_q2 or is_ny_q2:
        qt_status = "⚠️ Q2 MANIPULATION PHASE"
    elif is_london_q3 or is_ny_q3:
        qt_status = "🔥 Q3 DISTRIBUTION PHASE"
    else:
        qt_status = "🔄 Regular Session"

    return timestamp_str, is_weekend, qt_status

# ==========================================
# 3. FIXED SYNCHRONOUS DATA FETCHING
# ==========================================
def fetch_deriv_candles_sync(symbol, granularity, count=150):
    uri = "wss://ws.derivws.com/websockets/v3?app_id=1089"
    try:
        ws = websocket.create_connection(uri, timeout=10)
        request = {
            "ticks_history": symbol, "adjust_start_time": 1,
            "count": count, "end": "latest",
            "granularity": granularity, "style": "candles"
        }
        ws.send(json.dumps(request))
        response = ws.recv()
        ws.close()
        
        data = json.loads(response)
        if 'candles' in data:
            df = pd.DataFrame(data['candles'])
            df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
            for col in ['Open', 'High', 'Low', 'Close']: 
                df[col] = df[col].astype(float)
            return df
    except Exception as e:
        print(f"Data connection skip for {symbol}: {e}")
        return None

def get_data(symbol, timeframe, is_deriv):
    time.sleep(1.0)  # Throttling guard to protect IP reputation
    if is_deriv:
        tf_map = {'15m': 900, '30m': 1800, '4h': 14400}
        return fetch_deriv_candles_sync(symbol, tf_map.get(timeframe, 900))
    else:
        try:
            period = '30d' if timeframe == '4h' else '5d'
            df = yf.download(symbol, interval=timeframe, period=period, progress=False)
            if df.empty: return None
            df.reset_index(inplace=True)
            df.columns = [str(c).strip().lower().capitalize() for c in df.columns]
            return df[['Open', 'High', 'Low', 'Close']].dropna()
        except: 
            return None

# ==========================================
# 4. CHARTNAGARI SMC STRATEGY LOGIC
# ==========================================
def scan_smc_trap(df):
    if df is None or len(df) < 50: return None
    
    df['Swing_High'] = df['High'][(df['High'] > df['High'].shift(1)) & (df['High'] > df['High'].shift(2)) & (df['High'] > df['High'].shift(-1)) & (df['High'] > df['High'].shift(-2))]
    df['Swing_Low'] = df['Low'][(df['Low'] < df['Low'].shift(1)) & (df['Low'] < df['Low'].shift(2)) & (df['Low'] < df['Low'].shift(-1)) & (df['Low'] < df['Low'].shift(-2))]
    
    highs = df['Swing_High'].dropna()
    lows = df['Swing_Low'].dropna()
    
    if len(highs) < 2 or len(lows) < 2: return None
    
    last_high = highs.iloc[-1]
    last_low = lows.iloc[-1]
    
    current_close = df['Close'].iloc[-1]
    current_high = df['High'].iloc[-1]
    current_low = df['Low'].iloc[-1]
    
    if current_high > last_high and current_close < last_high:
        return "⚠️ Sell-Side Trap: Liquidity Swept Above Swing High"
    elif current_low < last_low and current_close > last_low:
        return "⚠️ Buy-Side Trap: Liquidity Swept Below Swing Low"
    return None

# ==========================================
# 5. EXECUTION MOTOR
# ==========================================
def main():
    # Immediate Diagnostic Ping to prove the pipeline is completely repaired
    send_telegram_alert("🧪 <b>SYSTEM CHECK:</b> TradeBot Autopilot is online and actively scanning all 31 structures.")
    
    timestamp_str, is_weekend, qt_status = get_market_context()
    active_symbols = DERIV_PAIRS if is_weekend else (STANDARD_PAIRS + DERIV_PAIRS)
    triggered_alerts = []

    for symbol in active_symbols:
        is_deriv = symbol in DERIV_PAIRS
        clean_name = symbol.replace('=X', '').replace('^', '')
        
        # 1. Higher Timeframe Structure Check
        df_4h = get_data(symbol, '4h', is_deriv)
        trap_result = scan_smc_trap(df_4h)
        if trap_result:
            triggered_alerts.append(f"🏛️ <b>SMC LIQUIDITY TRAP</b>\n🚨 Signal: {trap_result}\n🎯 Asset: <b>{clean_name} (4H)</b>\n📊 Context: {qt_status}")

        # 2. Lower Timeframe Momentum Crossovers
        for tf in ['15m', '30m']:
            df = get_data(symbol, tf, is_deriv)
            if df is None or len(df) < 15: continue
            
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
            
            if df['EMA_9'].iloc[-2] <= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_12'].iloc[-1]:
                triggered_alerts.append(f"🟢 <b>EMA BULLISH CROSSOVER</b>\n📈 Asset: <b>{clean_name} ({tf})</b>\n💰 Price: {round(df['Close'].iloc[-1], 4)}")
            elif df['EMA_9'].iloc[-2] >= df['EMA_12'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_12'].iloc[-1]:
                triggered_alerts.append(f"🔴 <b>EMA BEARISH CROSSUNDER</b>\n📉 Asset: <b>{clean_name} ({tf})</b>\n💰 Price: {round(df['Close'].iloc[-1], 4)}")

    if len(triggered_alerts) > 0:
        final_payload = [f"⚡ <b>TRADERULES COMPASS SIGNALS (Lagos: {timestamp_str})</b>", "========================"]
        final_payload.extend(triggered_alerts)
        send_telegram_alert("\n\n".join(final_payload))
    else:
        print(f"Scanner executed successfully at {timestamp_str} Lagos Time. Market quiet.")

if __name__ == "__main__":
    main()
