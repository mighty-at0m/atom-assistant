"""Phone bridge: ATOM <-> Mighty's phone, over the existing Telegram bot.

- send_to_phone(): send the latest screenshot, or a named file from the user folder,
  to Mighty's Telegram chat.
- Incoming (called from telegram_bot): a link sent by text is saved to saved_links.txt;
  a photo is downloaded into telegram_downloads/; a voice note is downloaded,
  transcribed with the same Groq STT the mic uses, and run through the brain as a
  command, exactly like a typed message.
- pc_status(): battery, disk and locked/unlocked, for "PC status" from anywhere.
"""

import re
import shutil
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
LINKS_FILE = HERE / "saved_links.txt"
DOWNLOADS_DIR = HERE / "telegram_downloads"
URL_RE = re.compile(r"https?://\S+")


def send_to_phone(name=""):
    import telegram_bot
    import tools
    if name:
        path = tools._user_path(name)
        if path is None or not path.is_file():
            found = tools.search_files(Path(name).name, "~")["message"].splitlines()
            path = tools._user_path(found[0]) if len(found) == 1 and found[0] != "No matching files found." else None
        if path is None or not path.is_file():
            return {"ok": False, "message": f"I couldn't find a file called {name} in your folders."}
    else:
        if not tools.LAST_SCREENSHOT.get("path"):
            shot = tools.take_screenshot()
            if not shot.get("ok"):
                return shot
        path = Path(tools.LAST_SCREENSHOT["path"])
    try:
        if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
            telegram_bot.send_photo(str(path), f"From ATOM: {path.name}")
        else:
            telegram_bot.send_document(str(path), f"From ATOM: {path.name}")
    except Exception as error:
        return {"ok": False, "message": f"Couldn't send it to your phone: {type(error).__name__}. "
                                        "Check Telegram is set up (telegram_token.txt and telegram_chat.txt)."}
    return {"ok": True, "message": f"Sent {path.name} to your phone on Telegram."}


def pc_status():
    import tools
    parts = ["PC status."]
    try:
        parts.append(tools.get_battery_status()["message"])
    except Exception:
        pass
    try:
        usage = shutil.disk_usage(str(Path.home()))
        parts.append(f"Disk: {usage.free / (1024 ** 3):.0f} GB free.")
    except Exception:
        pass
    parts.append(_lock_state())
    return {"ok": True, "message": " ".join(parts)}


def _lock_state():
    """Locked / unlocked on Windows via the input desktop; 'state unknown' elsewhere."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        handle = user32.OpenInputDesktop(0, False, 0x0001)
        if handle:
            user32.CloseDesktop(handle)
            return "The PC is unlocked."
        return "The PC is locked."
    except Exception:
        return "Lock state unknown."


# ---- Incoming from Telegram -------------------------------------------------

def save_link(text):
    urls = URL_RE.findall(text or "")
    if not urls:
        return None
    try:
        with LINKS_FILE.open("a", encoding="utf-8") as handle:
            for url in urls:
                handle.write(url.rstrip(").,") + "\n")
    except OSError:
        return None
    return urls[0]


def _download_file(file_id, suffix):
    """Telegram getFile -> download into telegram_downloads/. Returns the Path or None."""
    import telegram_bot
    result = telegram_bot._api("getFile", {"file_id": file_id}, timeout=15)
    file_path = (result.get("result") or {}).get("file_path")
    if not file_path:
        return None
    token = telegram_bot._read(telegram_bot.TOKEN_FILE)
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    name = Path(file_path).name or f"telegram_file{suffix}"
    if not Path(name).suffix:
        name += suffix
    target = DOWNLOADS_DIR / name
    with urllib.request.urlopen(url, timeout=30) as response:
        target.write_bytes(response.read())
    return target


def handle_photo(chat_id, message):
    import telegram_bot
    photos = message.get("photo") or []
    if not photos:
        return
    try:
        target = _download_file(photos[-1]["file_id"], ".jpg")
        if target:
            telegram_bot.send(f"Saved your photo to the PC as {target.name} in telegram_downloads.", chat_id)
        else:
            telegram_bot.send("I couldn't download that photo.", chat_id)
    except Exception as error:
        print("Telegram photo failed:", type(error).__name__)
        telegram_bot.send("I couldn't download that photo.", chat_id)


def handle_voice(chat_id, message):
    import telegram_bot
    voice = message.get("voice") or {}
    if not voice.get("file_id"):
        return
    try:
        target = _download_file(voice["file_id"], ".ogg")
        if target is None:
            telegram_bot.send("I couldn't download that voice note.", chat_id)
            return
        from groqclient import get_client
        with target.open("rb") as handle:
            result = get_client().audio.transcriptions.create(
                file=(target.name, handle), model="whisper-large-v3-turbo", language="en")
        text = (result.text or "").strip()
    except Exception as error:
        print("Telegram voice failed:", type(error).__name__)
        telegram_bot.send("I couldn't transcribe that voice note.", chat_id)
        return
    if not text:
        telegram_bot.send("I couldn't hear anything in that voice note.", chat_id)
        return
    telegram_bot._handle(chat_id, text)
