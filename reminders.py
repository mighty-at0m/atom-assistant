"""Reminders and timers that survive restarts (saved in reminders.json, git-ignored).

The app starts watch(announce) once; announce(text) is called when a reminder is due.
"""

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

FILE = Path(__file__).with_name("reminders.json")
_lock = threading.Lock()


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items):
    FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_time(at):
    """'18:30', '6pm', '6:15 pm', 'tomorrow 9am' -> datetime (next occurrence)."""
    text = at.lower().strip()
    tomorrow = "tomorrow" in text
    match = re.search(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    half = (match.group(3) or "").replace(".", "")
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    now = datetime.now()
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow:
        when += timedelta(days=1)
    elif when <= now:
        when += timedelta(days=1)
    return when


def _spoken(when):
    day = "today" if when.date() == datetime.now().date() else "tomorrow" if when.date() == (datetime.now() + timedelta(days=1)).date() else when.strftime("%A %d %B")
    return when.strftime("%I:%M %p").lstrip("0") + " " + day


def set_reminder(text, minutes=None, at=None):
    if minutes:
        when = datetime.now() + timedelta(minutes=float(minutes))
    elif at:
        when = _parse_time(at)
        if when is None:
            return {"ok": False, "message": "I didn't understand that time. Say something like 6pm or in 20 minutes."}
    else:
        return {"ok": False, "message": "When should I remind you?"}
    with _lock:
        items = _load()
        items.append({"text": text.strip() or "your reminder", "due": when.timestamp()})
        items.sort(key=lambda item: item["due"])
        _save(items)
    return {"ok": True, "message": f"Okay, I'll remind you to {text} at {_spoken(when)}."}


def list_reminders():
    items = _load()
    if not items:
        return {"ok": True, "message": "You have no reminders."}
    lines = [f"{i + 1}. {item['text']} at {_spoken(datetime.fromtimestamp(item['due']))}" for i, item in enumerate(items)]
    return {"ok": True, "message": "Reminders: " + "; ".join(lines)}


def cancel_reminder(which):
    """Cancel by number from list_reminders, by words in its text, or 'all'."""
    with _lock:
        items = _load()
        if str(which).lower() == "all":
            _save([])
            return {"ok": True, "message": f"Cancelled all {len(items)} reminders."}
        keep, gone = [], []
        for i, item in enumerate(items):
            if str(which) == str(i + 1) or str(which).lower() in item["text"].lower():
                gone.append(item)
            else:
                keep.append(item)
        if not gone:
            return {"ok": False, "message": "I couldn't find that reminder."}
        _save(keep)
    return {"ok": True, "message": "Cancelled: " + ", ".join(item["text"] for item in gone) + "."}


def upcoming(limit=5):
    """For the HUD: [(text, 'HH:MM AM today')]."""
    return [(item["text"], _spoken(datetime.fromtimestamp(item["due"]))) for item in _load()[:limit]]


def watch(announce):
    def loop():
        while True:
            try:
                now = time.time()
                with _lock:
                    items = _load()
                    due = [item for item in items if item["due"] <= now]
                    if due:
                        _save([item for item in items if item["due"] > now])
                for item in due:
                    late = now - item["due"]
                    prefix = "Sir, a reminder" if late < 600 else "Sir, you missed a reminder while I was off"
                    announce(f"{prefix}: {item['text']}.")
            except Exception as error:
                print("Reminder error:", type(error).__name__)
            time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()
