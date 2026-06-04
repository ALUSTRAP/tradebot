import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ── CONFIG ───────────────────────────────────────────────────────────────────
TOKEN = os.environ.get("BOT_TOKEN", "8733067183:AAFNzd6vzd6_vUgrR26f8RMlo2Ygt6AR9Xk")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── RULE CONTENT ─────────────────────────────────────────────────────────────

BUY_RULES = (
    "🟢 BUY SIGNAL — ALL 6 MUST BE TRUE\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "✅ 1. EMA CROSSOVER TRIGGER\n"
    "EMA 9 crosses ABOVE EMA 21\n"
    "Cross must be on a CLOSED 30-min candle\n\n"
    "✅ 2. TREND FILTER (EMA 50 & 200)\n"
    "Price ABOVE EMA 50 and EMA 200\n"
    "EMA 50 must be ABOVE EMA 200\n"
    "Do NOT buy below EMA 50 or 200\n\n"
    "✅ 3. MACD (12, 26, 9)\n"
    "MACD line crossed ABOVE signal line\n"
    "Histogram above zero or just crossed\n"
    "Bars increasing in size for 2+ candles\n\n"
    "✅ 4. RSI (Period 10)\n"
    "RSI must be between 55 and 75\n"
    "Above 75 = overbought → SKIP\n"
    "Below 55 = weak momentum → SKIP\n\n"
    "✅ 5. SESSION FILTER\n"
    "London: 8am – 12pm GMT+1\n"
    "New York: 2pm – 6pm GMT+1\n"
    "No entries 30 min before red news\n\n"
    "✅ 6. NOT OVEREXTENDED\n"
    "Price within 80 pts of EMA 21 (NAS100)\n"
    "Within 200 pts for US30\n"
    "If too far without pullback → SKIP"
)

SELL_RULES = (
    "🔴 SELL SIGNAL — ALL 6 MUST BE TRUE\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "✅ 1. EMA CROSSOVER TRIGGER\n"
    "EMA 9 crosses BELOW EMA 21\n"
    "Cross must be on a CLOSED 30-min candle\n\n"
    "✅ 2. TREND FILTER (EMA 50 & 200)\n"
    "Price BELOW EMA 50 and EMA 200\n"
    "EMA 50 must be BELOW EMA 200\n"
    "Do NOT sell above EMA 50 or 200\n\n"
    "✅ 3. MACD (12, 26, 9)\n"
    "MACD line crossed BELOW signal line\n"
    "Histogram below zero or just crossed\n"
    "Bars increasing downward for 2+ candles\n\n"
    "✅ 4. RSI (Period 10)\n"
    "RSI must be between 25 and 45\n"
    "Below 25 = oversold → SKIP\n"
    "Above 45 = weak bearish momentum → SKIP\n\n"
    "✅ 5. SESSION FILTER\n"
    "London: 8am – 12pm GMT+1\n"
    "New York: 2pm – 6pm GMT+1\n"
    "No entries 30 min before red news\n\n"
    "✅ 6. NOT OVEREXTENDED\n"
    "Price within 80 pts of EMA 21 (NAS100)\n"
    "Within 200 pts for US30\n"
    "If too far without pullback → SKIP"
)

EXIT_RULES = (
    "📤 EXIT & RISK MANAGEMENT\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔴 Stop Loss (NAS100): 25–30 pts below EMA 21\n"
    "🔴 Stop Loss (US30): 60–70 pts below EMA 21\n\n"
    "📐 Min Risk:Reward: 1:2 minimum\n"
    "If TP is not 2x your SL distance → SKIP\n\n"
    "💚 Take Profit 1 (50%): 1.5R from entry\n"
    "💚 Take Profit 2 (50%): 2.5R – 3R from entry\n\n"
    "🔵 Trailing Stop:\n"
    "After TP1 hit → move SL to breakeven + 10 pts\n\n"
    "⚡ EMA Exit Signal:\n"
    "EMA 9 crosses back through EMA 21 → close now\n\n"
    "⛔ Daily Loss Limit: $2,000 (2%) → close platform\n"
    "🚫 Max Trades Per Day: 3 trades only\n"
    "👥 Max Open Trades: 3 concurrent positions"
)

SKIP_RULES = (
    "🚫 SKIP THE TRADE — IF ANY ONE IS TRUE\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "✖ EMA cross happened but price below EMA 50 or 200\n"
    "✖ EMA 50 on wrong side of EMA 200\n"
    "✖ MACD histogram shrinking not growing\n"
    "✖ RSI (10) above 75 (buy) or below 25 (sell)\n"
    "✖ RSI diverging from price direction\n"
    "✖ Price more than 80 pts from EMA 21 (NAS100)\n"
    "✖ Within 30 min of red-folder news event\n"
    "✖ Outside London or NY session window\n"
    "✖ Already taken 3 trades today"
)

LOT_SIZES = (
    "📐 POSITION SIZING — $100K Account\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "0.5% → $500  | NAS100: 0.5 lots | US30: 0.8 lots\n"
    "1.0% → $1,000 | NAS100: 1.0 lots | US30: 1.5 lots\n"
    "1.5% → $1,500 | NAS100: 1.5 lots | US30: 2.2 lots\n\n"
    "💡 Recommended: 0.5% – 1% per trade\n\n"
    "⚠ Max 3 concurrent trades\n"
    "⚠ Max 3% total open exposure at once\n"
    "⚠ Daily loss $2,000 (2%) = close platform"
)

EMA_GUIDE = (
    "📊 EMA & INDICATOR SETTINGS\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Set these on your 30-min chart:\n\n"
    "〰 EMA 9   — Fast line (entry trigger)\n"
    "〰 EMA 21  — Slow line (entry trigger)\n"
    "〰 EMA 50  — Medium trend filter\n"
    "〰 EMA 200 — Major trend filter\n\n"
    "MACD Settings:\n"
    "Fast: 12  Slow: 26  Signal: 9\n\n"
    "RSI Settings:\n"
    "Period: 10 (NOT the default 14 — change it!)\n"
    "Overbought: 75  Oversold: 25\n\n"
    "Quick read:\n"
    "✅ BUY ZONE: Price > EMA50 > EMA200, EMA9 crosses above EMA21\n"
    "✅ SELL ZONE: Price < EMA50 < EMA200, EMA9 crosses below EMA21\n"
    "🚫 AVOID: Price between EMA50 and EMA200 (choppy zone)"
)

CHECKLIST_QUESTIONS_BUY = [
    "Has EMA 9 crossed ABOVE EMA 21 on a CLOSED 30-min candle?",
    "Is price trading ABOVE EMA 50?",
    "Is price trading ABOVE EMA 200?",
    "Is EMA 50 above EMA 200? (uptrend confirmed)",
    "Has MACD line crossed above signal line with histogram growing?",
    "Is RSI (10) between 55 and 75?",
    "Are you in London (8am-12pm) or NY (2pm-6pm) GMT+1?",
    "Is there NO red-folder news in the next 30 minutes?",
    "Is price within 80 pts of EMA 21 (NAS100) / 200 pts (US30)?",
]

CHECKLIST_QUESTIONS_SELL = [
    "Has EMA 9 crossed BELOW EMA 21 on a CLOSED 30-min candle?",
    "Is price trading BELOW EMA 50?",
    "Is price trading BELOW EMA 200?",
    "Is EMA 50 below EMA 200? (downtrend confirmed)",
    "Has MACD line crossed below signal line with histogram growing downward?",
    "Is RSI (10) between 25 and 45?",
    "Are you in London (8am-12pm) or NY (2pm-6pm) GMT+1?",
    "Is there NO red-folder news in the next 30 minutes?",
    "Is price within 80 pts of EMA 21 (NAS100) / 200 pts (US30)?",
]

# ── KEYBOARDS ─────────────────────────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 BUY Rules", callback_data="buy"),
         InlineKeyboardButton("🔴 SELL Rules", callback_data="sell")],
        [InlineKeyboardButton("📤 Exit Rules", callback_data="exit"),
         InlineKeyboardButton("🚫 Skip Conditions", callback_data="skip")],
        [InlineKeyboardButton("📐 Lot Sizes", callback_data="lots"),
         InlineKeyboardButton("📊 EMA Settings", callback_data="ema")],
        [InlineKeyboardButton("✅ Check BUY Setup", callback_data="check_buy_0_0")],
        [InlineKeyboardButton("✅ Check SELL Setup", callback_data="check_sell_0_0")],
    ])

# ── HANDLERS ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 TRADE RULES BOT\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "EMA 9 / 21 / 50 / 200\n"
        "MACD (12,26,9) · RSI (10)\n"
        "30-Min · NAS100 / US30\n\n"
        "Choose a section below 👇",
        reply_markup=main_menu_keyboard()
    )

async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(BUY_RULES)

async def sell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(SELL_RULES)

async def exit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(EXIT_RULES)

async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(SKIP_RULES)

async def lots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(LOT_SIZES)

async def ema_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(EMA_GUIDE)

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ TRADE CHECKER\n\nWhich direction are you trading?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Check BUY Setup", callback_data="check_buy_0_0")],
            [InlineKeyboardButton("🔴 Check SELL Setup", callback_data="check_sell_0_0")],
        ])
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    static = {
        "buy": BUY_RULES, "sell": SELL_RULES,
        "exit": EXIT_RULES, "skip": SKIP_RULES,
        "lots": LOT_SIZES, "ema": EMA_GUIDE
    }
    if data in static:
        await query.message.reply_text(static[data])
        return

    if data.startswith("check_"):
        parts = data.split("_")
        direction = parts[1]
        q_index = int(parts[2])
        yes_count = int(parts[3])
        questions = CHECKLIST_QUESTIONS_BUY if direction == "buy" else CHECKLIST_QUESTIONS_SELL
        color = "🟢" if direction == "buy" else "🔴"
        label = "BUY" if direction == "buy" else "SELL"

        if q_index >= len(questions):
            if yes_count == len(questions):
                await query.message.reply_text(
                    f"✅ TRADE VALID — TAKE THE TRADE!\n\n"
                    f"{color} All {len(questions)} conditions confirmed.\n\n"
                    f"Before you enter:\n"
                    f"• SL: 25–30 pts below EMA 21 (NAS100)\n"
                    f"• Confirm R:R is minimum 1:2\n"
                    f"• Risk max 1% on this trade\n"
                    f"• TP1 at 1.5R → move SL to breakeven\n"
                    f"• TP2 at 2.5R – 3R\n\n"
                    f"Trade with discipline. Protect the account."
                )
            else:
                failed = len(questions) - yes_count
                await query.message.reply_text(
                    f"🚫 DO NOT TAKE THIS TRADE\n\n"
                    f"❌ {failed} condition(s) not met.\n\n"
                    f"Wait for full confluence.\n"
                    f"A skipped bad trade is a WINNING trade.\n\n"
                    f"Patience is your edge."
                )
            return

        question = questions[q_index]
        progress = f"{q_index + 1}/{len(questions)}"
        await query.message.reply_text(
            f"{color} {label} CHECKER — Question {progress}\n\n"
            f"{question}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ YES",
                        callback_data=f"check_{direction}_{q_index + 1}_{yes_count + 1}"
                    ),
                    InlineKeyboardButton(
                        "❌ NO — SKIP",
                        callback_data=f"check_{direction}_{len(questions)}_0"
                    ),
                ]
            ])
        )

# ── MAIN ──────────────────────────────────────────────────────────────────────

async def run():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", buy_cmd))
    app.add_handler(CommandHandler("sell", sell_cmd))
    app.add_handler(CommandHandler("exit", exit_cmd))
    app.add_handler(CommandHandler("skip", skip_cmd))
    app.add_handler(CommandHandler("lots", lots_cmd))
    app.add_handler(CommandHandler("ema", ema_cmd))
    app.add_handler(CommandHandler("check", check_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(run())
