"""ATOM's health check and self-update.

health_check(): one plain spoken summary built from the existing status functions
(Gmail, Telegram, OBS) plus internet, disk and battery. Every check is guarded, so the
summary always comes out, even half-broken — that is the point of it.

self_update(): if this folder is a git checkout with a remote, run `git pull --ff-only`
(with a timeout), say what changed, and ask for a restart. It never restarts ATOM itself.
"""

import shutil
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent


def _guard(fetch):
    try:
        return fetch()
    except Exception as error:
        return f"unknown ({type(error).__name__})"


def _internet():
    try:
        urllib.request.urlopen("https://www.google.com", timeout=5)
        return "internet is up"
    except Exception:
        return "no internet connection"


def _disk():
    usage = shutil.disk_usage(str(Path.home()))
    free_gb = usage.free / (1024 ** 3)
    return f"{free_gb:.0f} GB free on disk"


def health_check():
    import gmail_tools
    import obs_tools
    import telegram_bot
    import tools
    parts = [
        "Health check.",
        _guard(lambda: gmail_tools.gmail_status()["message"]),
        _guard(lambda: telegram_bot.bot_status()["message"]),
        _guard(lambda: obs_tools.obs_status()["message"]),
        _guard(lambda: tools.get_battery_status()["message"]),
        _guard(_internet) + ".",
        _guard(_disk) + ".",
    ]
    return {"ok": True, "message": " ".join(p for p in parts if p)[:1700]}


def _git(*args, timeout=30):
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True,
                          timeout=timeout)


def self_update():
    try:
        inside = _git("rev-parse", "--is-inside-work-tree", timeout=10)
        if inside.returncode != 0 or "true" not in inside.stdout:
            return {"ok": False, "message": "This copy of ATOM is not a git checkout, so I can't pull "
                                            "updates. Download the latest version from GitHub instead."}
        remote = _git("remote", timeout=10)
        if not remote.stdout.strip():
            return {"ok": False, "message": "This checkout has no git remote set, so there is nowhere "
                                            "to pull updates from."}
        before = _git("rev-parse", "--short", "HEAD", timeout=10).stdout.strip()
        pull = _git("pull", "--ff-only", timeout=60)
    except FileNotFoundError:
        return {"ok": False, "message": "Git is not installed on this PC, so I can't update myself."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "The update timed out. Check the internet and ask me again."}
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or "").strip().splitlines()
        return {"ok": False, "message": "The update didn't go through: "
                                        + (detail[-1][:150] if detail else "git pull failed.")}
    after = _git("rev-parse", "--short", "HEAD", timeout=10).stdout.strip()
    if before == after:
        return {"ok": True, "message": "ATOM is already up to date, sir."}
    try:
        log = _git("log", "--oneline", f"{before}..{after}", timeout=10).stdout.strip()
        names = "; ".join(line.split(" ", 1)[-1] for line in log.splitlines()[:3] if line)
    except Exception:
        names = ""
    return {"ok": True, "message": (f"Updated ATOM from {before} to {after}"
                                     + (f": {names}." if names else ".")
                                     + " Restart ATOM to use the new code.")}
