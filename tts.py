"""ATOM's voice.

Online: Microsoft's free neural voices through edge-tts (sounds human). Pick one with ATOM_VOICE:
  en-GB-RyanNeural (default, British, Jarvis-like), en-NG-AbeoNeural (Nigerian man),
  en-NG-EzinneNeural (Nigerian woman), en-US-GuyNeural, en-GB-SoniaNeural.
Offline or on any error: the built-in Windows voice (pyttsx3), so ATOM never goes silent.
ATOM_VOICE=windows always uses the built-in voice.
"""

import asyncio
import ctypes
import os
import tempfile
import threading
import time

VOICE = os.getenv("ATOM_VOICE", "en-GB-RyanNeural")
RATE = os.getenv("ATOM_VOICE_RATE", "+5%")

_engine = None
_engine_lock = threading.Lock()
_stop = threading.Event()
_alias = {"n": 0}


def _mci(command):
    buffer = ctypes.create_unicode_buffer(256)
    error = ctypes.windll.winmm.mciSendStringW(command, buffer, 255, 0)
    return error, buffer.value


def _neural_mp3(text):
    import edge_tts
    path = os.path.join(tempfile.gettempdir(), "atom_say_%d.mp3" % int(time.time() * 1000))

    async def make():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(path)
    asyncio.run(asyncio.wait_for(make(), timeout=12))
    return path


def _play_mp3(path):
    """Play an mp3 with Windows' own player (no extra packages). Returns early if stopped."""
    _alias["n"] += 1
    alias = "atomvoice%d" % _alias["n"]
    error, _ = _mci(f'open "{path}" type mpegvideo alias {alias}')
    if error:
        raise RuntimeError("MCI could not open the audio")
    try:
        _mci(f"play {alias}")
        while not _stop.is_set():
            _, mode = _mci(f"status {alias} mode")
            if mode != "playing":
                break
            time.sleep(0.05)
    finally:
        _mci(f"stop {alias}")
        _mci(f"close {alias}")
        try:
            os.remove(path)
        except OSError:
            pass


def _windows_voice(text, rate=180):
    global _engine
    import pyttsx3
    with _engine_lock:
        _engine = pyttsx3.init()          # built-in Windows voices (offline)
        _engine.setProperty("rate", rate)
        _engine.say(text)
        _engine.runAndWait()
        _engine.stop()
        _engine = None


def speak(text, rate=180):
    _stop.clear()
    if not text:
        return
    if VOICE.lower() != "windows":
        try:
            path = _neural_mp3(text)
            if _stop.is_set():
                return
            _play_mp3(path)
            return
        except Exception as error:
            print("Neural voice failed, using Windows voice:", type(error).__name__)
    if not _stop.is_set():
        _windows_voice(text, rate)


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
    """Cut ATOM off immediately (Stop button, 'hey atom', or a new request)."""
    _stop.set()
    if _engine is not None:
        try:
            _engine.stop()
        except Exception:
            pass


if __name__ == "__main__":
    speak("Good evening sir. All systems are online.")
