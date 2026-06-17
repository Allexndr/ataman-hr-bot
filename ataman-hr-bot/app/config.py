from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_path() -> str:
    if os.environ.get("VERCEL") == "1":
        return "/tmp/ataman_hr.sqlite3"
    return "data/bot.sqlite3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    webhook_base_url: str = ""
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = "changeme"
    telegram_hr_chat_id: str = ""

    ai_provider: str = "together"
    together_api_key: str = ""
    together_model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"

    bot_timezone: str = "Asia/Almaty"
    cron_secret: str = ""
    admin_token: str = ""

    database_path: str = Field(default_factory=_default_database_path)

    fallback_attempts_max: int = 2

    @property
    def telegram_webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}/webhook/telegram"

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def is_together_configured(self) -> bool:
        return bool(self.together_api_key)

    @property
    def is_hr_notify_configured(self) -> bool:
        return bool(self.telegram_hr_chat_id and self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
