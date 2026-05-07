"""
XAUUSD Trading Signal Server
TradingView webhook → Telegram alert
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import json
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })


def format_signal(data: dict) -> str:
    signal    = data.get("signal", "?")
    entry     = data.get("entry", "?")
    price     = data.get("price", "?")
    d1_trend  = data.get("d1_trend", "?")
    time_raw  = data.get("time", "")

    emoji = "🟢" if signal == "BUY" else "🔴"
    entry_label = "Confirmation ✓" if entry == "confirmation_candle" else "Risk Entry ⚡"

    return (
        f"{emoji} <b>XAUUSD {signal}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 Entry type : {entry_label}\n"
        f"💰 Price      : {price}\n"
        f"📈 D1 Trend   : {d1_trend}\n"
        f"🕐 Time       : {time_raw}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ Inducement confirmed | H1 zone reached"
    )


@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.body()
        data = json.loads(body)
        message = format_signal(data)
        await send_telegram(message)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=400)


@app.get("/health")
async def health():
    return {"status": "running", "time": datetime.utcnow().isoformat()}
