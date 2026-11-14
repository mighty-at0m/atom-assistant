"""Small, explicit, non-destructive Windows tools available to ATOM."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

import win32clipboard

from memory import forget, remember


APPLICATIONS = {
    "calculator": "calc.exe",
    "notepad": "notepad.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "settings": "ms-settings:",
    "paint": "mspaint.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "browser": "msedge.exe",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
}


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open one of ATOM's approved Windows applications.",
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
            "description": "Open an existing folder in File Explorer. This does not modify its contents.",
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
            "description": "Read the current plain text from the Windows clipboard.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find up to 10 matching file names in a specified existing folder. It does not read, change, or delete files.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "folder": {"type": "string"}},
                "required": ["query", "folder"],
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
]


def open_application(name):
    normalized = name.lower().strip()
    command = APPLICATIONS.get(normalized)
    if not command and normalized in {"vs code", "visual studio code", "vscode"}:
        command = shutil.which("code")
    if not command:
        return {"ok": False, "message": f"{name} is not an approved application yet."}
    try:
        if command.startswith("ms-settings:"):
            os.startfile(command)
        else:
            subprocess.Popen([command], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"ok": True, "message": f"Opened {name}."}
    except OSError as error:
        return {"ok": False, "message": f"Could not open {name}: {error}"}


def open_folder(path):
    folder = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    if not folder.is_dir():
        return {"ok": False, "message": f"That folder does not exist: {folder}"}
    try:
        os.startfile(str(folder))
        return {"ok": True, "message": f"Opened {folder}."}
    except OSError as error:
        return {"ok": False, "message": f"Could not open the folder: {error}"}


def get_battery_status():
    command = [
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining,BatteryStatus,EstimatedRunTime | ConvertTo-Json -Compress",
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    if result.returncode != 0 or not result.stdout.strip() or result.stdout.strip() == "null":
        return {"ok": False, "message": "No battery information is available. This may be a desktop PC."}
    data = json.loads(result.stdout)
    if isinstance(data, list):
        data = data[0]
    charge = data.get("EstimatedChargeRemaining")
    minutes = data.get("EstimatedRunTime")
    detail = f"Battery is at {charge}%" if charge is not None else "Battery charge is unavailable"
    if isinstance(minutes, int) and 0 < minutes < 1440:
        detail += f", with about {minutes} minutes remaining"
    return {"ok": True, "message": detail + "."}


def get_current_time():
    return {"ok": True, "message": datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p")}


def read_clipboard():
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
    root = Path(os.path.expandvars(os.path.expanduser(folder))).resolve()
    if not root.is_dir():
        return {"ok": False, "message": "That folder does not exist."}
    matches = []
    try:
        for path in root.rglob("*"):
            if query.lower() in path.name.lower():
                matches.append(str(path))
                if len(matches) >= 10:
                    break
    except OSError as error:
        return {"ok": False, "message": f"Could not search that folder: {error}"}
    return {"ok": True, "message": "\n".join(matches) if matches else "No matching files found."}


def run_tool(name, arguments):
    handlers = {
        "open_application": lambda: open_application(arguments["name"]),
        "open_folder": lambda: open_folder(arguments["path"]),
        "get_battery_status": get_battery_status,
        "get_current_time": get_current_time,
        "read_clipboard": read_clipboard,
        "search_files": lambda: search_files(arguments["query"], arguments["folder"]),
        "remember_preference": lambda: remember(arguments["key"], arguments["value"]),
        "forget_preference": lambda: forget(arguments["key"]),
    }
    if name not in handlers:
        return {"ok": False, "message": f"Tool {name} is not available."}
    try:
        return handlers[name]()
    except (KeyError, TypeError, ValueError) as error:
        return {"ok": False, "message": f"Invalid tool request: {error}"}
