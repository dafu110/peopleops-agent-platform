import json
from datetime import datetime, timezone
from typing import Any, Dict

from .config import get_settings
from .security import redact_pii


def write_audit_event(event_type: str, payload: Dict[str, Any]) -> None:
    settings = get_settings()
    settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    safe_payload = {
        key: redact_pii(value) if isinstance(value, str) else value
        for key, value in payload.items()
    }
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": safe_payload,
    }

    with settings.audit_log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
