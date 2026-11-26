"""Per-machine configuration: VS_* settings, read from the environment, then from .env.

The .env file (project root, excluded from Git) holds all the personal configuration: server,
paths, secret vault, Chrome profile. Documented template: .env.example and docs/configuration.md.
Priority: environment variable > .env > default value in the code.

Format: one KEY=value per line; # starts a comment; optional quotes; no variable expansion
(backslashes in Windows paths are kept as they are).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
_values: dict[str, str] | None = None


def parse_env(text: str) -> dict[str, str]:
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:  # trailing comment (outside quotes)
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def file_values() -> dict[str, str]:
    global _values
    if _values is None:
        _values = parse_env(ENV_FILE.read_text(encoding="utf-8-sig")) if ENV_FILE.exists() else {}
    return _values


def get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    value = file_values().get(name)
    return value if value else default
