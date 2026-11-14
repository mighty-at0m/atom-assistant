import pyttsx3
import threading

_engine = None
_engine_lock = threading.Lock()


def speak(text, rate=180):
    global _engine
    with _engine_lock:
        _engine = pyttsx3.init()          # uses the built-in Windows voices (offline)
        _engine.setProperty("rate", rate)
        _engine.say(text)
        _engine.runAndWait()
        _engine.stop()
        _engine = None


def stop_speaking():
    """Best-effort immediate cancellation from the ATOM window."""
    if _engine is not None:
        _engine.stop()


if __name__ == "__main__":
    from stt import record, to_wav_bytes, transcribe
    from brain import ask

    heard = transcribe(to_wav_bytes(record(5)))
    print("You said:", heard)
    print("Thinking...")
    reply = ask(heard)
    print("ATOM:", reply)
    speak(reply)
