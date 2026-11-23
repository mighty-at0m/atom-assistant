"""Send WhatsApp messages through the WhatsApp Desktop app (no unofficial APIs, so no ban risk).

Most reliable: put numbers in contacts.json (git-ignored), e.g. {"navis": "2348012345678"}.
Without a number, ATOM searches the chat by name and checks the right chat is open before typing.
Every send is confirmed by voice first (tools.hold_for_yes).
"""

import json
import os
import time
import urllib.parse
from pathlib import Path

CONTACTS = Path(__file__).with_name("contacts.json")


def _contacts():
    try:
        return {k.lower(): v for k, v in json.loads(CONTACTS.read_text(encoding="utf-8")).items()}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_contact(name, phone):
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]  # Nigerian local number -> international
    if len(digits) < 10:
        return {"ok": False, "message": "That number looks too short."}
    data = _contacts()
    data[name.lower()] = digits
    CONTACTS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True, "message": f"Saved {name}'s number."}


def _focus_whatsapp():
    try:
        import win32gui
        import win32con
        found = []
        win32gui.EnumWindows(lambda h, _: found.append(h) if "whatsapp" in win32gui.GetWindowText(h).lower() and win32gui.IsWindowVisible(h) else None, None)
        if found:
            win32gui.ShowWindow(found[0], win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(found[0])
            return True
    except Exception:
        pass
    return False


def _chat_is_open(name):
    """Ask vision (or the UI tree) whether the open chat is with this person."""
    import screen
    try:
        answer = screen.look_at_screen(
            f"In this WhatsApp window, is the chat that is currently OPEN (header at the top of the conversation) with '{name}'? Reply only yes or no.")
        return "yes" in answer.get("message", "").lower()[:10]
    except Exception:
        listing = screen.read_screen().get("message", "").lower()
        return name.lower() in listing


def send_whatsapp(contact, text):
    import pyautogui
    import screen
    phone = _contacts().get(contact.lower())
    if phone:
        os.startfile(f"whatsapp://send?phone={phone}&text={urllib.parse.quote(text)}")
        time.sleep(3.5)
        _focus_whatsapp()
        time.sleep(0.5)
        pyautogui.press("enter")
        return {"ok": True, "message": f"Sent to {contact} on WhatsApp."}
    os.startfile("whatsapp:")
    time.sleep(3.5)
    _focus_whatsapp()
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "f")        # chat search
    time.sleep(0.6)
    pyautogui.hotkey("ctrl", "a")
    screen.type_text(contact)
    time.sleep(1.5)
    pyautogui.press("down")
    pyautogui.press("enter")             # open the top result
    time.sleep(1.5)
    if not _chat_is_open(contact):
        pyautogui.press("esc")
        return {"ok": False, "message": f"I couldn't find a chat with {contact}, so I sent nothing. Save their number and I'll use that."}
    screen.type_text(text, press_enter=True)
    return {"ok": True, "message": f"Sent to {contact} on WhatsApp."}
