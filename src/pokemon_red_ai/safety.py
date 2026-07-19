from __future__ import annotations

import re

PLACEHOLDER_USERNAMES = {"example", "runner", "user", "username"}
PRIVATE_HOME_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:/(?:Users|home)/(?P<posix>[A-Za-z0-9._-]+)/|"
    r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"
    r"(?P<windows>[A-Za-z0-9._-]+)[\\/])"
)
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"gh[opsu]_[A-Za-z0-9]{20,}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
}


def sensitive_text_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    for match in PRIVATE_HOME_PATH.finditer(text):
        username = (match.group("posix") or match.group("windows")).lower()
        if username not in PLACEHOLDER_USERNAMES:
            reasons.append("private home-directory path")
            break
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            reasons.append(label)
    return reasons
