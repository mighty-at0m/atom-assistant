"""Lets tools control the screen panels without importing the window.

atom.py calls set_ui(app) once. The web UI (ui_web.WebApp) has show_panels(); the classic
window does not, so panel commands there just say they need the web UI.
"""

import re

PANELS = ["chat", "news", "music", "inbox", "reminders", "markets"]
ALIASES = {
    "chat": "chat", "chats": "chat", "transcript": "chat", "conversation": "chat", "log": "chat",
    "news": "news", "headlines": "news",
    "live": "live", "tv": "live", "video": "live",
    "music": "music", "player": "music", "song": "music", "media": "music",
    "inbox": "inbox", "messages": "inbox", "notifications": "inbox", "message": "inbox",
    "reminders": "reminders", "reminder": "reminders", "today": "reminders", "schedule": "reminders",
    "markets": "markets", "market": "markets", "naira": "markets", "dollar": "markets", "chart": "markets",
    "rates": "markets", "rate": "markets", "exchange": "markets", "crypto": "markets", "bitcoin": "markets",
    "briefing": "briefing", "desk": "briefing", "dashboard": "briefing",
    "all": "all", "everything": "all", "panels": "all", "panel": None, "screen": None,
}
# Opening the briefing shows these together, laid out like the approved mockup.
BRIEFING = ["news", "markets", "chat", "reminders"]

_ui = {"app": None}


def set_ui(app):
    _ui["app"] = app


def get_ui():
    return _ui["app"]


def expand(names):
    """Spoken panel names -> canonical names. 'briefing' expands; 'all' stays 'all'; 'live' stays 'live'."""
    found = []
    for name in names or []:
        key = ALIASES.get(str(name).lower().strip(), str(name).lower().strip())
        if key == "briefing":
            found += BRIEFING
        elif key in PANELS or key in ("all", "live"):
            found.append(key)
    return list(dict.fromkeys(found))


def _spoken_list(names):
    names = [n for n in names if n != "live"]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def show_panels(open=None, close=None):
    """Tool handler. open/close are lists of panel names."""
    app = get_ui()
    if app is None or not hasattr(app, "show_panels"):
        return {"ok": False, "message": "Screen panels need the web UI. Start ATOM with ATOM_UI=web."}
    wanted = list(open or [])
    briefing = any(ALIASES.get(str(n).lower(), str(n).lower()) == "briefing" for n in wanted)
    to_open, to_close = expand(wanted), expand(close)
    if not to_open and not to_close:
        return {"ok": False, "message": "Panels I can show: " + ", ".join(PANELS) + ", briefing and live news."}
    app.show_panels(to_open, to_close, briefing=briefing)
    if "all" in to_close and not to_open:
        return {"ok": True, "message": "Closed everything."}
    parts = []
    if briefing:
        parts.append("Here's your briefing.")
    elif "live" in to_open:
        parts.append("Putting the live news on.")
    elif to_open:
        parts.append("Opening " + _spoken_list(to_open) + ".")
    if to_close:
        parts.append("Closed everything." if "all" in to_close else "Closed " + _spoken_list(to_close) + ".")
    return {"ok": True, "message": " ".join(parts)}


# ---- Fast path: plain panel commands are handled in code, no brain round trip -------------

OPEN_WORDS = {"open", "show", "display", "bring", "put", "pull", "launch", "start", "turn", "on"}
CLOSE_WORDS = {"close", "hide", "remove", "dismiss", "clear"}  # not "turn off": that may mean the music itself
FILLER = {"the", "my", "me", "and", "up", "please", "atom", "sir", "a", "panel", "panels", "screen",
          "on", "of", "to", "can", "you", "for", "window", "windows", "now", "just", "also", "both", "it",
          "with", "plus", "then", "board", "feed", "too"}
VAGUE = {"panel", "screen", None}


def parse_command(text):
    """'open chat and music' -> (['chat', 'music'], []). Returns None unless EVERY word is a
    panel verb, a panel name or filler, so 'open chrome' or 'open chatgpt' never match."""
    words = re.findall(r"[a-z]+", (text or "").lower())
    if not words or len(words) > 14:
        return None
    opened, closed, mode, saw_verb = [], [], None, False
    for word in words:
        if word in CLOSE_WORDS:
            mode, saw_verb = "close", True
        elif word in OPEN_WORDS and word not in ("on", "turn"):
            mode, saw_verb = "open", True
        elif word in ALIASES and ALIASES[word] not in VAGUE:
            (closed if mode == "close" else opened).append(word)
        elif word in FILLER or word in ("turn", "on"):
            continue
        else:
            return None
    if not saw_verb or not (opened or closed):
        return None
    return opened, closed
