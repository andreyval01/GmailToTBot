from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class AppState:
    last_uid: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppState":
        return cls(last_uid=int(data.get("last_uid", 0) or 0))

    def to_dict(self) -> dict[str, Any]:
        return {"last_uid": self.last_uid}


def load_state(path: str | Path) -> AppState:
    p = Path(path)
    if not p.exists():
        return AppState()
    try:
        raw = p.read_text(encoding="utf-8")
        return AppState.from_dict(json.loads(raw) if raw.strip() else {})
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read state at %s (%s); starting fresh", p, exc)
        return AppState()


def save_state(path: str | Path, state: AppState) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
