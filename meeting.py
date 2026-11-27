"""Meeting mode: record a meeting in chunks, transcribe it, summarise it.

"Start meeting mode" begins a background loop: record until a pause, transcribe with
the usual STT, repeat. "Stop meeting mode" joins the transcript, asks the brain chain
for a summary + action points, saves everything to meeting_notes/meeting_<date>.md
beside atom.py (git-ignored), and returns the summary to be spoken.
Everything is guarded: no mic or no STT key means a plain spoken failure, not a crash.
"""

import threading
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
NOTES_DIR = HERE / "meeting_notes"

STATE = {"on": False, "chunks": [], "started": None}
_stop = threading.Event()
_lock = threading.Lock()


def _loop():
    import stt
    while not _stop.is_set():
        try:
            audio = stt.record_until_silence(_stop, wait_for_speech_seconds=20, max_seconds=120)
            if audio is None:
                if _stop.is_set():
                    break
                continue
            text = stt.transcribe(stt.to_wav_bytes(audio))
            if text:
                with _lock:
                    STATE["chunks"].append(text)
        except Exception as error:
            print("Meeting mode:", type(error).__name__, str(error)[:100])
            break
    STATE["on"] = False


def start_meeting():
    if STATE["on"]:
        return {"ok": True, "message": "Meeting mode is already on."}
    try:
        import stt  # noqa: F401  (fails fast here if the mic/STT stack is missing)
        from groqclient import get_client
        get_client()
    except Exception as error:
        return {"ok": False, "message": f"Meeting mode can't start: {type(error).__name__}. "
                                        "Check the microphone and the Groq key, then ask me again."}
    with _lock:
        STATE.update({"on": True, "chunks": [], "started": datetime.now()})
    _stop.clear()
    threading.Thread(target=_loop, daemon=True).start()
    return {"ok": True, "message": "Meeting mode on. I'm listening and taking notes. "
                                   "Say stop meeting mode when you're done."}


def _summarise(transcript):
    import brains
    messages = [
        {"role": "system", "content": "You summarise meetings for a voice assistant. Reply in plain "
                                      "spoken sentences, no markdown: first a two-sentence summary, "
                                      "then 'Action points:' followed by the action points in one line."},
        {"role": "user", "content": "Meeting transcript:\n" + transcript[:6000]},
    ]
    return brains.chat(messages, max_tokens=350).content.strip()


def stop_meeting():
    if not STATE["on"] and not STATE["chunks"]:
        return {"ok": True, "message": "Meeting mode isn't on."}
    _stop.set()
    STATE["on"] = False
    with _lock:
        chunks = list(STATE["chunks"])
        started = STATE["started"] or datetime.now()
    transcript = " ".join(chunks).strip()
    if not transcript:
        return {"ok": True, "message": "Meeting mode off. I didn't catch any speech to summarise."}
    try:
        summary = _summarise(transcript)
    except Exception as error:
        print("Meeting summary failed:", type(error).__name__)
        summary = "I saved the transcript, but couldn't summarise it just now."
    try:
        NOTES_DIR.mkdir(exist_ok=True)
        path = NOTES_DIR / started.strftime("meeting_%Y%m%d_%H%M.md")
        path.write_text(f"# Meeting {started.strftime('%d %B %Y, %I:%M %p')}\n\n"
                        f"## Summary\n{summary}\n\n## Transcript\n{transcript}\n", encoding="utf-8")
        saved = f" Notes saved as {path.name} in the meeting_notes folder."
    except OSError:
        saved = ""
    return {"ok": True, "message": ("Meeting summary: " + summary + saved)[:1700]}
