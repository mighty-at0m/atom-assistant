"""Gmail for ATOM: check, read, reply and send (sending always waits for a spoken yes).

One-time setup: put credentials.json (Google Cloud > OAuth client > Desktop app) beside atom.py,
then run:  python gmail_tools.py   (a browser opens, allow access, token.json is saved).
Both files are git-ignored. Needs: pip install google-api-python-client google-auth-oauthlib
"""

import base64
import re
from email.mime.text import MIMEText
from html import unescape
from pathlib import Path

HERE = Path(__file__).parent
CREDENTIALS = HERE / "credentials.json"
TOKEN = HERE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
LAST_LIST = []   # message ids from the last check, so "read number 2" works
_service = {"s": None}
STATUS = {"text": "unknown"}   # last gmail_status() result, in plain words


def _setup_message():
    """What is missing, and the exact step that fixes it — never a raw stack trace."""
    if not CREDENTIALS.exists():
        return (f"Gmail isn't connected: credentials.json is missing. Download it from Google Cloud "
                f"(APIs & Services > Credentials > OAuth client ID > Desktop app) and put it in "
                f"{HERE} beside atom.py, then run: python gmail_tools.py")
    return ("Gmail isn't connected yet: run python gmail_tools.py once and allow access in the "
            "browser that opens (that saves token.json beside atom.py).")


def _gmail(interactive=False):
    if _service["s"] is not None:
        return _service["s"]
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
        except Exception:
            print("Gmail: saved token.json could not be read; treating Gmail as not connected.")
            creds = None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError(_setup_message())
        from google_auth_oauthlib.flow import InstalledAppFlow
        if not CREDENTIALS.exists():
            raise RuntimeError(_setup_message())
        creds = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    _service["s"] = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _service["s"]


def _is_auth_error(error):
    status = getattr(getattr(error, "resp", None), "status", None)
    if status in (401, "401"):
        return True
    text = str(error).lower()
    return "invalid_grant" in text or "token has been expired or revoked" in text


def _run(operation):
    """Run a Gmail operation. If Google rejects the saved login (401 / expired or revoked
    token), drop the cached service, rebuild it once (which refreshes the token), and retry
    the operation once — instead of failing every call until ATOM is restarted."""
    try:
        return operation()
    except Exception as error:
        if not _is_auth_error(error):
            raise
        print("Gmail: login was rejected (401); reconnecting and retrying once.")
        _service["s"] = None
        return operation()


def gmail_status():
    """Plain connected / not-connected status, with the exact fix when it isn't. Never raises."""
    if not TOKEN.exists():
        STATUS["text"] = "not connected"
        return {"ok": False, "connected": False, "state": "not connected", "message": _setup_message()}
    try:
        profile = _run(lambda: _gmail().users().getProfile(userId="me").execute())
        STATUS["text"] = "connected"
        address = profile.get("emailAddress", "")
        return {"ok": True, "connected": True, "state": "connected",
                "message": f"Gmail is connected{' as ' + address if address else ''}."}
    except Exception as error:
        STATUS["text"] = "not connected"
        if _is_auth_error(error):
            reason = ("the saved login has expired or been revoked: run python gmail_tools.py "
                      "once and allow access again")
        else:
            reason = f"the check failed ({type(error).__name__}); check your internet connection, then ask me again"
        return {"ok": False, "connected": False, "state": "not connected",
                "message": f"Gmail isn't connected: {reason}."}


def _header(message, name):
    for header in message.get("payload", {}).get("headers", []):
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""


def _name(sender):
    return re.sub(r"\s*<.*?>", "", sender).strip('" ') or sender


def _check_email(count=5, unread_only=True):
    service = _gmail()
    query = "in:inbox category:primary" + (" is:unread" if unread_only else "")
    found = service.users().messages().list(userId="me", q=query, maxResults=max(1, min(int(count), 10))).execute()
    ids = [m["id"] for m in found.get("messages", [])]
    LAST_LIST[:] = ids
    if not ids:
        return {"ok": True, "message": "No new emails." if unread_only else "Your inbox is empty."}
    lines = []
    for i, message_id in enumerate(ids):
        message = service.users().messages().get(userId="me", id=message_id, format="metadata",
                                                 metadataHeaders=["From", "Subject"]).execute()
        lines.append(f"{i + 1}. From {_name(_header(message, 'From'))}: {_header(message, 'Subject')}")
    return {"ok": True, "message": f"{len(ids)} emails. " + " | ".join(lines)}


def check_email(count=5, unread_only=True):
    return _run(lambda: _check_email(count, unread_only))


def _body(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
    for part in payload.get("parts", []) or []:
        text = _body(part)
        if text:
            return text
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        html = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
        return unescape(re.sub(r"<[^>]+>", " ", html))
    return ""


def _pick(number):
    try:
        return LAST_LIST[int(number) - 1]
    except (ValueError, IndexError):
        return None


def _read_email(number=1):
    message_id = _pick(number)
    if not message_id:
        return {"ok": False, "message": "Check your email first, then tell me which number."}
    service = _gmail()
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
    text = re.sub(r"\s+", " ", _body(message["payload"])).strip()
    return {"ok": True, "message": f"From {_name(_header(message, 'From'))}, subject {_header(message, 'Subject')}: {text[:1400]}"}


def read_email(number=1):
    return _run(lambda: _read_email(number))


def _send_once(to, subject, body, thread_id=None, reply_to_id=None):
    mime = MIMEText(body)
    mime["to"], mime["subject"] = to, subject
    if reply_to_id:
        mime["In-Reply-To"] = mime["References"] = reply_to_id
    raw = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
    if thread_id:
        raw["threadId"] = thread_id
    _gmail().users().messages().send(userId="me", body=raw).execute()
    return {"ok": True, "message": f"Email sent to {_name(to)}."}


def _send(to, subject, body, thread_id=None, reply_to_id=None):
    return _run(lambda: _send_once(to, subject, body, thread_id, reply_to_id))


def _reply_email(number, text):
    from tools import hold_for_yes
    message_id = _pick(number)
    if not message_id:
        return {"ok": False, "message": "Check your email first, then tell me which one to reply to."}
    message = _gmail().users().messages().get(userId="me", id=message_id, format="metadata",
                                              metadataHeaders=["From", "Reply-To", "Subject", "Message-ID"]).execute()
    to = _header(message, "Reply-To") or _header(message, "From")
    subject = _header(message, "Subject")
    subject = subject if subject.lower().startswith("re:") else "Re: " + subject
    return hold_for_yes(f"reply to {_name(to)} saying: {text}",
                        lambda: _send(to, subject, text, message["threadId"], _header(message, "Message-ID")))


def reply_email(number, text):
    return _run(lambda: _reply_email(number, text))


def _address_for(name):
    if "@" in name:
        return name
    found = _gmail().users().messages().list(userId="me", q=f"from:{name} OR to:{name}", maxResults=1).execute()
    for item in found.get("messages", []):
        message = _gmail().users().messages().get(userId="me", id=item["id"], format="metadata",
                                                  metadataHeaders=["From", "To"]).execute()
        for field in ("From", "To"):
            value = _header(message, field)
            if name.lower() in value.lower():
                match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", value)
                if match:
                    return match.group(0)
    return None


def _send_email(to, subject, body):
    from tools import hold_for_yes
    address = _address_for(to)
    if not address:
        return {"ok": False, "message": f"I don't have an email address for {to}. Tell me the address."}
    return hold_for_yes(f"email {address} with subject {subject}, saying: {body}", lambda: _send(address, subject, body))


def send_email(to, subject, body):
    return _run(lambda: _send_email(to, subject, body))


if __name__ == "__main__":
    _gmail(interactive=True)
    print("Gmail connected.", check_email(3)["message"])
