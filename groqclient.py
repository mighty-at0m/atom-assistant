"""One shared Groq client, created on first use so a missing key never crashes startup."""

import os
from pathlib import Path

from groq import Groq

KEY_FILE = Path(__file__).with_name("groq_key.txt")
_client = None


def get_client():
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key and KEY_FILE.exists():
            key = KEY_FILE.read_text(encoding="utf-8").strip()
        if not key:
            raise RuntimeError("No Groq key. Set GROQ_API_KEY or put groq_key.txt beside atom.py.")
        _client = Groq(api_key=key)
    return _client
