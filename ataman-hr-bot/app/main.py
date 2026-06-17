"""Ataman HR Bot — FastAPI + Telegram webhook (Vercel)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.bot.engine import BotEngine
from app.bot.handlers import handle_telegram_update
from app.config import get_settings
from app.storage.db import store
from app.telegram_api import TelegramClient
from app.together_client import TogetherClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

tg_client: TelegramClient | None = None
together_client: TogetherClient | None = None
engine: BotEngine | None = None
_ready = False


async def ensure_ready() -> None:
    global tg_client, together_client, engine, _ready
    if _ready:
        return
    settings = get_settings()
    await store.init()
    if settings.is_telegram_configured:
        tg_client = TelegramClient(settings.telegram_bot_token)
    if settings.is_together_configured:
        together_client = TogetherClient(settings.together_api_key, settings.together_model)
    if tg_client:
        engine = BotEngine(settings, together_client, tg_client)
    _ready = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_ready()
    settings = get_settings()
    if tg_client and settings.webhook_base_url:
        r = await tg_client.set_webhook(
            settings.telegram_webhook_url,
            settings.telegram_webhook_secret,
        )
        logger.info("Webhook: %s", r)
    yield


app = FastAPI(title="Ataman HR Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "ok": True,
        "telegram": settings.is_telegram_configured,
        "together": settings.is_together_configured,
        "hr_notify": settings.is_hr_notify_configured,
    }


@app.get("/setup")
@app.post("/setup")
async def setup():
    await ensure_ready()
    settings = get_settings()
    if not tg_client or not settings.webhook_base_url:
        raise HTTPException(400, "TELEGRAM_BOT_TOKEN and WEBHOOK_BASE_URL required")
    result = await tg_client.set_webhook(
        settings.telegram_webhook_url,
        settings.telegram_webhook_secret,
    )
    return {"webhook": settings.telegram_webhook_url, "result": result}


@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    await ensure_ready()
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(403, "Invalid secret")

    if not engine or not tg_client:
        raise HTTPException(503, "Bot not configured")

    body = await request.json()
    try:
        await handle_telegram_update(body, settings, tg_client, engine)
    except Exception:
        logger.exception("Handler error")
    return {"ok": True}


@app.get("/api/cron/reminders")
@app.post("/api/cron/reminders")
async def cron_reminders(
    request: Request,
    authorization: str = Header(default=""),
):
    await ensure_ready()
    settings = get_settings()
    secret = settings.cron_secret or settings.admin_token
    if secret:
        auth = authorization.replace("Bearer ", "").strip()
        q = request.query_params.get("secret", "")
        if auth != secret and q != secret:
            raise HTTPException(403, "Forbidden")

    if not engine:
        return {"sent": 0}
    n = await engine.process_reminders()
    return {"sent": n}


@app.get("/admin/stats")
async def admin_stats(authorization: str = Header(default="")):
    settings = get_settings()
    if settings.admin_token:
        if authorization.replace("Bearer ", "").strip() != settings.admin_token:
            raise HTTPException(403, "Forbidden")
    await store.init()
    stats = await store.get_stats()
    return JSONResponse(stats)
