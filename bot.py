import asyncio
import json
import ccxt.async_support as ccxt
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config import BOT_TOKEN

exchange = ccxt.bitget()

RULES = [
    "Risk maksimal 1%",
    "RR minimal 1:3",
    "Tidak averaging loss",
    "Tidak revenge trade",
    "Maksimal 2 posisi aktif"
]

MAIN_KEYBOARD = [
    ["📈 Harga", "🚨 Alert"],
    ["📋 Alerts", "🗑 Hapus Alert"],
    ["📖 Rules", "✅ Checklist"]
]

PAIRS = ["BTCUSDT", "HYPEUSDT", "XRPUSDT", "ETHUSDT"]


# ============================================================
# COMMAND HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    reply_markup = ReplyKeyboardMarkup(
        MAIN_KEYBOARD,
        resize_keyboard=True
    )

    await update.message.reply_text(
        "Selamat datang di Trading Assistant\n\n"
        "Gunakan tombol di bawah, atau ketik command:\n"
        "/harga BTCUSDT\n"
        "/setalert BTCUSDT 105000 106000\n"
        "/alerts\n"
        "/delalert BTCUSDT\n"
        "/jurnal BTCUSDT BUY\n"
        "/rules\n"
        "/periksa",
        reply_markup=reply_markup
    )


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):

    txt = "\n".join([f"✅ {x}" for x in RULES])

    await update.message.reply_text(txt)


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
CHECKLIST ENTRY

☑ Trend sesuai
☑ Liquidity Sweep
☑ MSS / BOS
☑ Entry di OB/FVG
☑ RR > 1:3

Jika ada yang tidak terpenuhi:
JANGAN ENTRY.
"""

    await update.message.reply_text(text)


def symbol_to_pair(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol.endswith("USDT"):
        return symbol[:-4] + "/USDT"
    return symbol


async def fetch_price_text(symbol: str) -> str:
    """Fetch current price for a symbol like 'BTCUSDT' and format the reply text."""

    pair = symbol_to_pair(symbol)

    try:
        ticker = await exchange.fetch_ticker(pair)
        price = ticker["last"]
        return f"{pair}\nHarga: {price}"

    except Exception as e:
        return f"Error: {e}"


async def harga(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:

        keyboard = [
            [InlineKeyboardButton(p, callback_data=f"harga:{p}")]
            for p in PAIRS
        ]

        await update.message.reply_text(
            "Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    symbol = context.args[0]

    text = await fetch_price_text(symbol)

    await update.message.reply_text(text)


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        with open("watchlist.json") as f:
            data = json.load(f)
    except FileNotFoundError:
        await update.message.reply_text(
            "watchlist.json tidak ditemukan."
        )
        return

    msg = "WATCHLIST\n\n"

    for pair in data["symbols"]:

        try:

            ticker = await exchange.fetch_ticker(pair)

            msg += f"{pair} : {ticker['last']}\n"

        except Exception:
            msg += f"{pair} : error\n"

    await update.message.reply_text(msg)


async def jurnal(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) < 2:

        await update.message.reply_text(
            "Contoh:\n/jurnal BTCUSDT BUY"
        )
        return

    pair = context.args[0]
    side = context.args[1]

    data = {
        "tanggal": str(datetime.now()),
        "pair": pair,
        "side": side
    }

    try:
        with open("journal.json") as f:
            journal = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        journal = []

    journal.append(data)

    with open("journal.json", "w") as f:
        json.dump(journal, f, indent=4)

    await update.message.reply_text(
        "Jurnal tersimpan."
    )


async def setalert(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 3:

        await update.message.reply_text(
            "Format:\n/setalert BTCUSDT 105000 106000"
        )
        return

    symbol = context.args[0].upper()

    try:
        low = float(context.args[1])
        high = float(context.args[2])
    except ValueError:
        await update.message.reply_text(
            "Low dan high harus angka."
        )
        return

    if low > high:
        low, high = high, low

    alerts = load_alerts()

    alerts[symbol] = {
        "low": low,
        "high": high,
        "chat_id": update.effective_chat.id,
        "triggered": False
    }

    save_alerts(alerts)

    await update.message.reply_text(
        f"Alert tersimpan\n{symbol}\n{low}-{high}"
    )


async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = load_alerts()

    if not data:
        await update.message.reply_text("Belum ada alert")
        return

    msg = "DAFTAR ALERT\n\n"

    for symbol, info in data.items():

        status = "🔔 triggered" if info.get("triggered") else "⏳ menunggu"

        msg += (
            f"{symbol}\n"
            f"{info['low']} - {info['high']}\n"
            f"{status}\n\n"
        )

    await update.message.reply_text(msg)


async def delalert(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 1:

        await update.message.reply_text(
            "Format:\n/delalert BTCUSDT"
        )
        return

    symbol = context.args[0].upper()

    alerts = load_alerts()

    if symbol in alerts:
        del alerts[symbol]

        save_alerts(alerts)

        await update.message.reply_text(
            f"{symbol} dihapus"
        )

    else:
        await update.message.reply_text(
            "Alert tidak ditemukan"
        )


# ============================================================
# BUTTON (REPLY KEYBOARD) HANDLER
# ============================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Routes presses on the ReplyKeyboardMarkup buttons.
    These arrive as plain text messages, not commands.
    """

    text = update.message.text

    if text == "📈 Harga":

        keyboard = [
            [InlineKeyboardButton(p, callback_data=f"harga:{p}")]
            for p in PAIRS
        ]

        await update.message.reply_text(
            "Pilih pair:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif text == "🚨 Alert":
        await update.message.reply_text(
            "Ketik:\n/setalert SYMBOL LOW HIGH\n\n"
            "Contoh:\n/setalert BTCUSDT 105000 106000"
        )

    elif text == "📋 Alerts":
        await alerts_cmd(update, context)

    elif text == "🗑 Hapus Alert":
        await update.message.reply_text(
            "Ketik:\n/delalert SYMBOL\n\nContoh: /delalert BTCUSDT"
        )

    elif text == "📖 Rules":
        await rules(update, context)

    elif text == "✅ Checklist":
        await check(update, context)

    else:
        await update.message.reply_text(
            "Command tidak dikenali. Gunakan /start untuk lihat menu."
        )


# ============================================================
# INLINE KEYBOARD HANDLER (pair buttons)
# ============================================================

async def harga_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles taps on the inline 'Pilih pair' buttons.
    callback_data format: 'harga:BTCUSDT'
    """

    query = update.callback_query

    await query.answer()

    symbol = query.data.split(":", 1)[1]

    text = await fetch_price_text(symbol)

    await query.edit_message_text(text)


# ============================================================
# ALERT MONITOR (BACKGROUND TASK)
# ============================================================

async def monitor_alerts(app):

    while True:

        alerts = load_alerts()

        changed = False

        for symbol, info in alerts.items():

            try:

                pair = symbol.replace("USDT", "/USDT")

                ticker = await exchange.fetch_ticker(pair)

                price = ticker["last"]

                low = info["low"]
                high = info["high"]

                if low <= price <= high:

                    if not info["triggered"]:

                        await app.bot.send_message(
                            chat_id=info["chat_id"],
                            text=(
                                f"🚨 ENTRY ALERT\n\n"
                                f"{symbol}\n"
                                f"Harga: {price}\n"
                                f"Zona: {low}-{high}"
                            )
                        )

                        alerts[symbol]["triggered"] = True

                        changed = True

                else:

                    if info["triggered"]:

                        alerts[symbol]["triggered"] = False

                        changed = True

            except Exception as e:

                print(e)

        if changed:
            save_alerts(alerts)

        await asyncio.sleep(30)


async def post_init(app):

    asyncio.create_task(
        monitor_alerts(app)
    )


# ============================================================
# JSON HELPERS
# ============================================================

def load_alerts():
    try:
        with open("alerts.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_alerts(data):
    with open("alerts.json", "w") as f:
        json.dump(data, f, indent=4)


# ============================================================
# APP SETUP
# ============================================================

app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("rules", rules))
app.add_handler(CommandHandler("periksa", check))
app.add_handler(CommandHandler("harga", harga))
app.add_handler(CommandHandler("watchlist", watchlist))
app.add_handler(CommandHandler("jurnal", jurnal))
app.add_handler(CommandHandler("setalert", setalert))
app.add_handler(CommandHandler("alerts", alerts_cmd))
app.add_handler(CommandHandler("delalert", delalert))

# Inline pair-picker buttons (callback_data "harga:SYMBOL")
app.add_handler(CallbackQueryHandler(harga_callback, pattern=r"^harga:"))

# Catches button presses (plain text, not commands)
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

print("Bot berjalan...")

app.run_polling()
