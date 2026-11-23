"""Routines: one phrase runs several steps. Edit routines.json to make your own.

Each step is {"tool": "<tool name>", "args": {...}}. Special tool "say" just adds words.
"""

import json
from pathlib import Path

FILE = Path(__file__).with_name("routines.json")
DND = {"on": False}   # do not disturb: notifications are kept for later instead of read out

DEFAULTS = {
    "start my day": [
        {"tool": "say", "args": {"text": "Good morning sir."}},
        {"tool": "get_current_time", "args": {}},
        {"tool": "get_weather", "args": {}},
        {"tool": "list_reminders", "args": {}},
        {"tool": "check_email", "args": {"count": 3}},
        {"tool": "open_application", "args": {"name": "Visual Studio Code"}},
    ],
    "recording mode": [
        {"tool": "set_do_not_disturb", "args": {"on": True}},
        {"tool": "open_application", "args": {"name": "OBS Studio"}},
        {"tool": "say", "args": {"text": "Recording mode on. I'll keep notifications quiet until you say stop recording mode."}},
    ],
    "stop recording mode": [
        {"tool": "set_do_not_disturb", "args": {"on": False}},
        {"tool": "read_missed_notifications", "args": {}},
    ],
    "goodnight": [
        {"tool": "list_reminders", "args": {}},
        {"tool": "media_control", "args": {"action": "pause"}},
        {"tool": "say", "args": {"text": "Goodnight sir."}},
    ],
}


def _all():
    if not FILE.exists():
        FILE.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
    try:
        return {k.lower(): v for k, v in json.loads(FILE.read_text(encoding="utf-8")).items()}
    except json.JSONDecodeError:
        return DEFAULTS


def names():
    return list(_all())


def set_dnd(on):
    DND["on"] = bool(on)
    return {"ok": True, "message": "Do not disturb is on." if on else "Do not disturb is off."}


# Screen panels a routine opens (web UI only). Kept here, not in routines.json, so it also works
# with a routines.json written by an older version.
SCREEN = {"start my day": {"open": ["briefing"]}, "goodnight": {"close": ["all"]}}


def run_routine(name):
    from tools import run_tool
    routines = _all()
    key = name.lower().strip()
    found = routines.get(key) and key or next((k for k in routines if key in k or k in key), None)
    steps = routines.get(found) if found else None
    if steps is None:
        return {"ok": False, "message": "Your routines are: " + ", ".join(routines)}
    if found in SCREEN:
        try:
            import ui_bridge
            if hasattr(ui_bridge.get_ui(), "show_panels"):
                ui_bridge.show_panels(SCREEN[found].get("open"), SCREEN[found].get("close"))
        except Exception as error:
            print("Routine screen step failed:", type(error).__name__)
    said = []
    for step in steps:
        if step.get("tool") == "say":
            said.append(step["args"].get("text", ""))
            continue
        result = run_tool(step.get("tool", ""), step.get("args", {}))
        said.append(str(result.get("message", "")))
    return {"ok": True, "message": " ".join(s for s in said if s)[:1700]}
