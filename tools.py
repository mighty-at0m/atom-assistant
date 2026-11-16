"""Small, explicit, non-destructive Windows tools available to ATOM."""

import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from datetime import datetime

HOME = Path.home().resolve()
SEARCH_SECONDS = 4
SCREENSHOT_DIR = HOME / "Pictures" / "ATOM"

from memory import forget, remember


# Spoken names -> what Windows "start" understands. "start" finds apps through the
# App Paths registry, so chrome and msedge work even though they are not on PATH.
APPLICATIONS = {
    "calculator": "calc",
    "notepad": "notepad",
    "file explorer": "explorer",
    "explorer": "explorer",
    "files": "explorer",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "terminal": "wt",
    "windows terminal": "wt",
    "command prompt": "cmd",
    "cmd": "cmd",
    "powershell": "powershell",
    "chrome": "chrome",
    "google chrome": "chrome",
    "chrome browser": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "edge browser": "msedge",
    "browser": "https://www.google.com",
    "default browser": "https://www.google.com",
    "web browser": "https://www.google.com",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "code": "code",
    "word": "winword",
    "microsoft word": "winword",
    "excel": "excel",
    "microsoft excel": "excel",
    "powerpoint": "powerpnt",
    "spotify": "spotify:",
    "camera": "microsoft.windows.camera:",
    "task manager": "taskmgr",
    "control panel": "control",
}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open any installed Windows app by name (Chrome, Edge, Spotify, VS Code, Notepad, Word, OBS...). Pre-approved: call it right away. Do not open a website instead unless this fails.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Application name."}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Open an existing folder inside the user's folder (e.g. Desktop, Downloads, Documents/Projects) in File Explorer.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "A Windows folder path."}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery_status",
            "description": "Read the laptop battery charge and estimated remaining time.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date and time from this PC.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "Read the current plain text from the Windows clipboard. Only use when the user explicitly asks about the clipboard.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find up to 10 file names containing the query inside the user's folders (default: the whole user folder; e.g. Desktop, Documents, Downloads). It does not read, change, or delete files.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "folder": {"type": "string", "description": "Optional folder, e.g. Desktop or Documents."}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_preference",
            "description": "Save a user preference locally, only after the user explicitly asks ATOM to remember it.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_preference",
            "description": "Remove a locally saved preference when the user explicitly asks ATOM to forget it.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a website or a web search in the default browser, e.g. site='netflix', site='youtube' with search='lofi music', site='spotify' with search='burna boy', or search='weather in Aba'. Pre-approved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site": {"type": "string", "description": "Site name or URL, e.g. netflix, youtube, github.com"},
                    "search": {"type": "string", "description": "Optional words to search for"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": ("Play a song, artist or playlist. Default app='youtube' (plays automatically). "
                            "Use app='spotify' only if the user says Spotify; it opens the search in the Spotify app."),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "e.g. 'Dave Sprinter' or 'Dave'"},
                    "app": {"type": "string", "enum": ["youtube", "spotify"]},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Pause, resume, skip to next or go to previous track in whatever is playing (Spotify, YouTube, any player).",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop"]}},
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_action",
            "description": ("Ask to do a risky action: shutdown, restart, sleep, close_app (target = app name) "
                            "or delete_file (target = file name or path; goes to the Recycle Bin). "
                            "Nothing happens until the user says yes. Speak the returned question exactly."),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["shutdown", "restart", "sleep", "close_app", "delete_file"]},
                    "target": {"type": "string"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot of the whole screen and save it in Pictures\\ATOM.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set the system speaker volume to a level from 0 to 100, or mute.",
            "parameters": {
                "type": "object",
                "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}},
                "required": ["level"],
                "additionalProperties": False,
            },
        },
    },
]


def _fn(name, description, properties=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required),
                       "additionalProperties": False}}}


TOOL_DEFINITIONS += [
    _fn("read_screen", "List the numbered buttons, links and boxes in the active window. Call this before clicking, and again after the screen changes."),
    _fn("look_at_screen", "Look at a screenshot and answer a question about what is showing (slower; use when read_screen isn't enough).",
        {"question": {"type": "string"}}),
    _fn("click", "Click something on screen: its number from read_screen, its exact name, or a short description like 'the green play button'. Risky buttons ask the user first.",
        {"target": {"type": "string"}, "double": {"type": "boolean"}, "right": {"type": "boolean"}}, ["target"]),
    _fn("type_text", "Type text into the focused box. Set press_enter to submit.",
        {"text": {"type": "string"}, "press_enter": {"type": "boolean"}}, ["text"]),
    _fn("press_keys", "Press a key or shortcut, e.g. 'enter', 'esc', 'space', 'ctrl+l', 'ctrl+t', 'alt+tab', 'ctrl+f'.",
        {"keys": {"type": "string"}}, ["keys"]),
    _fn("scroll", "Scroll the active window.",
        {"direction": {"type": "string", "enum": ["up", "down"]}, "amount": {"type": "integer"}}, ["direction"]),
]


def _screen(name):
    import screen
    return getattr(screen, name)


def _user_path(path):
    """Resolve a path and refuse anything outside the user's own folders."""
    raw = os.path.expandvars(os.path.expanduser(path.strip()))
    candidate = Path(raw)
    if not candidate.is_absolute():
        for base in (HOME, HOME / "Desktop", HOME / "Documents", HOME / "Downloads"):
            if (base / candidate).exists():
                candidate = base / candidate
                break
        else:
            candidate = HOME / candidate
    candidate = candidate.resolve()
    if candidate != HOME and HOME not in candidate.parents:
        return None
    return candidate


def _start(target):
    """Open an app, URI or URL the way the Run box does, without a console window."""
    subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=subprocess.CREATE_NO_WINDOW)


def _match_app(name):
    normalized = " ".join(name.lower().replace(".exe", "").split())
    for prefix in ("open ", "launch ", "the ", "my "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    if normalized in APPLICATIONS:
        return APPLICATIONS[normalized]
    for word in ("chrome", "edge", "notepad", "calculator", "explorer", "settings", "paint",
                 "terminal", "code", "word", "excel", "powerpoint", "spotify", "camera"):
        if word in normalized.split() or word == normalized:
            return APPLICATIONS.get(word)
    return None


START_MENUS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]


def _find_shortcut(name):
    """Find an installed app's Start Menu shortcut by name, e.g. 'photoshop' or 'obs'."""
    wanted = name.lower().replace(".exe", "").strip()
    best = None
    for root in START_MENUS:
        if not root.is_dir():
            continue
        for link in root.rglob("*.lnk"):
            title = link.stem.lower()
            if "uninstall" in title:
                continue
            if title == wanted:
                return str(link)
            if wanted in title and (best is None or len(title) < len(Path(best).stem)):
                best = str(link)
    return best


_START_APPS = []


def _start_apps():
    """Every app in the Start menu, Microsoft Store apps included: [(name, AppID)]."""
    if not _START_APPS:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            data = json.loads(result.stdout or "[]")
            data = data if isinstance(data, list) else [data]
            _START_APPS.extend((item["Name"], item["AppID"]) for item in data if item.get("AppID"))
        except (ValueError, KeyError):
            pass
    return _START_APPS


def _find_start_app(name):
    wanted = name.lower().replace(".exe", "").strip()
    best = None
    for title, app_id in _start_apps():
        lowered = title.lower()
        if "uninstall" in lowered:
            continue
        if lowered == wanted:
            return "shell:AppsFolder\\" + app_id
        if wanted in lowered and (best is None or len(title) < best[0]):
            best = (len(title), "shell:AppsFolder\\" + app_id)
    return best[1] if best else None


def open_application(name):
    target = _match_app(name)
    if target in {"chrome", "msedge", "spotify:", "winword", "excel", "powerpnt"} or not target:
        # Prefer the real installed shortcut; it always works when the app is installed.
        shortcut = _find_shortcut({"msedge": "microsoft edge", "spotify:": "spotify", "winword": "word",
                                   "powerpnt": "powerpoint", "chrome": "google chrome"}.get(target, target or name))
        if shortcut:
            target = shortcut
        else:
            store_app = _find_start_app({"msedge": "microsoft edge", "spotify:": "spotify", "winword": "word",
                                         "powerpnt": "powerpoint", "chrome": "google chrome"}.get(target, target or name))
            if store_app:
                target = store_app
    if not target:
        return {"ok": False, "message": f"I couldn't find an app called {name} on this PC."}
    try:
        _start(target)
        return {"ok": True, "message": f"Opened {name}."}
    except OSError as error:
        return {"ok": False, "message": f"Could not open {name}: {error}"}


SITES = {
    "youtube": "https://www.youtube.com", "netflix": "https://www.netflix.com",
    "google": "https://www.google.com", "gmail": "https://mail.google.com",
    "github": "https://github.com", "chatgpt": "https://chatgpt.com",
    "whatsapp": "https://web.whatsapp.com", "x": "https://x.com", "spotify": "https://open.spotify.com", "twitter": "https://x.com",
    "facebook": "https://www.facebook.com", "instagram": "https://www.instagram.com",
}


def open_website(site=None, search=None):
    import urllib.parse
    import webbrowser
    if search:
        site_key = (site or "").lower().strip()
        if site_key == "youtube":
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(search)
        elif site_key == "spotify":
            url = "https://open.spotify.com/search/" + urllib.parse.quote(search)
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(search)
    elif site:
        key = site.lower().strip().replace("www.", "")
        url = SITES.get(key) or SITES.get(key.split(".")[0])
        if not url:
            url = site if site.startswith("http") else ("https://" + site if "." in site else
                  "https://www.google.com/search?q=" + urllib.parse.quote_plus(site))
    else:
        url = "https://www.google.com"
    webbrowser.open(url)  # uses the default browser
    return {"ok": True, "message": "Opened it in your browser."}


def _first_youtube_video(query):
    import re
    import urllib.parse
    import urllib.request
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"})
    page = urllib.request.urlopen(request, timeout=8).read().decode("utf-8", "ignore")
    found = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', page)
    return found.group(1) if found else None


def play_music(query, app="youtube"):
    """Play a song or artist. YouTube starts playing by itself; Spotify opens the search in the app."""
    import urllib.parse
    import webbrowser
    if app == "spotify":
        if "liked" in query.lower():
            _start("spotify:collection:tracks")
            return {"ok": True, "message": "Opened your Liked Songs in Spotify. Next, read_screen or click the green Play button."}
        _start("spotify:search:" + urllib.parse.quote(query))
        return {"ok": True, "message": f"Opened the {query} search in Spotify. To play it, wait a moment, then click the top result's Play button."}
    try:
        video = _first_youtube_video(query + " official audio")
    except Exception:
        video = None
    if not video:
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query))
        return {"ok": True, "message": "I opened YouTube results for it. Pick one to play."}
    webbrowser.open("https://www.youtube.com/watch?v=" + video)
    return {"ok": True, "message": f"Playing {query} on YouTube."}


VK_MEDIA = {"play_pause": 0xB3, "pause": 0xB3, "play": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}


def media_control(action):
    key = VK_MEDIA.get(action)
    if key is None:
        return {"ok": False, "message": "I can play, pause, skip or go back."}
    ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key, 0, 2, 0)
    return {"ok": True, "message": {"next": "Skipped.", "previous": "Went back."}.get(action, "Done.")}


def open_folder(path):
    folder = _user_path(path)
    if folder is None:
        return {"ok": False, "message": "I can only open folders inside your user folder."}
    if not folder.is_dir():
        return {"ok": False, "message": f"That folder does not exist: {folder}"}
    try:
        os.startfile(str(folder))
        return {"ok": True, "message": f"Opened {folder}."}
    except OSError as error:
        return {"ok": False, "message": f"Could not open the folder: {error}"}


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def get_battery_status():
    """Instant Windows API read (the old PowerShell version took several seconds)."""
    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return {"ok": False, "message": "I couldn't read the battery."}
    if status.BatteryFlag == 128 or status.BatteryLifePercent == 255:
        return {"ok": False, "message": "No battery found. This may be a desktop PC."}
    detail = f"Battery is at {status.BatteryLifePercent}%"
    if status.ACLineStatus == 1:
        detail += " and plugged in"
    elif 0 < status.BatteryLifeTime < 86400:
        detail += f", about {status.BatteryLifeTime // 60} minutes left"
    return {"ok": True, "message": detail + "."}


def get_current_time():
    return {"ok": True, "message": datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p")}


def read_clipboard():
    import win32clipboard
    try:
        win32clipboard.OpenClipboard()
        text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        return {"ok": True, "message": text[:4000]}
    except Exception:
        return {"ok": False, "message": "The clipboard has no readable plain text."}
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


def search_files(query, folder):
    root = _user_path(folder or "~")
    if root is None:
        return {"ok": False, "message": "I can only search inside your user folder."}
    if not root.is_dir():
        return {"ok": False, "message": "That folder does not exist."}
    matches = []
    deadline = time.time() + SEARCH_SECONDS
    try:
        for path in root.rglob("*"):
            if time.time() > deadline:
                break
            if query.lower() in path.name.lower():
                matches.append(str(path))
                if len(matches) >= 10:
                    break
    except OSError as error:
        return {"ok": False, "message": f"Could not search that folder: {error}"}
    return {"ok": True, "message": "\n".join(matches) if matches else "No matching files found."}


def take_screenshot():
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"ok": False, "message": "Screenshots need Pillow. Run pip install pillow."}
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    ImageGrab.grab(all_screens=True).save(path)
    return {"ok": True, "message": f"Screenshot saved to Pictures, ATOM folder, as {path.name}."}


VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF


def _press(key, times):
    for _ in range(times):
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)


def set_volume(level):
    level = max(0, min(100, int(level)))
    _press(VK_VOLUME_DOWN, 50)  # each press is 2 percent, so this reaches 0
    if level == 0:
        return {"ok": True, "message": "Volume muted."}
    _press(VK_VOLUME_UP, round(level / 2))
    return {"ok": True, "message": f"Volume set to about {level} percent."}


# ---- Actions that need a spoken "yes" -------------------------------------
# The model can only *request* these. They wait in PENDING until the user says
# yes (checked in code by fastbrain.py, not by the model), and expire after 60 s.

PENDING = {}
CONFIRM_SECONDS = 60


def _power(command):
    subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)


def _close_app(name):
    target = _match_app(name) or name.lower().strip()
    exe = {"msedge": "msedge.exe", "chrome": "chrome.exe", "code": "Code.exe", "winword": "WINWORD.EXE",
           "excel": "EXCEL.EXE", "powerpnt": "POWERPNT.EXE", "spotify:": "Spotify.exe",
           "notepad": "notepad.exe", "calc": "CalculatorApp.exe", "mspaint": "mspaint.exe"}.get(target)
    exe = exe or (target if target.endswith(".exe") else target + ".exe")
    result = subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        return {"ok": False, "message": f"{name} doesn't seem to be running."}
    return {"ok": True, "message": f"Closed {name}."}


def _recycle(path):
    file = _user_path(path)
    if file is None or not file.exists():
        return {"ok": False, "message": "I can't find that file in your user folder."}
    script = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
              "$p = $env:ATOM_TARGET; "
              "if ((Get-Item -LiteralPath $p).PSIsContainer) "
              "{ [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($p, 'OnlyErrorDialogs', 'SendToRecycleBin') } "
              "else { [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p, 'OnlyErrorDialogs', 'SendToRecycleBin') }")
    env = dict(os.environ, ATOM_TARGET=str(file))
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env,
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        return {"ok": False, "message": "I couldn't delete it."}
    return {"ok": True, "message": f"Moved {file.name} to the Recycle Bin."}


RISKY_ACTIONS = {
    "shutdown": ("shut down the computer", lambda arg: _power(["shutdown", "/s", "/t", "5"])
                 or {"ok": True, "message": "Shutting down in 5 seconds."}),
    "restart": ("restart the computer", lambda arg: _power(["shutdown", "/r", "/t", "5"])
                or {"ok": True, "message": "Restarting in 5 seconds."}),
    "sleep": ("put the computer to sleep", lambda arg: _power(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
              or {"ok": True, "message": "Going to sleep."}),
    "close_app": ("close {arg}", _close_app),
    "delete_file": ("move {arg} to the Recycle Bin", _recycle),
}


def request_action(action, target=""):
    if action not in RISKY_ACTIONS:
        return {"ok": False, "message": f"I can't do {action}."}
    if action in {"close_app", "delete_file"} and not target:
        return {"ok": False, "message": "Tell me which one."}
    if action == "delete_file":
        file = _user_path(target)
        if file is None or not file.exists():
            found = search_files(Path(target).name, "~")["message"].splitlines()
            if len(found) == 1 and found[0] != "No matching files found.":
                target = found[0]
            else:
                return {"ok": False, "message": "I couldn't find exactly one file with that name."}
    label = RISKY_ACTIONS[action][0].format(arg=target)
    PENDING.clear()
    PENDING.update({"action": action, "target": target, "label": label, "at": time.time()})
    return {"ok": True, "needs_confirmation": True,
            "message": f"Should I {label}? Say yes to confirm."}


def hold_for_yes(label, run):
    """Park any risky step until the user says yes."""
    PENDING.clear()
    PENDING.update({"label": label, "run": run, "at": time.time()})
    return {"ok": True, "needs_confirmation": True, "message": f"Should I {label}? Say yes to confirm."}


def confirm_pending():
    """Run the waiting action. Called by fastbrain only after the user says yes."""
    if not PENDING or time.time() - PENDING["at"] > CONFIRM_SECONDS:
        PENDING.clear()
        return None
    job = dict(PENDING)
    PENDING.clear()
    print("Confirmed by voice:", job["label"])
    if "run" in job:
        return job["run"]()
    return RISKY_ACTIONS[job["action"]][1](job["target"])


def cancel_pending():
    had = bool(PENDING)
    PENDING.clear()
    return had


def run_tool(name, arguments):
    handlers = {
        "open_application": lambda: open_application(arguments["name"]),
        "open_folder": lambda: open_folder(arguments["path"]),
        "get_battery_status": get_battery_status,
        "get_current_time": get_current_time,
        "read_clipboard": read_clipboard,
        "search_files": lambda: search_files(arguments["query"], arguments.get("folder", "~")),
        "take_screenshot": take_screenshot,
        "open_website": lambda: open_website(arguments.get("site"), arguments.get("search")),
        "set_volume": lambda: set_volume(arguments["level"]),
        "read_screen": lambda: _screen("read_screen")(),
        "look_at_screen": lambda: _screen("look_at_screen")(arguments.get("question", "Describe what is on the screen.")),
        "click": lambda: _screen("click")(arguments["target"], arguments.get("double", False), arguments.get("right", False)),
        "type_text": lambda: _screen("type_text")(arguments["text"], arguments.get("press_enter", False)),
        "press_keys": lambda: _screen("press_keys")(arguments["keys"]),
        "scroll": lambda: _screen("scroll")(arguments["direction"], arguments.get("amount", 5)),
        "play_music": lambda: play_music(arguments["query"], arguments.get("app", "youtube")),
        "media_control": lambda: media_control(arguments["action"]),
        "request_action": lambda: request_action(arguments["action"], arguments.get("target", "")),
        "remember_preference": lambda: remember(arguments["key"], arguments["value"]),
        "forget_preference": lambda: forget(arguments["key"]),
    }
    if name not in handlers:
        return {"ok": False, "message": f"Tool {name} is not available."}
    try:
        return handlers[name]()
    except (KeyError, TypeError, ValueError) as error:
        return {"ok": False, "message": f"Invalid tool request: {error}"}
    except Exception as error:  # a broken tool must never crash ATOM
        return {"ok": False, "message": f"{name} failed: {type(error).__name__}: {str(error)[:150]}"}
