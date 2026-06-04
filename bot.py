import os
import requests

def get_live_market_data():
    """Fetches live exchange rates and major stock indices using public endpoints."""
    # 1. Fetch Forex Data
    forex_url = "https://open.er-api.com/v6/latest/USD"
    forex_text = "⚠️ Unable to fetch Forex market data."
    
    try:
        f_response = requests.get(forex_url)
        f_data = f_response.json()
        
        if f_data.get("result") == "success":
            rates = f_data.get("rates", {})
            
            # Extract standard requested pairs (Reciprocals where USD is the quote)
            eur_usd = 1 / rates.get("EUR", 1)
            gbp_usd = 1 / rates.get("GBP", 1)
            aud_usd = 1 / rates.get("AUD", 1)
            nzd_usd = 1 / rates.get("NZD", 1)
            
            # Standard USD base pairs
            usd_jpy = rates.get("JPY", 1)
            usd_chf = rates.get("CHF", 1)
            usd_cad = rates.get("CAD", 1)
            
            forex_text = (
                "💱 **Major Forex Pairs**\n"
                f"• EUR/USD: `{eur_usd:.4f}`\n"
                f"• GBP/USD: `{gbp_usd:.4f}`\n"
                f"• USD/JPY: `{usd_jpy:.2f}`\n"
                f"• USD/CHF: `{usd_chf:.4f}`\n"
                f"• AUD/USD: `{aud_usd:.4f}`\n"
                f"• USD/CAD: `{usd_cad:.4f}`\n"
                f"• NZD/USD: `{nzd_usd:.4f}`\n"
            )
    except Exception as e:
        forex_text = f"⚠️ Forex Connection Error: {str(e)}"

    # 2. Fetch Major Stock Indices Data
    indices_url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=^GSPC,^IXIC,^DJI,^FTSE,^GDAXI,^N225,^STOXX50E,^FCHI,^AXJO"
    # Using a standard browser header to ensure Yahoo allows the script connection
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    indices_text = "⚠️ Unable to fetch Stock Indices data."
    
    try:
        i_response = requests.get(indices_url, headers=headers)
        i_data = i_response.json()
        result_list = i_data.get("quoteResponse", {}).get("result", [])
        
        # Build dictionary matching ticker symbols to current market prices
        prices = {item.get("symbol"): item.get("regularMarketPrice", 0.0) for item in result_list}
        
        indices_text = (
            "📈 **Major Stock Indices**\n"
            f"• S&P 500: `{prices.get('^GSPC', 0.0):,.2f}`\n"
            f"• Nasdaq 100: `{prices.get('^IXIC', 0.0):,.2f}`\n"
            f"• Dow Jones: `{prices.get('^DJI', 0.0):,.2f}`\n"
            f"• FTSE 100 (UK): `{prices.get('^FTSE', 0.0):,.2f}`\n"
            f"• DAX 40 (Germany): `{prices.get('^GDAXI', 0.0):,.2f}`\n"
            f"• Nikkei 225 (Japan): `{prices.get('^N225', 0.0):,.2f}`\n"
            f"• Euro Stoxx 50: `{prices.get('^STOXX50E', 0.0):,.2f}`\n"
            f"• CAC 40 (France): `{prices.get('^FCHI', 0.0):,.2f}`\n"
            f"• ASX 200 (Australia): `{prices.get('^AXJO', 0.0):,.2f}`\n"
        )
    except Exception as e:
        indices_text = f"⚠️ Indices Connection Error: {str(e)}"

    # Combine into a final summary update
    final_message = (
        "📊 **Live Market Update** 📊\n"
        "-------------------------\n"
        f"{forex_text}\n"
        f"{indices_text}"
        "-------------------------\n"
        "⏰ *Checked automatically via GitHub*"
    )
    return final_message

def send_telegram_alert(text_message):
    """Sends the formatted alert to your Telegram Bot."""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("Missing API tokens. Check your GitHub Secrets!")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text_message,
        "parse_mode": "Markdown"
    }
    
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Alert sent successfully to Telegram!")
    else:
        print(f"Failed to send message: {response.text}")

if __name__ == "__main__":
    market_update = get_live_market_data()
    send_telegram_alert(market_update)
