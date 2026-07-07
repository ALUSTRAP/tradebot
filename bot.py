Import os
import json
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import websocket  # Synchronous client bypassing the GitHub event loop bug
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURATION & TARGET ASSETS
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STANDARD_PAIRS = [
    # Forex Majors
    'EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'USDCHF=X', 'USDCAD=X', 'NZDUSD=X',

    # Crosses
    'EURGBP=X', 'EURAUD=X', 'AUDCAD=X', 'GBPAUD=X', 'GBPCAD=X',

    # Precious Metals
    'GC=F',  # Gold COMEX Futures
    'SI=F',  # Silver COMEX Futures
    
    # Global Indices
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
    'BOOM50', 'BOOM100', 'BOOM150', 'BOOM200', 
    'BOOM300', 'BOOM500', 'BOOM600', 'BOOM900', 'BOOM1000',
    # Crash Indices
    'CRASH50', 'CRASH100', 'CRASH150', 'CRASH200', 
    'CRASH300', 'CRASH500', 'CRASH600', 'CRASH900', 'CRASH1000',
    # Step Indices
    'STP', 'STP200', 'STP300', 'STP400', 'STP500'
]

def send_telegram_alert(message):
    token = str(TELEGRAM_BOT_TOKEN).strip()
    if token.lower().startswith("bot"):
        token = token[3:]  
        
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
# 3. ROBUST DATA FETCHING & RESAMPLING MATRIX
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
    if is_deriv:
        time.sleep(0.1)  
        tf_map = {'15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '8h': 28800}
        return fetch_deriv_candles_sync(symbol, tf_map.get(timeframe, 900))
    else:
        time.sleep(1.2)  
        try:
            # Realigned configuration parameters for traditional asset stability
            if timeframe == '1d':
                yf_interval = '1d'
                period = '90d'
            elif timeframe == '4h':
                yf_interval = '1h'  # Download hourly bars to build custom 4H data frames
                period = '30d'
            elif timeframe == '1h':
                yf_interval = '1h'
                period = '14d'
            else:
                yf_interval = timeframe
                period = '5d'
                
            df = yf.download(symbol, interval=yf_interval, period=period, progress=False)
            if df is None or df.empty:
                return None
                
            # CRITICAL FIX: Flatten MultiIndex columns returned by modern yfinance engines
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            # CRITICAL FIX: Custom Resampling Engine for 4-Hour structures
            if timeframe == '4h':
                df = df.resample('4H').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
                }).dropna()
                
            return df
        except Exception as e:
            print(f"⚠️ Yahoo Finance Error on {symbol} ({timeframe}): {e}")
            return None

# ==========================================
# 4. LIVE ECONOMIC CALENDAR DATA ENGINE
# ==========================================
def clean_economic_value(val_str):
    if not val_str or str(val_str).strip() == "": return None
    try:
        clean = "".join([c for c in str(val_str) if c.isdigit() or c in ['.', '-']])
        return float(clean) if clean else None
    except:
        return None

def fetch_economic_news_alerts():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    news_alerts = []
    try:
        res = requests.get(url, timeout=12)
        if res.status_code != 200:
            print(f"⚠️ News API connection response code: {res.status_code}")
            return news_alerts
            
        events = res.json()
        lagos_today = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d")
        
        for event in events:
            if lagos_today in event.get('date', ''):
                impact = event.get('impact', 'Low')
                country = event.get('country', '')
                title = event.get('title', '')
                
                event_time = event.get('time', '')
                if not event_time and 'T' in event.get('date', ''):
                    event_time = event.get('date', '').split('T')[1][:5]
                if not event_time:
                    event_time = "Specified Today"
                
                if impact in ['High', 'Medium'] and country in ['USD', 'EUR', 'GBP', 'AUD', 'CAD', 'CHF', 'NZD']:
                    act_str = event.get('actual', '')
                    for_str = event.get('forecast', '')
                    prev_str = event.get('previous', '')
                    
                    if not act_str:
                        news_alerts.append(
                            f"📅 <b>UPCOMING IMPACT NEWS ALERT</b>\n"
                            f"🔴 Impact: <b>{impact}</b>\n"
                            f"⏰ Time: <b>{event_time}</b>\n"
                            f"🌐 Currency: <b>{country}</b> | Asset: <b>{title}</b>\n"
                            f"📊 Status: Pending Release (Standby for direction)"
                        )
                    else:
                        act_val = clean_economic_value(act_str)
                        for_val = clean_economic_value(for_str)
                        
                        bias_message = "🔄 Mixed/Neutral Bias (Watch price action structure)"
                        
                        if act_val is not None and for_val is not None:
                            is_inverted = any(k in title.lower() for k in ['unemployment', 'claims', 'jobless'])
                            is_better = (act_val < for_val) if is_inverted else (act_val > for_val)
                            
                            if country == 'USD':
                                if is_better:
                                    bias_message = "🦅 <b>USD STRONG (BUY USD Bias)</b>\n📉 <b>SELL:</b> EURUSD, GBPUSD, AUDUSD, NZDUSD, ^GSPC, ^IXIC\n📈 <b>BUY:</b> USDCAD, USDCHF"
                                else:
                                    bias_message = "🪵 <b>USD WEAK (SELL USD Bias)</b>\n📈 <b>BUY:</b> EURUSD, GBPUSD, AUDUSD, NZDUSD, ^GSPC, ^IXIC\n📉 <b>SELL:</b> USDCAD, USDCHF"
                            elif country == 'EUR':
                                bias_message = f"📈 <b>BUY EURUSD</b>" if is_better else f"📉 <b>SELL EURUSD</b>"
                            elif country == 'GBP':
                                bias_message = f"📈 <b>BUY GBPUSD</b>" if is_better else f"📉 <b>SELL GBPUSD</b>"
                            elif country == 'AUD':
                                bias_message = f"📈 <b>BUY AUDUSD</b>" if is_better else f"📉 <b>SELL AUDUSD</b>"
                            elif country == 'NZD':
                                bias_message = f"📈 <b>BUY NZDUSD</b>" if is_better else f"📉 <b>SELL NZDUSD</b>"
                            elif country == 'CAD':
                                bias_message = f"📉 <b>SELL USDCAD</b>" if is_better else f"📈 <b>BUY USDCAD</b>"
                            elif country == 'CHF':
                                bias_message = f"📉 <b>SELL USDCHF</b>" if is_better else f"📈 <b>BUY USDCHF</b>"
                        
                        news_alerts.append(
                            f"⚡ <b>LIVE ECONOMIC RELEASE IMPACT</b>\n"
                            f"📢 Event: <b>{title} ({country})</b>\n"
                            f"⏰ Time: <b>{event_time}</b>\n"
                            f"🎯 Actual: <b>{act_str}</b> | Forecast: <b>{for_str}</b> | Prev: {prev_str}\n"
                            f"⚖️ Macro Directional Vector:\n{bias_message}"
                        )
        return news_alerts
    except Exception as e:
        print(f"❌ Failed to parse macroeconomic calendar: {e}")
        return news_alerts

# ==========================================
# 5. CHARTNAGARI SMC STRATEGY LOGIC
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
# 6. EXECUTION ENGINE (WITH ASSET GROUPING)
# ==========================================
def main():
    send_telegram_alert("🧪 <b>SYSTEM CHECK:</b> TradeBot Autopilot is running unified scan matrix.")
    
    timestamp_str, is_weekend, qt_status = get_market_context()
    active_symbols = DERIV_PAIRS if is_weekend else (STANDARD_PAIRS + DERIV_PAIRS)
    
    # Core dictionary map for collecting technical signals organized strictly by asset key
    asset_grouped_alerts = {}
    
    economic_news = [] if is_weekend else fetch_economic_news_alerts()

    for symbol in active_symbols:
        is_deriv = symbol in DERIV_PAIRS
        clean_name = symbol.replace('=X', '').replace('^', '')
        
        # Local container for any active triggers on this unique symbol loop
        current_pair_alerts = []
        
        # 1. Higher Timeframe Structure Check
        df_4h = get_data(symbol, '4h', is_deriv)
        trap_result = scan_smc_trap(df_4h)
        if trap_result:
            current_pair_alerts.append(f"🏛️ <b>SMC LIQUIDITY TRAP (4H)</b>\n🚨 Signal: {trap_result}\n📊 Context: {qt_status}")

        # 2. Lower & Macro Timeframe Engine Loops
        # Custom timeframes loop: Uses 8h for Deriv websockets, drops 8h for Daily ('1d') on yfinance
        target_timeframes = ['15m', '30m', '1h', '4h', '8h'] if is_deriv else ['15m', '30m', '1h', '4h', '1d']
        
        for tf in target_timeframes:
            df = get_data(symbol, tf, is_deriv)
            if df is None or len(df) < 30: continue  
            
            # --- 9 / 21 EMA MATRIX ---
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()  
            
            if df['EMA_9'].iloc[-2] <= df['EMA_21'].iloc[-2] and df['EMA_9'].iloc[-1] > df['EMA_21'].iloc[-1]:
                current_pair_alerts.append(f"🟢 <b>EMA BULLISH CROSSOVER (9/21) [{tf}]</b>\n💰 Price: {round(df['Close'].iloc[-1], 4)}")
            elif df['EMA_9'].iloc[-2] >= df['EMA_21'].iloc[-2] and df['EMA_9'].iloc[-1] < df['EMA_21'].iloc[-1]:
                current_pair_alerts.append(f"🔴 <b>EMA BEARISH CROSSUNDER (9/21) [{tf}]</b>\n📉 Price: {round(df['Close'].iloc[-1], 4)}")

            # --- DeMARKER 15 DIRECTIONAL ENGINE ---
            if tf in ['30m', '1h', '4h', '8h', '1d']:
                high_diff = df['High'].diff()
                demax = np.where(high_diff > 0, high_diff, 0.0)
                
                low_diff = df['Low'].shift(1) - df['Low']
                demin = np.where(low_diff > 0, low_diff, 0.0)
                
                demax_sma = pd.Series(demax).rolling(window=15).mean()
                demin_sma = pd.Series(demin).rolling(window=15).mean()
                
                demarker_series = demax_sma / (demax_sma + demin_sma)
                
                if len(demarker_series) >= 3:
                    current_dem = demarker_series.iloc[-2]
                    prev_dem = demarker_series.iloc[-3]
                    current_price = df['Close'].iloc[-1]
                    
                    if prev_dem < 0.3 and current_dem >= 0.3:
                        current_pair_alerts.append(
                            f"🔵 <b>DeMARKER 15 BUY SIGNAL [{tf}]</b>\n"
                            f"💰 Price: {round(current_price, 4)} | 📊 Value: {round(current_dem, 4)}\n"
                            f"🔄 Context: Oversold recovery confirmation"
                        )
                    elif prev_dem > 0.7 and current_dem <= 0.7:
                        current_pair_alerts.append(
                            f"🔴 <b>DeMARKER 15 SELL SIGNAL [{tf}]</b>\n"
                            f"📉 Price: {round(current_price, 4)} | 📊 Value: {round(current_dem, 4)}\n"
                            f"🔄 Context: Overbought distribution confirmation"
                        )
                        
        # Store technical indicators grouped neatly under the target pair
        if current_pair_alerts:
            asset_grouped_alerts[clean_name] = current_pair_alerts

    # ==========================================
    # 7. TELEGRAM DISPATCH FORMATTING MATRIX
    # ==========================================
    if len(economic_news) > 0 or len(asset_grouped_alerts) > 0:
        final_payload = [f"⚡ <b>TRADERULES COMPASS SIGNALS (Lagos: {timestamp_str})</b>", "========================"]
        
        # A. Append macro calendar releases first
        if economic_news:
            final_payload.extend(economic_news)
            final_payload.append("========================")
            
        # B. Append technical parameters systematically categorized under individual Asset blocks
        if asset_grouped_alerts:
            for asset_name, signals in asset_grouped_alerts.items():
                asset_block = f"🔸 <b>{asset_name}</b>\n" + "\n\n".join(signals)
                final_payload.append(asset_block)
                
        send_telegram_alert("\n\n".join(final_payload))
    else:
        print(f"Scanner executed successfully at {timestamp_str} Lagos Time. Market quiet.")

if __name__ == "__main__":
    main()
