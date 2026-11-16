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


def speak_async(text, rate=180):
    """Speak on a background thread and return it, so the caller can listen for an interruption."""
    def run():
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            speak(text, rate)
        except Exception as error:
            print("Speech error:", type(error).__name__)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


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
