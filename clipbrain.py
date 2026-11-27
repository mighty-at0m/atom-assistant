"""Clipboard brain: a short local history of what Mighty copied, recallable by voice.

OFF by default — it only records while enabled ("start clipboard history"). While on, a
background thread polls the clipboard every 2 seconds and keeps the last 50 text entries
(with timestamps) in clipboard_history.json beside atom.py (git-ignored, never leaves
this PC). Note: it stores whatever text is copied, so don't enable it while copying
passwords — ATOM can't tell a password apart from any other text.
"""

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
FILE = HERE / "clipboard_history.json"
MAX_ENTRIES = 50
POLL_SECONDS = 2

STATE = {"on": False}
_stop = threading.Event()
_lock = threading.Lock()


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(entries):
    try:
        FILE.write_text(json.dumps(entries[-MAX_ENTRIES:], indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _read_clipboard_text():
    import tools
    result = tools.read_clipboard()
    return result["message"] if result.get("ok") else None


def _write_clipboard_text(text):
    import win32clipboard
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def record(text, when=None):
    """Add one entry (used by the poller, and directly testable)."""
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        entries = _load()
        if entries and entries[-1]["text"] == text:
            return
        entries.append({"at": (when or datetime.now()).isoformat(timespec="seconds"), "text": text[:4000]})
        _save(entries)


def _loop():
    while not _stop.is_set():
        try:
            text = _read_clipboard_text()
            if text:
                record(text)
        except Exception:
            pass
        _stop.wait(POLL_SECONDS)
    STATE["on"] = False


def start_history():
    if STATE["on"]:
        return {"ok": True, "message": "Clipboard history is already on."}
    STATE["on"] = True
    _stop.clear()
    threading.Thread(target=_loop, daemon=True).start()
    return {"ok": True, "message": "Clipboard history is on. I'll keep the last 50 things you copy, "
                                   "on this PC only. Careful: don't copy passwords while it's on."}


def stop_history():
    if not STATE["on"]:
        return {"ok": True, "message": "Clipboard history is already off."}
    _stop.set()
    return {"ok": True, "message": "Clipboard history is off. What I already saved stays in "
                                   "clipboard_history.json until you delete it."}


def find_entry(query=""):
    """Latest entry, or the latest one matching the query words (e.g. 'link', 'github')."""
    entries = _load()
    if not entries:
        return None
    words = [w for w in re.split(r"\W+", (query or "").lower())
             if w and w not in ("the", "that", "link", "from", "yesterday", "earlier", "copy", "copied", "what", "did", "i")]
    if not words:
        return entries[-1]
    for entry in reversed(entries):
        if any(word in entry["text"].lower() for word in words):
            return entry
    return None


def recall_clipboard(query=""):
    entry = find_entry(query)
    if entry is None:
        return {"ok": False, "message": "I don't have that in the clipboard history. "
                                        "It only holds text copied while history was on."}
    try:
        _write_clipboard_text(entry["text"])
        copied = " I've put it back on your clipboard."
    except Exception:
        copied = ""
    when = entry["at"].replace("T", " ")
    return {"ok": True, "message": f"From {when}: {entry['text'][:300]}{copied}"}
