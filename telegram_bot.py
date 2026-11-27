"""Text ATOM from your phone on Telegram. Same brain, same tools, same 'yes' confirmations.

Setup: put your bot token (from @BotFather) in telegram_token.txt. Start ATOM, send your bot /start,
it replies with your chat id: put that number in telegram_chat.txt (no restart needed: ATOM re-reads
telegram_chat.txt on every message, so just send another message afterwards).
Only that chat is obeyed. Everyone else is ignored. Both files are git-ignored.
If OpenClaw also uses this bot, stop OpenClaw or make a new bot: only one program can read a bot at a time.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).parent
TOKEN_FILE, CHAT_FILE = HERE / "telegram_token.txt", HERE / "telegram_chat.txt"
STATUS = {"text": "off"}
FORWARD = os.getenv("ATOM_TELEGRAM_FORWARD", "reminders")  # reminders | all | off


def _read(path):
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _api(method, params=None, timeout=40):
    url = f"https://api.telegram.org/bot{_read(TOKEN_FILE)}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(url, data=data, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def bot_status():
    """Plain token status: no token, invalid token, unverified (network), or ready.
    Never raises, and never prints the token itself."""
    if not _read(TOKEN_FILE):
        STATUS["text"] = "off"
        return {"ok": False, "state": "no token",
                "message": "Telegram is off: telegram_token.txt is missing or empty. Put the token "
                           "from @BotFather in telegram_token.txt beside atom.py."}
    try:
        result = _api("getMe", timeout=10)
    except urllib.error.HTTPError as error:
        if error.code in (401, 404):
            STATUS["text"] = "invalid token"
            return {"ok": False, "state": "invalid token",
                    "message": "Telegram rejected the bot token. Get a fresh token from @BotFather "
                               "and replace telegram_token.txt beside atom.py."}
        STATUS["text"] = "unverified"
        return {"ok": False, "state": "unverified",
                "message": f"Telegram didn't answer the token check (HTTP {error.code}); ATOM will keep trying."}
    except Exception as error:
        STATUS["text"] = "unverified"
        return {"ok": False, "state": "unverified",
                "message": f"Couldn't check the Telegram token ({type(error).__name__}); ATOM will keep trying."}
    if not result.get("ok"):
        STATUS["text"] = "invalid token"
        return {"ok": False, "state": "invalid token",
                "message": "Telegram rejected the bot token. Get a fresh token from @BotFather "
                           "and replace telegram_token.txt beside atom.py."}
    bot = result.get("result", {})
    name = f"@{bot['username']}" if bot.get("username") else "your bot"
    STATUS["text"] = "connected" if _read(CHAT_FILE) else "needs chat id"
    return {"ok": True, "state": STATUS["text"],
            "message": f"Telegram token is valid ({name})." + ("" if _read(CHAT_FILE) else
                       " Send the bot /start to get your chat id for telegram_chat.txt.")}


def send(text, chat_id=None):
    chat_id = chat_id or _read(CHAT_FILE)
    if not chat_id or not _read(TOKEN_FILE):
        return
    try:
        _api("sendMessage", {"chat_id": chat_id, "text": text[:4000]}, timeout=10)
    except Exception as error:
        print("Telegram send failed:", type(error).__name__)


def send_photo(path, caption="", chat_id=None):
    chat_id = chat_id or _read(CHAT_FILE)
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat_id), ("caption", caption)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"screen.png\"\r\n"
                 f"Content-Type: image/png\r\n\r\n".encode() + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(f"https://api.telegram.org/bot{_read(TOKEN_FILE)}/sendPhoto", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(request, timeout=30).read()


def send_document(path, caption="", chat_id=None):
    chat_id = chat_id or _read(CHAT_FILE)
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat_id), ("caption", caption)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{Path(path).name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(f"https://api.telegram.org/bot{_read(TOKEN_FILE)}/sendDocument", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(request, timeout=30).read()


def forward(kind, text):
    """Called for reminders and notifications; sends them to your phone depending on ATOM_TELEGRAM_FORWARD."""
    if FORWARD == "all" or (FORWARD == "reminders" and kind == "reminder"):
        send("⏰ " + text if kind == "reminder" else "🔔 " + text)


def _handle(chat_id, text):
    import tools
    from fastbrain import ask
    allowed = _read(CHAT_FILE)
    if not allowed:
        send(f"Your chat id is {chat_id}. Put it in telegram_chat.txt beside atom.py, then send me another message (no restart needed).", chat_id)
        return
    if str(chat_id) != allowed:
        return  # strangers get nothing
    if text.strip().lower() in ("/start", "/help"):
        send("ATOM online. Text me like you talk to me: 'battery?', 'screenshot', 'open chrome', 'remind me at 6pm to call mum'.", chat_id)
        return
    lowered = text.strip().lower()
    if lowered in ("pc status", "pc status?", "status of my pc", "how is my pc"):
        import phonebridge
        send(phonebridge.pc_status()["message"], chat_id)
        return
    if lowered.startswith(("http://", "https://")) and " " not in text.strip():
        import phonebridge
        saved = phonebridge.save_link(text)
        send(f"Saved that link to saved_links.txt on the PC: {saved}" if saved else "I couldn't save that link.", chat_id)
        return
    before = tools.LAST_SCREENSHOT.get("path")
    try:
        reply = ask(text)
    except Exception as error:
        print("Telegram ask failed:", type(error).__name__, str(error)[:120])
        reply = "Something went wrong with that. ATOM is still running; try again."
    send(reply, chat_id)
    after = tools.LAST_SCREENSHOT.get("path")
    if after and after != before:
        try:
            send_photo(after, "Your screen", chat_id)
        except Exception as error:
            send(f"Couldn't send the screenshot: {type(error).__name__}", chat_id)


def start():
    if not _read(TOKEN_FILE):
        STATUS["text"] = "off"
        print(bot_status()["message"])
        return

    def loop():
        offset = 0
        status = bot_status()
        print("Telegram:", status["message"])
        if status["state"] == "invalid token":
            return  # polling with a rejected token would fail forever; the message above says the fix
        STATUS["text"] = "connected" if _read(CHAT_FILE) else "needs chat id"
        while True:
            try:
                updates = _api("getUpdates", {"timeout": 30, "offset": offset})
                for update in updates.get("result", []):
                    # Advance the offset per update, inside its own try: one malformed or
                    # failing update is logged and skipped, never re-fetched forever while
                    # every later message waits behind it.
                    try:
                        offset = update["update_id"] + 1
                    except Exception:
                        print("Telegram: skipped a malformed update with no update_id.")
                        continue
                    try:
                        message = update.get("message") or {}
                        chat_id = message["chat"]["id"]
                        if not _read(CHAT_FILE) and (message.get("photo") or message.get("voice")):
                            send(f"Your chat id is {chat_id}. Put it in telegram_chat.txt beside atom.py, then send me another message (no restart needed).", chat_id)
                        elif str(chat_id) != _read(CHAT_FILE) and _read(CHAT_FILE):
                            pass  # strangers get nothing, media included
                        elif message.get("photo"):
                            import phonebridge
                            threading.Thread(target=phonebridge.handle_photo, args=(chat_id, message), daemon=True).start()
                        elif message.get("voice"):
                            import phonebridge
                            threading.Thread(target=phonebridge.handle_voice, args=(chat_id, message), daemon=True).start()
                        elif message.get("text"):
                            threading.Thread(target=_handle, args=(chat_id, message["text"]), daemon=True).start()
                    except Exception as error:
                        print("Telegram: skipped update", update.get("update_id"), ":", type(error).__name__, str(error)[:100])
                STATUS["text"] = "connected" if _read(CHAT_FILE) else "needs chat id"
            except Exception as error:
                STATUS["text"] = "reconnecting"
                print("Telegram:", type(error).__name__, str(error)[:100])
                time.sleep(10)
    threading.Thread(target=loop, daemon=True).start()
