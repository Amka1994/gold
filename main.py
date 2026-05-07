"""
XAUUSD Trading Signal Server
TradingView webhook → News filter → Signal log → Telegram alert
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import httpx
import json
import csv
import os
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

load_dotenv()

app = FastAPI()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SIGNAL_LOG       = "signals.csv"


# ════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════
async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })


# ════════════════════════════════════════
# МЭДЭЭНИЙ ШҮҮЛТ — ForexFactory RSS
# ════════════════════════════════════════
HIGH_IMPACT_KEYWORDS = [
    "Non-Farm", "NFP", "FOMC", "Fed", "CPI", "GDP",
    "Unemployment", "Interest Rate", "Inflation", "Powell"
]

async def has_high_impact_news() -> tuple[bool, str]:
    """Өнөөдөр өндөр нөлөөтэй мэдээ байгаа эсэхийг шалгана"""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.xml")
            root = ET.fromstring(r.text)

        today = datetime.now(timezone.utc).strftime("%m-%d-%Y")
        found = []

        for event in root.findall("event"):
            date  = event.findtext("date", "")
            title = event.findtext("title", "")
            impact = event.findtext("impact", "")

            if today in date and impact == "High":
                for kw in HIGH_IMPACT_KEYWORDS:
                    if kw.lower() in title.lower():
                        found.append(title)
                        break

        if found:
            return True, ", ".join(found)
        return False, ""

    except Exception:
        return False, ""


# ════════════════════════════════════════
# SIGNAL ЖУРНАЛ
# ════════════════════════════════════════
def log_signal(data: dict, blocked: bool, block_reason: str = ""):
    file_exists = os.path.exists(SIGNAL_LOG)
    with open(SIGNAL_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "datetime", "signal", "type", "price", "sl", "tp", "rr",
            "d1_trend", "entry", "blocked", "block_reason"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "datetime":    datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "signal":      data.get("signal", ""),
            "type":        data.get("type", ""),
            "price":       data.get("price", ""),
            "sl":          data.get("sl", ""),
            "tp":          data.get("tp", ""),
            "rr":          data.get("rr", ""),
            "d1_trend":    data.get("d1_trend", ""),
            "entry":       data.get("entry", ""),
            "blocked":     "YES" if blocked else "NO",
            "block_reason": block_reason
        })


# ════════════════════════════════════════
# WIN RATE ТООЦООЛОЛ
# ════════════════════════════════════════
def get_stats() -> str:
    if not os.path.exists(SIGNAL_LOG):
        return "Сигнал байхгүй байна."
    with open(SIGNAL_LOG, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sent    = [r for r in rows if r["blocked"] == "NO"]
    blocked = [r for r in rows if r["blocked"] == "YES"]
    buys    = [r for r in sent if r["signal"] == "BUY"]
    sells   = [r for r in sent if r["signal"] == "SELL"]

    return (
        f"📊 <b>Signal статистик</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Нийт сигнал    : {len(rows)}\n"
        f"Илгээгдсэн     : {len(sent)}\n"
        f"Хаагдсан       : {len(blocked)}\n"
        f"BUY сигнал     : {len(buys)}\n"
        f"SELL сигнал    : {len(sells)}\n"
    )


# ════════════════════════════════════════
# TELEGRAM МЕССЕЖ ФОРМАТЛАХ
# ════════════════════════════════════════
def format_signal(data: dict) -> str:
    signal = data.get("signal", "?")
    entry  = data.get("entry", "?")
    price  = data.get("price", "?")
    sl     = data.get("sl", "?")
    tp     = data.get("tp", "?")
    rr     = data.get("rr", "?")
    trend  = data.get("d1_trend", "?")
    time   = data.get("time", "")

    emoji        = "🟢" if signal == "BUY" else "🔴"
    entry_label  = "Confirmation ✓" if entry == "confirmation_candle" else "Risk Entry ⚡"

    return (
        f"{emoji} <b>XAUUSD {signal}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 Entry  : {entry_label}\n"
        f"💰 Price  : {price}\n"
        f"🛑 SL     : {sl}\n"
        f"🎯 TP     : {tp}\n"
        f"⚖️ RR     : 1 : {rr}\n"
        f"📈 Trend  : D1 {trend}\n"
        f"🕐 Time   : {time}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ Inducement confirmed | H1 zone reached"
    )


# ════════════════════════════════════════
# WEBHOOK ENDPOINT
# ════════════════════════════════════════
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = json.loads(await request.body())

        # Мэдээний шүүлт
        is_news, news_title = await has_high_impact_news()
        if is_news:
            log_signal(data, blocked=True, block_reason=f"High impact news: {news_title}")
            return JSONResponse({"status": "blocked", "reason": news_title})

        # Сигнал илгээх
        message = format_signal(data)
        await send_telegram(message)
        log_signal(data, blocked=False)

        return JSONResponse({"status": "ok"})

    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=400)


# ════════════════════════════════════════
# STATS ENDPOINT
# ════════════════════════════════════════
@app.get("/stats")
async def stats():
    text = get_stats()
    await send_telegram(text)
    return JSONResponse({"status": "ok"})


@app.get("/health")
async def health():
    return {"status": "running", "time": datetime.utcnow().isoformat()}
