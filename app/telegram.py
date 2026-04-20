from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str, *, timeout: int) -> None:
        self._session = requests.Session()
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id
        self._timeout = timeout

    def send_document(self, *, filename: str, data: bytes, caption: str, max_retries: int = 6) -> None:
        url = f"{self._base}/sendDocument"
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                files = {"document": (filename, data)}
                resp = self._session.post(
                    url,
                    data={"chat_id": self._chat_id, "caption": caption},
                    files=files,
                    timeout=self._timeout,
                )
                if resp.status_code == 429:
                    retry_after = float(resp.json().get("parameters", {}).get("retry_after", 5))
                    log.warning("Telegram 429; retrying after %.1fs", retry_after)
                    time.sleep(retry_after)
                    continue
                if 500 <= resp.status_code < 600:
                    delay = min(60.0, 2.0**attempt)
                    log.warning("Telegram %s; retry in %.1fs", resp.status_code, delay)
                    time.sleep(delay)
                    continue

                payload = resp.json()
                if not payload.get("ok"):
                    raise RuntimeError(f"Telegram sendDocument failed: {payload}")
                return
            except (requests.RequestException, OSError) as exc:
                last_exc = exc
                delay = min(60.0, 2.0**attempt)
                log.warning("Telegram request error (attempt %s/%s): %s", attempt + 1, max_retries, exc)
                time.sleep(delay)

        assert last_exc is not None
        raise last_exc


def truncate_caption(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"
