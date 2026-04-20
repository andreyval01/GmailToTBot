from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.gmail_imap import GmailImapClient, parse_rfc2822_date
from app.state import AppState, load_state, save_state
from app.telegram import TelegramClient, truncate_caption

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _is_image_file(filename: str) -> bool:
    """Check if file is an image based on extension."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}
    return Path(filename).suffix.lower() in image_extensions


def _format_caption(settings: Settings, mail) -> str:  # noqa: ANN001
    now_local = datetime.now(settings.tz)
    received = now_local.strftime("%Y-%m-%d %H:%M")
    tz_label = str(settings.tz)
    parts = [f"{received} ({tz_label})"]
    meta = mail.meta
    if meta.subject:
        parts.append(meta.subject)
    date_parsed = parse_rfc2822_date(meta.date_header)
    if date_parsed:
        parts.append(f"Date: {date_parsed}")
    return truncate_caption(" — ".join(parts))


def process_once(settings: Settings, state: AppState) -> AppState:
    tg = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id, timeout=settings.telegram_timeout_seconds)

    with GmailImapClient(
        host=settings.gmail_imap_host,
        port=settings.gmail_imap_port,
        user=settings.gmail_email,
        password=settings.gmail_app_password,
        mailbox=settings.mailbox,
        timeout=settings.imap_timeout_seconds,
    ) as imap:
        for mail in imap.iter_unseen_messages():
            uid = mail.meta.uid
            if uid <= state.last_uid:
                log.info("Skip uid=%s (<= last_uid=%s)", uid, state.last_uid)
                continue

            if not mail.attachments:
                log.info("uid=%s has no attachments; marking read", uid)
                imap.mark_seen_uid(uid)
                state.last_uid = max(state.last_uid, uid)
                save_state(settings.state_path, state)
                continue

            caption = _format_caption(settings, mail)

            eligible: list[tuple[str, bytes]] = []
            for filename, payload in mail.attachments:
                if len(payload) > settings.max_attachment_bytes:
                    log.warning(
                        "Skip attachment %r on uid=%s: size=%s > max=%s",
                        filename,
                        uid,
                        len(payload),
                        settings.max_attachment_bytes,
                    )
                    continue
                eligible.append((filename, payload))

            if not eligible:
                log.info(
                    "uid=%s: no attachments under size limit; leaving message UNSEEN for manual handling",
                    uid,
                )
                continue

            for filename, payload in eligible:
                log.info("Sending uid=%s file=%r bytes=%s", uid, filename, len(payload))
                if _is_image_file(filename):
                    tg.send_photo(filename=Path(filename).name, data=payload, caption=caption)
                else:
                    tg.send_document(filename=Path(filename).name, data=payload, caption=caption)

            imap.mark_seen_uid(uid)
            state.last_uid = max(state.last_uid, uid)
            save_state(settings.state_path, state)
            log.info("Processed uid=%s last_uid=%s", uid, state.last_uid)

    return state


def main() -> None:
    _configure_logging()
    settings = Settings.from_env()
    state = load_state(settings.state_path)
    log.info("Starting poll every %ss; state_path=%s last_uid=%s", settings.poll_seconds, settings.state_path, state.last_uid)

    while True:
        try:
            state = process_once(settings, state)
        except Exception:  # noqa: BLE001 — keep service alive
            log.exception("Poll iteration failed")
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
