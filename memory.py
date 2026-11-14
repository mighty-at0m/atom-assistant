"""Deliberate, local-only preferences saved by ATOM."""

import json
from pathlib import Path

MEMORY_FILE = Path(__file__).with_name("memory.json")


def _load():
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data):
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def remember(key, value):
    data = _load()
    data[key.strip().lower()] = value.strip()
    _save(data)
    return {"ok": True, "message": f"Remembered {key}."}


def forget(key):
    data = _load()
    if data.pop(key.strip().lower(), None) is None:
        return {"ok": False, "message": f"I do not have a memory named {key}."}
    _save(data)
    return {"ok": True, "message": f"Forgot {key}."}


def context():
    data = _load()
    return "\n".join(f"- {key}: {value}" for key, value in data.items()) or "No saved user preferences."
