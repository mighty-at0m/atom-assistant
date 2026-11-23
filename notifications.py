"""Read Windows notifications (WhatsApp, Telegram, Gmail in Chrome, Phone Link...) so ATOM can announce them.

Needs: pip install winsdk   (or the winrt-* packages on Python 3.11+)
and Windows Settings > Privacy > Notifications > "Allow apps to access your notifications" ON.
Apps to announce: ATOM_NOTIFY_APPS (comma list, matched inside the app name).
Tip: link your Android phone with Phone Link, and ATOM can announce your phone's messages too.
"""

import asyncio
import os
import threading
import time
from collections import deque

APPS = [a.strip().lower() for a in os.getenv(
    "ATOM_NOTIFY_APPS", "whatsapp,telegram,phone link,your phone,mail,outlook,gmail,chrome,edge,instagram,messenger").split(",") if a.strip()]
RECENT = deque(maxlen=30)      # newest last: dicts with app, sender, text, at
LAST = {}                      # the newest announced message, for "reply to him"
STATUS = {"text": "off"}       # shown on the HUD
_seen = set()


def _imports():
    try:
        from winsdk.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
        from winsdk.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
    except ImportError:
        from winrt.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
        from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
    return UserNotificationListener, UserNotificationListenerAccessStatus, NotificationKinds, KnownNotificationBindings


def _enum(kind, name):
    return getattr(kind, name.upper(), None) or getattr(kind, name.lower(), None) or getattr(kind, name.title())


async def _fetch():
    Listener, Access, Kinds, Bindings = _imports()
    listener = Listener.current
    allowed = _enum(Access, "allowed")
    if listener.get_access_status() != allowed:
        if await listener.request_access_async() != allowed:
            raise PermissionError("notification access is off")
    found = []
    for item in await listener.get_notifications_async(_enum(Kinds, "toast")):
        try:
            app = item.app_info.display_info.display_name
        except Exception:
            app = "Unknown app"
        try:
            binding = item.notification.visual.get_binding(Bindings.toast_generic)
            texts = [t.text for t in binding.get_text_elements()] if binding else []
        except Exception:
            texts = []
        found.append((item.id, app, texts))
    return found


def _parse(app, texts):
    texts = [t.strip() for t in texts if t and t.strip()]
    if not texts:
        return None
    if len(texts) > 2 and " " not in texts[-1] and "." in texts[-1]:
        texts = texts[:-1]  # Chrome/Edge add the site name (mail.google.com) last
    sender = texts[0]
    body = " ".join(texts[1:]) or texts[0]
    return {"app": app.replace("Google Chrome", "Chrome"), "sender": sender, "text": body[:300], "at": time.time()}


def watch(announce, every=3):
    """Poll for new notifications; call announce(dict) for each new one from an allowed app."""
    def loop():
        asyncio.set_event_loop(asyncio.new_event_loop())
        first = True
        while True:
            try:
                items = asyncio.get_event_loop().run_until_complete(_fetch())
                STATUS["text"] = "on"
                for item_id, app, texts in items:
                    if item_id in _seen:
                        continue
                    _seen.add(item_id)
                    if first or not any(a in app.lower() for a in APPS):
                        continue  # don't read out what was already there when ATOM started
                    note = _parse(app, texts)
                    if note:
                        RECENT.append(note)
                        LAST.clear()
                        LAST.update(note)
                        announce(note)
                first = False
            except ImportError:
                STATUS["text"] = "needs winsdk"
                print("Notifications off: run  pip install winsdk")
                return
            except PermissionError:
                STATUS["text"] = "no access"
                print("Notifications off: Settings > Privacy > Notifications > allow apps to access notifications")
                time.sleep(30)
            except Exception as error:
                STATUS["text"] = "error"
                print("Notification error:", type(error).__name__, str(error)[:120])
                time.sleep(10)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


def spoken(note):
    app = note["app"]
    if "whatsapp" in app.lower() or "telegram" in app.lower():
        return f"Sir, {note['sender']} on {app} says: {note['text']}"
    return f"Sir, {app} notification from {note['sender']}: {note['text']}"


def read_missed(count=5):
    if not RECENT:
        return {"ok": True, "message": "No new notifications."}
    items = list(RECENT)[-int(count):]
    return {"ok": True, "message": " | ".join(f"{n['app']}, {n['sender']}: {n['text']}" for n in items)}


def context():
    """A line for the brain so 'reply to him' knows who 'him' is."""
    if not LAST or time.time() - LAST["at"] > 900:
        return ""
    return (f"Latest message ({int((time.time() - LAST['at']) // 60)} min ago): {LAST['app']} from "
            f"{LAST['sender']}: \"{LAST['text']}\". If the user says reply/tell him/her, reply to this sender with reply_message.")
