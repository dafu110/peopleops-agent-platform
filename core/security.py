import hashlib
import re
from typing import Dict, Iterable, List


PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact_pii(text: str) -> str:
    if not text:
        return ""

    redacted = PHONE_RE.sub("[手机号已脱敏]", text)
    redacted = EMAIL_RE.sub("[邮箱已脱敏]", redacted)
    redacted = ID_CARD_RE.sub("[身份证号已脱敏]", redacted)
    return redacted


def redact_messages(messages: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    return [
        {
            "role": message.get("role", ""),
            "content": redact_pii(str(message.get("content", ""))),
        }
        for message in messages
    ]


def verify_password(input_password: str, expected_password: str | None) -> bool:
    if not expected_password:
        return True
    return input_password == expected_password


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
