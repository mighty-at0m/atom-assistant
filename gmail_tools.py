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


def _gmail(interactive=False):
    if _service["s"] is not None:
        return _service["s"]
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("Gmail isn't connected. Run python gmail_tools.py once.")
        from google_auth_oauthlib.flow import InstalledAppFlow
        if not CREDENTIALS.exists():
            raise RuntimeError("Put credentials.json beside atom.py first.")
        creds = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    _service["s"] = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _service["s"]


def _header(message, name):
    for header in message.get("payload", {}).get("headers", []):
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""


def _name(sender):
    return re.sub(r"\s*<.*?>", "", sender).strip('" ') or sender


def check_email(count=5, unread_only=True):
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


def read_email(number=1):
    message_id = _pick(number)
    if not message_id:
        return {"ok": False, "message": "Check your email first, then tell me which number."}
    service = _gmail()
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}).execute()
    text = re.sub(r"\s+", " ", _body(message["payload"])).strip()
    return {"ok": True, "message": f"From {_name(_header(message, 'From'))}, subject {_header(message, 'Subject')}: {text[:1400]}"}


def _send(to, subject, body, thread_id=None, reply_to_id=None):
    mime = MIMEText(body)
    mime["to"], mime["subject"] = to, subject
    if reply_to_id:
        mime["In-Reply-To"] = mime["References"] = reply_to_id
    raw = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
    if thread_id:
        raw["threadId"] = thread_id
    _gmail().users().messages().send(userId="me", body=raw).execute()
    return {"ok": True, "message": f"Email sent to {_name(to)}."}


def reply_email(number, text):
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


def send_email(to, subject, body):
    from tools import hold_for_yes
    address = _address_for(to)
    if not address:
        return {"ok": False, "message": f"I don't have an email address for {to}. Tell me the address."}
    return hold_for_yes(f"email {address} with subject {subject}, saying: {body}", lambda: _send(address, subject, body))


if __name__ == "__main__":
    _gmail(interactive=True)
    print("Gmail connected.", check_email(3)["message"])
