from __future__ import annotations

import email
import imaplib
import logging
import socket
import time
from dataclasses import dataclass
from email.message import Message
from email.policy import default as email_policy
from email.utils import parsedate_to_datetime
from typing import Iterator

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailMeta:
    uid: int
    message_id: str | None
    subject: str
    from_addr: str
    date_header: str | None


@dataclass(frozen=True)
class MailWithAttachments:
    meta: MailMeta
    attachments: tuple[tuple[str, bytes], ...]


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    decoded_parts = email.header.decode_header(value)
    chunks: list[str] = []
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            chunks.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            chunks.append(part)
    return "".join(chunks).strip()


def _parse_message(uid: int, raw_bytes: bytes) -> MailWithAttachments:
    msg: Message = email.message_from_bytes(raw_bytes, policy=email_policy)
    message_id = (msg.get("Message-ID") or "").strip() or None
    subject = _decode_header(msg.get("Subject"))
    from_addr = _decode_header(msg.get("From"))
    date_header = msg.get("Date")

    attachments: list[tuple[str, bytes]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue

        disp = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if filename:
            filename = _decode_header(filename)

        # Skip inline parts without a filename (typical cid: images).
        if disp == "inline" and not filename:
            continue

        if disp != "attachment" and not filename:
            continue

        if not filename:
            ext = part.get_content_subtype() or "bin"
            filename = f"attachment.{ext}"

        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if not isinstance(payload, (bytes, bytearray)):
            continue

        attachments.append((filename, bytes(payload)))

    meta = MailMeta(
        uid=uid,
        message_id=message_id,
        subject=subject,
        from_addr=from_addr,
        date_header=date_header,
    )
    return MailWithAttachments(meta=meta, attachments=tuple(attachments))


def _backoff_sleep(attempt: int) -> None:
    delay = min(60.0, 2.0**attempt)
    time.sleep(delay)


class GmailImapClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        mailbox: str,
        timeout: int,
        max_retries: int = 5,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._mailbox = mailbox
        self._timeout = timeout
        self._max_retries = max_retries
        self._imap: imaplib.IMAP4_SSL | None = None

    def _connect(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(self._host, self._port, timeout=self._timeout)
        imap.login(self._user, self._password)
        typ, _ = imap.select(self._mailbox, readonly=False)
        if typ != "OK":
            raise RuntimeError(f"IMAP SELECT {self._mailbox!r} failed: {typ}")
        return imap

    def __enter__(self) -> "GmailImapClient":
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                self._imap = self._connect()
                return self
            except (imaplib.IMAP4.error, OSError, socket.error) as exc:  # noqa: PERF203
                last_exc = exc
                log.warning("IMAP connect failed (attempt %s/%s): %s", attempt + 1, self._max_retries, exc)
                _backoff_sleep(attempt)
        assert last_exc is not None
        raise last_exc

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if self._imap is not None:
            try:
                self._imap.logout()
            except Exception:  # noqa: BLE001
                pass
            self._imap = None

    def iter_unseen_messages(self) -> Iterator[MailWithAttachments]:
        imap = self._imap
        if imap is None:
            raise RuntimeError("IMAP client is not connected")

        typ, data = imap.uid("SEARCH", None, "UNSEEN")
        if typ != "OK":
            raise RuntimeError(f"IMAP UID SEARCH UNSEEN failed: {typ}")

        chunk = data[0] if data else b""
        raw_ids = (chunk or b"").split() if chunk is not None else []
        if not raw_ids:
            return

        for raw_uid in raw_ids:
            uid = int(raw_uid)
            typ, fetched = imap.uid("FETCH", str(uid), "(RFC822)")
            if typ != "OK" or not fetched or not isinstance(fetched[0], tuple):
                log.warning("FETCH failed for uid=%s typ=%s", uid, typ)
                continue
            raw_bytes = fetched[0][1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                log.warning("Unexpected FETCH payload for uid=%s", uid)
                continue
            yield _parse_message(uid, bytes(raw_bytes))

    def mark_seen_uid(self, uid: int) -> None:
        imap = self._imap
        if imap is None:
            raise RuntimeError("IMAP client is not connected")
        typ, _ = imap.uid("STORE", str(uid), "+FLAGS", r"(\Seen)")
        if typ != "OK":
            raise RuntimeError(f"IMAP STORE +FLAGS \\Seen failed for uid={uid}: {typ}")


def parse_rfc2822_date(date_header: str | None) -> str:
    """Return a short diagnostic string for the message Date header (best-effort)."""
    if not date_header:
        return ""
    try:
        dt = parsedate_to_datetime(date_header.strip())
        if dt.tzinfo is None:
            return dt.isoformat(sep=" ", timespec="minutes")
        return dt.astimezone().isoformat(sep=" ", timespec="minutes")
    except (TypeError, ValueError, OverflowError):
        return date_header.strip()
