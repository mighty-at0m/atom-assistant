"""ATOM's eyes and hands: read the active window, look at the screen, click, type and scroll.

Layers, fastest first:
1. UI Automation reads the buttons, links and boxes Windows exposes for the active window.
2. Gemini vision looks at a screenshot when an element isn't in that list.
3. pyautogui moves the mouse and keyboard.
"""

import base64
import ctypes
import io
import json
import os
import time
import urllib.request
from pathlib import Path

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # real pixels, so clicks land where we aim
except Exception:
    pass

import pyautogui

pyautogui.FAILSAFE = True  # slam the mouse into a screen corner to stop ATOM
pyautogui.PAUSE = 0.05

GEMINI_MODEL = os.getenv("ATOM_GEMINI_MODEL", "gemini-flash-lite-latest")
KEY_FILE = Path(__file__).with_name("gemini_key.txt")
CLICKABLE = {"ButtonControl", "MenuItemControl", "ListItemControl", "HyperlinkControl", "TabItemControl",
             "EditControl", "CheckBoxControl", "TreeItemControl", "RadioButtonControl", "ComboBoxControl",
             "SplitButtonControl", "DataItemControl"}
RISKY_WORDS = ("send", "buy", "pay", "purchase", "order", "delete", "remove", "post", "submit",
               "uninstall", "transfer", "checkout", "sign out", "log out", "format")
MAX_ELEMENTS = 45
LAST_ELEMENTS = []  # [(number, name, kind, x, y)] from the latest read_screen


def _gemini_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    return key


def _screenshot_jpeg():
    from PIL import ImageGrab
    image = ImageGrab.grab()
    width, height = image.size
    image.thumbnail((1280, 1280))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=70)
    return buffer.getvalue(), width, height


def _gemini(prompt, want_json=False):
    key = _gemini_key()
    if not key:
        raise RuntimeError("No Gemini key. Put it in gemini_key.txt beside atom.py.")
    jpeg, width, height = _screenshot_jpeg()
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
        {"text": prompt}]}],
        "generationConfig": {"temperature": 0}}
    if want_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    reply = json.load(urllib.request.urlopen(request, timeout=30))
    text = reply["candidates"][0]["content"]["parts"][0]["text"]
    return text, width, height


def _risky(name):
    lowered = name.lower()
    return any(word in lowered for word in RISKY_WORDS)


# ---- 1. Read the active window -------------------------------------------

def read_screen():
    """List the clickable things in the active window, numbered, so the model can click by number."""
    import uiautomation as auto
    LAST_ELEMENTS.clear()
    with auto.UIAutomationInitializerInThread():
        window = auto.GetForegroundControl()
        if window is None:
            return {"ok": False, "message": "I can't see an active window."}
        window = window.GetTopLevelControl() or window
        title = window.Name or "Untitled window"
        seen = set()
        deadline = time.time() + 3
        for control, depth in auto.WalkControl(window, maxDepth=25):
            if time.time() > deadline or len(LAST_ELEMENTS) >= MAX_ELEMENTS:
                break
            try:
                kind = control.ControlTypeName
                name = (control.Name or "").strip()
                if kind not in CLICKABLE or not name or control.IsOffscreen:
                    continue
                rect = control.BoundingRectangle
                if rect.width() <= 2 or rect.height() <= 2:
                    continue
                key = (name, rect.xcenter() // 10, rect.ycenter() // 10)
                if key in seen:
                    continue
                seen.add(key)
                LAST_ELEMENTS.append((len(LAST_ELEMENTS) + 1, name[:50], kind.replace("Control", ""),
                                      rect.xcenter(), rect.ycenter()))
            except Exception:
                continue
    if not LAST_ELEMENTS:
        return {"ok": True, "message": f"Window: {title}. It exposes no readable buttons; use look_at_screen."}
    lines = [f"{n}. {name} ({kind})" for n, name, kind, x, y in LAST_ELEMENTS]
    return {"ok": True, "message": f"Window: {title}\n" + "\n".join(lines)}


# ---- 2. Look with vision ---------------------------------------------------

def look_at_screen(question="Describe what is on the screen."):
    try:
        text, _, _ = _gemini("You are the eyes of a voice assistant. Answer briefly in plain sentences. " + question)
        return {"ok": True, "message": text.strip()[:1200]}
    except Exception as error:
        return {"ok": False, "message": f"I couldn't look at the screen: {type(error).__name__}"}


def _find_with_vision(target):
    text, width, height = _gemini(
        f'Find this on the screenshot: "{target}". Reply only JSON {{"found": true, "x": <0-1000>, "y": <0-1000>}} '
        'giving its center as fractions of the image width and height times 1000, or {"found": false}.',
        want_json=True)
    data = json.loads(text)
    if not data.get("found"):
        return None
    return int(data["x"] / 1000 * width), int(data["y"] / 1000 * height)


# ---- 3. Act ------------------------------------------------------------------

def _do_click(x, y, double=False, right=False):
    if right:
        pyautogui.rightClick(x, y)
    elif double:
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.click(x, y)


def click(target, double=False, right=False, confirmed=False):
    """Click an element: a number from read_screen, its name, or a description for vision.

    Returns needs_confirmation for risky buttons (send, buy, delete...) unless confirmed.
    """
    target = str(target).strip()
    point = None
    label = target
    if target.isdigit():
        for n, name, kind, x, y in LAST_ELEMENTS:
            if n == int(target):
                point, label = (x, y), name
    else:
        lowered = target.lower()
        exact = [e for e in LAST_ELEMENTS if e[1].lower() == lowered]
        partial = [e for e in LAST_ELEMENTS if lowered in e[1].lower()]
        match = (exact or partial or [None])[0]
        if match:
            point, label = (match[3], match[4]), match[1]
    if point is None:
        try:
            point = _find_with_vision(target)
        except Exception as error:
            return {"ok": False, "message": f"I couldn't find {target}: {type(error).__name__}"}
        if point is None:
            return {"ok": False, "message": f"I can't see {target} on the screen."}
    if _risky(label) and not confirmed:
        from tools import hold_for_yes
        return hold_for_yes(f"click {label}", lambda: _clicked(point, label, double, right))
    return _clicked(point, label, double, right)


def _clicked(point, label, double, right):
    _do_click(point[0], point[1], double, right)
    time.sleep(0.6)
    return {"ok": True, "message": f"Clicked {label}."}


def type_text(text, press_enter=False):
    if any(ord(ch) > 127 for ch in text):
        # pyautogui can't type non-ASCII, so paste it instead
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.write(text, interval=0.01)
    if press_enter:
        pyautogui.press("enter")
    return {"ok": True, "message": "Typed it." + (" Pressed Enter." if press_enter else "")}


ALLOWED_KEYS = set(pyautogui.KEYBOARD_KEYS)


def press_keys(keys):
    """Press a key or shortcut like 'enter', 'ctrl+l', 'alt+tab', 'space'."""
    parts = [p.strip().lower() for p in keys.replace(" ", "").split("+") if p.strip()]
    parts = [{"control": "ctrl", "windows": "win", "escape": "esc", "return": "enter"}.get(p, p) for p in parts]
    if not parts or any(p not in ALLOWED_KEYS for p in parts):
        return {"ok": False, "message": f"I don't know the key {keys}."}
    if len(parts) == 1:
        pyautogui.press(parts[0])
    else:
        pyautogui.hotkey(*parts)
    time.sleep(0.4)
    return {"ok": True, "message": f"Pressed {keys}."}


def scroll(direction="down", amount=5):
    clicks = max(1, min(30, int(amount))) * 120
    pyautogui.scroll(-clicks if direction == "down" else clicks)
    return {"ok": True, "message": f"Scrolled {direction}."}
