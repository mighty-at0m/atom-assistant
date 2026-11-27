"""Text ATOM from your phone on Telegram. Same brain, same tools, same 'yes' confirmations.

Setup: put your bot token (from @BotFather) in telegram_token.txt. Start ATOM, send your bot /start,
it replies with your chat id: put that number in telegram_chat.txt and restart ATOM.
Only that chat is obeyed. Everyone else is ignored. Both files are git-ignored.
If OpenClaw also uses this bot, stop OpenClaw or make a new bot: only one program can read a bot at a time.
"""

import json
import os
import threading
import time
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


def forward(kind, text):
    """Called for reminders and notifications; sends them to your phone depending on ATOM_TELEGRAM_FORWARD."""
    if FORWARD == "all" or (FORWARD == "reminders" and kind == "reminder"):
        send("⏰ " + text if kind == "reminder" else "🔔 " + text)


def _handle(chat_id, text):
    import tools
    from fastbrain import ask
    allowed = _read(CHAT_FILE)
    if not allowed:
        send(f"Your chat id is {chat_id}. Put it in telegram_chat.txt beside atom.py and restart ATOM.", chat_id)
        return
    if str(chat_id) != allowed:
        return  # strangers get nothing
    if text.strip().lower() in ("/start", "/help"):
        send("ATOM online. Text me like you talk to me: 'battery?', 'screenshot', 'open chrome', 'remind me at 6pm to call mum'.", chat_id)
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
        return

    def loop():
        offset = 0
        STATUS["text"] = "connected" if _read(CHAT_FILE) else "needs chat id"
        while True:
            try:
                updates = _api("getUpdates", {"timeout": 30, "offset": offset})
                for update in updates.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message") or {}
                    if message.get("text"):
                        threading.Thread(target=_handle, args=(message["chat"]["id"], message["text"]), daemon=True).start()
                STATUS["text"] = "connected" if _read(CHAT_FILE) else "needs chat id"
            except Exception as error:
                STATUS["text"] = "reconnecting"
                print("Telegram:", type(error).__name__, str(error)[:100])
                time.sleep(10)
    threading.Thread(target=loop, daemon=True).start()
