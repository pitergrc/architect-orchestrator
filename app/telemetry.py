from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, UTC

from .schemas import TelemetryEvent


DEFAULT_LOG = Path(os.getenv("LOG_PATH", "logs/events.jsonl"))


def log_event(event: TelemetryEvent, log_path: str | Path = DEFAULT_LOG) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event.event,
        "route": event.route,
        "payload": event.payload,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
