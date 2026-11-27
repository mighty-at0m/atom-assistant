"""Weekly PC clean-up report: duplicates, biggest files, and wasted space.

The scanner is a plain tool ("clean-up report") plus an optional weekly run: when
cleanup_settings.json (beside atom.py, git-ignored) holds {"weekly": true}, the
reminders watch loop calls weekly_cleanup_if_enabled() and the report is announced
at most once every 7 days. Read-only: it never deletes or moves anything.
"""

import hashlib
import json
import time
from pathlib import Path

HERE = Path(__file__).parent
SETTINGS_FILE = HERE / "cleanup_settings.json"
WEEK_SECONDS = 7 * 24 * 3600
MAX_FILES = 20000   # stop counting past this so a huge drive can't hang the report


def _settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_settings(data):
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def set_weekly_cleanup(on):
    data = _settings()
    data["weekly"] = bool(on)
    _save_settings(data)
    return {"ok": True, "message": "Weekly clean-up report is on. I'll report every Sunday-ish, once a week."
            if on else "Weekly clean-up report is off. You can still ask for a clean-up report any time."}


def _hash(file):
    digest = hashlib.md5()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mb(size):
    return f"{size / (1024 * 1024):.0f} MB" if size < 1024 ** 3 else f"{size / (1024 ** 3):.1f} GB"


def scan_folders(folders):
    """Walk the folders once: duplicates by content hash, and the largest files."""
    seen = {}
    duplicates = []          # (extra copy path, size)
    largest = []             # (size, path)
    counted = 0
    for folder in folders:
        try:
            paths = sorted(Path(folder).rglob("*"))
        except OSError:
            continue
        for path in paths:
            if counted >= MAX_FILES:
                break
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                counted += 1
                size = path.stat().st_size
                largest.append((size, path))
                if size == 0:
                    continue
                fingerprint = _hash(path)
            except OSError:
                continue
            if fingerprint in seen:
                duplicates.append((path, size))
            else:
                seen[fingerprint] = path
    largest.sort(reverse=True)
    return duplicates, largest[:5]


def default_folders():
    home = Path.home()
    return [folder for folder in (home / "Downloads", home / "Desktop", home / "Documents") if folder.is_dir()]


def cleanup_report(folders=None):
    folders = [Path(f) for f in folders] if folders else default_folders()
    if not folders:
        return {"ok": False, "message": "I couldn't find Downloads, Desktop or Documents to scan."}
    duplicates, largest = scan_folders(folders)
    wasted = sum(size for _, size in duplicates)
    parts = ["Clean-up report."]
    if duplicates:
        names = ", ".join(path.name for path, _ in duplicates[:3])
        parts.append(f"{len(duplicates)} duplicate files are wasting {_mb(wasted)} "
                     f"(for example {names}). Nothing was deleted; say the word and I'll list them all.")
    else:
        parts.append("No duplicate files found. Tidy work, sir.")
    if largest:
        big = "; ".join(f"{path.name} ({_mb(size)})" for size, path in largest[:3])
        parts.append(f"Biggest files: {big}.")
    return {"ok": True, "message": " ".join(parts)[:1700]}


def weekly_cleanup_if_enabled(announce):
    """Called by the reminders watch loop. Announces the report at most once a week,
    and only when the weekly flag is on. Cheap when off: one small file read."""
    try:
        data = _settings()
        if not data.get("weekly"):
            return
        if time.time() - float(data.get("last_run") or 0) < WEEK_SECONDS:
            return
        data["last_run"] = time.time()
        _save_settings(data)
        announce("Sir, your weekly " + cleanup_report()["message"])
    except Exception as error:
        print("Weekly clean-up failed:", type(error).__name__)
