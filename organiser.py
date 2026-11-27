"""Downloads auto-organiser: sorts new downloads into category folders, by itself.

Uses watchdog (in requirements.txt) for instant folder events when it is installed,
with a stdlib polling sweep underneath either way — the sweep is what enforces the
one-minute age rule, and it is also the fallback if watchdog is missing, so the
organiser never hard-crashes on a missing package. Default OFF — it starts only
when Mighty says "start the organiser". Safety rules:
- only files at least a minute old are moved (a file still arriving is left alone),
- partial downloads (.crdownload, .part, .tmp, .download, .opdownload) are never touched,
- files already inside a category folder are left alone,
- every move is appended to organiser_log.txt beside atom.py.
Categories match the organise.py from ATOM LABS' "PYTHON DOES IT IN SECONDS" series.
"""

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
LOG_FILE = HERE / "organiser_log.txt"
MIN_AGE_SECONDS = 60
PARTIAL_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".opdownload"}
POLL_SECONDS = 20

CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "Videos": [".mp4", ".mov", ".mkv"],
    "Documents": [".pdf", ".docx", ".txt", ".md"],
    "Audio": [".mp3", ".wav"],
    "Archives": [".zip", ".rar", ".7z"],
    "Code": [".py", ".js", ".html", ".css"],
}

STATE = {"running": False, "folder": None, "moved": 0}
_stop = threading.Event()
_sweep_lock = threading.Lock()


def downloads_folder():
    return Path.home() / "Downloads"


def category_for(file):
    ext = file.suffix.lower()
    for name, extensions in CATEGORIES.items():
        if ext in extensions:
            return name
    return "Other"


def is_partial(file):
    return file.suffix.lower() in PARTIAL_SUFFIXES or file.name.lower().endswith(".tmp")


def should_move(file, now=None):
    """Pure rule, kept separate so it can be tested: old enough, finished, a real file."""
    now = time.time() if now is None else now
    try:
        if not file.is_file() or is_partial(file):
            return False
        return now - file.stat().st_mtime >= MIN_AGE_SECONDS
    except OSError:
        return False


def _log(line):
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    except OSError:
        pass


def organise_once(folder=None):
    """One pass over the folder. Returns how many files were moved. Never raises."""
    folder = Path(folder) if folder else downloads_folder()
    moved = 0
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return 0
    for file in entries:
        if not should_move(file):
            continue
        dest_folder = folder / category_for(file)
        dest = dest_folder / file.name
        try:
            if dest.exists():
                dest = dest_folder / f"{file.stem}_{int(time.time())}{file.suffix}"
            dest_folder.mkdir(exist_ok=True)
            shutil.move(str(file), str(dest))
            moved += 1
            STATE["moved"] += 1
            _log(f"MOVE {file.name} -> {category_for(file)}/")
        except OSError as error:
            _log(f"SKIP {file.name}: {type(error).__name__}")
    return moved


def _sweep():
    with _sweep_lock:
        organise_once(STATE["folder"])


def _start_watchdog(folder):
    """Instant sweeps on file events, when watchdog is installed. None if it isn't."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("Organiser: watchdog not installed, using polling only.")
        return None

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            if not _stop.is_set():
                _sweep()

        def on_moved(self, event):
            if not _stop.is_set():
                _sweep()

    observer = Observer()
    observer.schedule(_Handler(), str(folder), recursive=False)
    observer.start()
    return observer


def _loop():
    observer = _start_watchdog(STATE["folder"])
    try:
        while not _stop.is_set():
            _sweep()
            _stop.wait(POLL_SECONDS)
    finally:
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=3)
            except Exception:
                pass
        STATE["running"] = False


def start_organiser(folder=None):
    if STATE["running"]:
        return {"ok": True, "message": f"The organiser is already running on {STATE['folder']}."}
    folder = Path(folder) if folder else downloads_folder()
    if not folder.is_dir():
        return {"ok": False, "message": f"There is no folder at {folder} to organise."}
    STATE.update({"running": True, "folder": folder, "moved": 0})
    _stop.clear()
    threading.Thread(target=_loop, daemon=True).start()
    return {"ok": True, "message": f"Organiser started on {folder.name}. New downloads will be sorted "
                                   "by type once they finish downloading. Say stop the organiser to end it."}


def stop_organiser():
    if not STATE["running"]:
        return {"ok": True, "message": "The organiser isn't running."}
    _stop.set()
    return {"ok": True, "message": f"Organiser stopping. It sorted {STATE['moved']} files this session."}


def organiser_status():
    if STATE["running"]:
        return {"ok": True, "message": f"The organiser is running on {STATE['folder']} and has sorted "
                                       f"{STATE['moved']} files this session."}
    return {"ok": True, "message": "The organiser is off. Say start the organiser to turn it on."}
