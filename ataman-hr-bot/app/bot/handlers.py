from __future__ import annotations

import logging
from typing import Any

from app.bot.engine import BotEngine
from app.bot.outbound import deliver_bot_reply
from app.config import Settings
from app.hr_notify import notify_hr
from app.storage.db import store
from app.telegram_api import TelegramClient, detect_message_lang, extract_update_info

logger = logging.getLogger(__name__)


async def handle_telegram_update(
    body: dict[str, Any],
    settings: Settings,
    tg: TelegramClient,
    engine: BotEngine,
) -> None:
    chat_id, text, sender_name, callback_id = extract_update_info(body)
    if not chat_id:
        return

    if callback_id:
        await tg.answer_callback_query(callback_id)

    msg = body.get("message") or {}
    if msg.get("voice") or msg.get("audio"):
        from app.bot import content_kk as KK
        from app.bot import content_ru as RU

        session = await store.get_session(chat_id)
        lang = session.lang or "kk"
        c = KK if lang == "kk" else RU
        await tg.send_message(chat_id, c.FALLBACK_VOICE)
        return

    is_callback = "callback_query" in body
    text = text or ""

    session = await store.get_session(chat_id)
    if sender_name and not session.contact_name:
        session.contact_name = sender_name
    if text and not is_callback:
        if session.state not in ("choose_view", "choose_lang") or session.profile.get("lang_locked"):
            session.lang = detect_message_lang(text)
        await store.log_message(chat_id, "in", text)

    if text.strip() in ("/start", "/reset"):
        session = await store.reset_session(chat_id)
        if sender_name:
            session.contact_name = sender_name
        session.profile.pop("panel_message_id", None)

    if settings.is_together_configured and len(text) > 40:
        await tg.send_chat_action(chat_id, "typing")

    reply = await engine.handle(session, text, is_callback=is_callback)
    await store.save_session(session)

    if reply.stat:
        await store.bump_stat(reply.stat)

    force_new = text.strip() in ("/start", "/reset")
    await deliver_bot_reply(tg, session, chat_id, reply, body, force_new=force_new)
    await store.log_message(chat_id, "out", reply.text)

    if reply.notify_hr:
        await notify_hr(settings, tg, session, reply.notify_hr)
