from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings
from app.gmail_imap import Attachment, GmailImapClient
from app.state import AppState, load_state, save_state
from app.telegram import TelegramClient, truncate_caption

log = logging.getLogger(__name__)


def _parse_email_datetime(date_header: str | None, tz: ZoneInfo) -> datetime | None:
    """Parse email date header to datetime object in specified timezone."""
    if not date_header:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_header.strip())
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)
    except (TypeError, ValueError, OverflowError):
        return None


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".avif"}
)


def _is_image_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in _IMAGE_EXTENSIONS


def _is_image_attachment(att: Attachment) -> bool:
    ct = att.content_type.lower()
    if ct.startswith("image/"):
        return True
    return _is_image_file(att.filename)


def _format_caption(settings: Settings, mail) -> str:  # noqa: ANN001
    meta = mail.meta
    
    # Use email date instead of current time
    email_datetime = _parse_email_datetime(meta.date_header, settings.tz)
    if email_datetime:
        received = email_datetime.strftime("%Y-%m-%d %H:%M")
        tz_label = str(settings.tz)
        parts = [f"{received} ({tz_label})"]
    else:
        # Fallback to current time if email date parsing fails
        now_local = datetime.now(settings.tz)
        received = now_local.strftime("%Y-%m-%d %H:%M")
        tz_label = str(settings.tz)
        parts = [f"{received} ({tz_label})"]
    
    if meta.subject:
        parts.append(meta.subject)
    
    # Remove the separate date line since we now use email date as main timestamp
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

            to_photo: list[tuple[str, bytes]] = []
            to_document: list[tuple[str, bytes]] = []

            for att in mail.attachments:
                fn = att.filename
                payload = att.data
                if _is_image_attachment(att):
                    if len(payload) > settings.max_photo_bytes:
                        log.warning(
                            "Skip image %r on uid=%s: size=%s > MAX_PHOTO_BYTES=%s",
                            fn,
                            uid,
                            len(payload),
                            settings.max_photo_bytes,
                        )
                        continue
                    to_photo.append((fn, payload))
                    continue

                if not settings.send_document:
                    log.info(
                        "Skip non-image attachment %r on uid=%s (SEND_DOCUMENT is false)",
                        fn,
                        uid,
                    )
                    continue

                if len(payload) > settings.max_attachment_bytes:
                    log.warning(
                        "Skip document %r on uid=%s: size=%s > MAX_ATTACHMENT_BYTES=%s",
                        fn,
                        uid,
                        len(payload),
                        settings.max_attachment_bytes,
                    )
                    continue
                to_document.append((fn, payload))

            if not to_photo and not to_document:
                log.info(
                    "uid=%s: nothing to send after filters; leaving message UNSEEN",
                    uid,
                )
                continue

            for filename, payload in to_photo:
                log.info("Sending photo uid=%s file=%r bytes=%s", uid, filename, len(payload))
                tg.send_photo(filename=Path(filename).name, data=payload, caption=caption)

            for filename, payload in to_document:
                log.info("Sending document uid=%s file=%r bytes=%s", uid, filename, len(payload))
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
    log.info(
        "Starting poll every %ss; state_path=%s last_uid=%s SEND_DOCUMENT=%s max_photo_bytes=%s max_attachment_bytes=%s",
        settings.poll_seconds,
        settings.state_path,
        state.last_uid,
        settings.send_document,
        settings.max_photo_bytes,
        settings.max_attachment_bytes,
    )

    while True:
        try:
            state = process_once(settings, state)
        except Exception:  # noqa: BLE001 — keep service alive
            log.exception("Poll iteration failed")
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
