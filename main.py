import asyncio
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = "8888331288:AAEwrMBWXjIF_mhiAARTtD2Kt4OHqrVn4ek"

ACTIVE_POSITIONS = {}

async def fetch_token_data(ca: str):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=7) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs")
                    if pairs:
                        primary = pairs[0]
                        mcap = float(primary.get("marketCap") or primary.get("fdv") or 0)
                        liquidity = float(primary.get("liquidity", {}).get("usd") or 0)
                        symbol = primary.get("baseToken", {}).get("symbol", "TOKEN")
                        return {"mcap": mcap, "liquidity": liquidity, "symbol": symbol}
    except Exception:
        pass
    return None

async def monitor_position(ca: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    pos = ACTIVE_POSITIONS[ca]
    entry_mcap = pos["entry"]

    while ca in ACTIVE_POSITIONS:
        await asyncio.sleep(10)
        data = await fetch_token_data(ca)
        if not data or data["mcap"] == 0:
            continue

        curr_mcap = data["mcap"]
        curr_liq = data["liquidity"]
        symbol = data["symbol"]

        if curr_mcap > pos["peak"]:
            pos["peak"] = curr_mcap

        peak_mcap = pos["peak"]

        # Alert 1: Liquidity Drain / Rug Check
        if curr_liq < 3000 and entry_mcap > 20000:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🚨 *RUG WARNING: ${symbol}*\nLiquidity fell to `${curr_liq:,.0f}`! Exit immediately.",
                parse_mode="Markdown"
            )
            break

        # Alert 2: 2x Take Profit Trigger
        if curr_mcap >= (entry_mcap * 2.0) and not pos["tp_hit"]:
            pos["tp_hit"] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎯 *2X TARGET HIT: ${symbol}*\n"
                    f"• Entry: `${entry_mcap:,.0f}`\n"
                    f"• Current: `${curr_mcap:,.0f}`\n"
                    f"💡 *Action:* Sell 50% to recover initial capital!"
                ),
                parse_mode="Markdown"
            )

        # Alert 3: Trailing Floor (30% drop from highest point)
        if peak_mcap >= (entry_mcap * 1.20):
            if (peak_mcap - curr_mcap) / peak_mcap >= 0.30:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🛡️ *TRAILING FLOOR HIT: ${symbol}*\n"
                        f"• Peak MCap: `${peak_mcap:,.0f}`\n"
                        f"• Current: `${curr_mcap:,.0f}`\n"
                        f"⚠️ Momentum broken. Close position to lock in profit."
                    ),
                    parse_mode="Markdown"
                )
                break

    if ca in ACTIVE_POSITIONS:
        del ACTIVE_POSITIONS[ca]

async def track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ *Usage:*\n`/track <TOKEN_CA> <ENTRY_MCAP>`\n\n*Example:*\n`/track 7xKX... 50k`",
            parse_mode="Markdown"
        )
        return

    ca = context.args[0].strip()
    raw = context.args[1].lower().strip()
    try:
        mult = 1_000_000 if raw.endswith("m") else (1_000 if raw.endswith("k") else 1)
        entry_mcap = float(raw.rstrip("km")) * mult
    except ValueError:
        await update.message.reply_text("❌ Invalid market cap. Example: `50k`, `250000`, `1.2m`")
        return

    status_msg = await update.message.reply_text("🔎 Fetching pool data...")
    data = await fetch_token_data(ca)
    if not data:
        await status_msg.edit_text("❌ Token not found on DexScreener.")
        return

    ACTIVE_POSITIONS[ca] = {
        "entry": entry_mcap,
        "peak": max(entry_mcap, data["mcap"]),
        "tp_hit": False
    }

    await status_msg.edit_text(
        f"🛡️ *Shield Active for ${data['symbol']}*\n\n"
        f"• Entry MCap: `${entry_mcap:,.0f}`\n"
        f"• Current MCap: `${data['mcap']:,.0f}`\n"
        f"• Liquidity: `${data['liquidity']:,.0f}`\n\n"
        f"Quiet mode active. Notifications sent only for TP (2x), Trailing floor (-30%), or Rug alert.",
        parse_mode="Markdown"
    )
    asyncio.create_task(monitor_position(ca, update.effective_chat.id, context))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/stop <CA>`")
        return
    ca = context.args[0].strip()
    if ca in ACTIVE_POSITIONS:
        del ACTIVE_POSITIONS[ca]
        await update.message.reply_text(f"🛑 Stopped tracking `{ca[:6]}...{ca[-4:]}`")
    else:
        await update.message.reply_text("Token not currently tracked.")

def main():
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        raise ValueError("Please replace YOUR_TELEGRAM_BOT_TOKEN_HERE with your real BotFather token!")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("track", track))
    app.add_handler(CommandHandler("stop", stop))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()