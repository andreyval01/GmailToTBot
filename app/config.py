from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    gmail_imap_host: str
    gmail_imap_port: int
    gmail_email: str
    gmail_app_password: str
    mailbox: str
    poll_seconds: int
    telegram_bot_token: str
    telegram_chat_id: str
    tz: ZoneInfo
    state_path: str
    send_document: bool
    max_photo_bytes: int
    max_attachment_bytes: int
    imap_timeout_seconds: int
    telegram_timeout_seconds: int

    @staticmethod
    def from_env() -> "Settings":
        tz_name = os.environ.get("TZ", "Europe/Moscow").strip() or "Europe/Moscow"
        try:
            tz = ZoneInfo(tz_name)
        except Exception as exc:  # noqa: BLE001 — surface bad TZ at startup
            raise ValueError(f"Invalid TZ={tz_name!r}: {exc}") from exc

        gmail_email = os.environ.get("GMAIL_EMAIL", "").strip()
        gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
        telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

        missing = [
            name
            for name, val in (
                ("GMAIL_EMAIL", gmail_email),
                ("GMAIL_APP_PASSWORD", gmail_app_password),
                ("TELEGRAM_BOT_TOKEN", telegram_bot_token),
                ("TELEGRAM_CHAT_ID", telegram_chat_id),
            )
            if not val
        ]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        return Settings(
            gmail_imap_host=os.environ.get("GMAIL_IMAP_HOST", "imap.gmail.com").strip(),
            gmail_imap_port=_env_int("GMAIL_IMAP_PORT", 993),
            gmail_email=gmail_email,
            gmail_app_password=gmail_app_password,
            mailbox=os.environ.get("MAILBOX", "INBOX").strip() or "INBOX",
            poll_seconds=max(5, _env_int("POLL_SECONDS", 60)),
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
            tz=tz,
            state_path=os.environ.get("STATE_PATH", "/data/state.json").strip(),
            send_document=_env_bool("SEND_DOCUMENT", False),
            max_photo_bytes=max(
                1024,
                _env_int("MAX_PHOTO_BYTES", 10 * 1024 * 1024),
            ),
            max_attachment_bytes=max(
                1024,
                _env_int(
                    "MAX_ATTACHMENT_BYTES",
                    49 * 1024 * 1024,
                ),
            ),
            imap_timeout_seconds=max(10, _env_int("IMAP_TIMEOUT_SECONDS", 120)),
            telegram_timeout_seconds=max(10, _env_int("TELEGRAM_TIMEOUT_SECONDS", 120)),
        )
