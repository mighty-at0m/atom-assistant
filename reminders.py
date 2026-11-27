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


APP_PROCESSES = {
    "vs code": "code.exe", "visual studio code": "code.exe", "code": "code.exe",
    "chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe",
    "microsoft edge": "msedge.exe", "obs": "obs64.exe", "obs studio": "obs64.exe",
    "spotify": "spotify.exe", "notepad": "notepad.exe", "word": "winword.exe",
    "excel": "excel.exe", "powerpoint": "powerpnt.exe", "whatsapp": "whatsapp.exe",
    "terminal": "windowsterminal.exe", "file explorer": "explorer.exe", "explorer": "explorer.exe",
}


def _process_names():
    """Running process image names (lowercase). psutil (in requirements.txt) first —
    it doesn't depend on tasklist's localised output; tasklist is the fallback."""
    try:
        import psutil
        return {proc.info["name"].lower() for proc in psutil.process_iter(["name"]) if proc.info.get("name")}
    except ImportError:
        pass
    except Exception:
        pass
    import csv
    import io
    import subprocess
    try:
        result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                                timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {row[0].lower() for row in csv.reader(io.StringIO(result.stdout)) if row}
    except Exception:
        return set()


def app_process(app):
    """Spoken app name -> the exe to watch for."""
    key = " ".join(str(app).lower().split())
    if key in APP_PROCESSES:
        return APP_PROCESSES[key]
    cleaned = "".join(ch for ch in key if ch.isalnum() or ch in " ._-").strip()
    return cleaned.replace(" ", "") + ".exe" if cleaned else ""


def due_app_reminders(items, running):
    """Reminders whose trigger app is running now. Pure, so it can be tested."""
    return [item for item in items if item.get("app") and app_process(item["app"]) in running]


def set_reminder(text, minutes=None, at=None, app=None):
    if app:
        with _lock:
            items = _load()
            items.append({"text": text.strip() or "your reminder", "due": 0, "app": str(app).strip()})
            _save(items)
        return {"ok": True, "message": f"Okay, I'll remind you to {text} when you open {app}."}
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


def _describe(item):
    if item.get("app"):
        return f"{item['text']} when you open {item['app']}"
    return f"{item['text']} at {_spoken(datetime.fromtimestamp(item['due']))}"


def list_reminders():
    items = _load()
    if not items:
        return {"ok": True, "message": "You have no reminders."}
    lines = [f"{i + 1}. {_describe(item)}" for i, item in enumerate(items)]
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
    """For the HUD: [(text, 'HH:MM AM today')]. App-trigger reminders have no clock time."""
    timed = [item for item in _load() if item.get("due")]
    return [(item["text"], _spoken(datetime.fromtimestamp(item["due"]))) for item in timed[:limit]]


def watch(announce):
    checks = {"apps_at": 0.0}

    def loop():
        while True:
            try:
                now = time.time()
                with _lock:
                    items = _load()
                    due = [item for item in items if item.get("due") and item["due"] <= now]
                    if due:
                        _save([item for item in items if item not in due])
                for item in due:
                    late = now - item["due"]
                    prefix = "Sir, a reminder" if late < 600 else "Sir, you missed a reminder while I was off"
                    announce(f"{prefix}: {item['text']}.")
                # App-trigger reminders: check what's running at most every 20 s, and fire
                # (then remove) a reminder the first time its app shows up.
                if now - checks["apps_at"] >= 20:
                    checks["apps_at"] = now
                    with _lock:
                        items = _load()
                    fired = due_app_reminders(items, _process_names())
                    for item in fired:
                        announce(f"Sir, a reminder for {item['app']}: {item['text']}.")
                    if fired:
                        with _lock:
                            _save([item for item in _load() if item not in fired])
                try:
                    import cleanup
                    cleanup.weekly_cleanup_if_enabled(announce)
                except Exception:
                    pass
            except Exception as error:
                print("Reminder error:", type(error).__name__)
            time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()
