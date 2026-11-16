"""Lower other apps' sound while ATOM listens and talks, then put it back.

Mode (ATOM_DUCK_MODE): "duck" (default) turns every other app down to ATOM_DUCK_LEVEL;
"pause" presses the media pause key, but only if something is actually playing; "off" does nothing.
ATOM's own voice is never lowered.
"""

import os

MODE = os.getenv("ATOM_DUCK_MODE", "duck").lower()
LEVEL = float(os.getenv("ATOM_DUCK_LEVEL", "0.15"))
_saved = {}          # session key -> original volume
_paused = {"done": False}


def _sessions():
    from pycaw.pycaw import AudioUtilities
    mine = os.getpid()
    for session in AudioUtilities.GetAllSessions():
        process = session.Process
        if process is None or process.pid == mine:
            continue
        name = process.name().lower()
        if name in {"python.exe", "pythonw.exe"}:  # never duck ATOM itself
            continue
        yield (process.pid, name), session


def _something_playing():
    try:
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
        speakers = AudioUtilities.GetSpeakers()
        device = getattr(speakers, "_dev", speakers)
        meter = device.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
        meter = meter.QueryInterface(IAudioMeterInformation)
        return meter.GetPeakValue() > 0.01
    except Exception:
        return False


def duck():
    if MODE == "off" or _saved or _paused["done"]:
        return
    try:
        if MODE == "pause":
            if _something_playing():
                from tools import media_control
                media_control("play_pause")
                _paused["done"] = True
            return
        for key, session in _sessions():
            volume = session.SimpleAudioVolume
            current = volume.GetMasterVolume()
            if current > LEVEL:
                _saved[key] = current
                volume.SetMasterVolume(LEVEL, None)
    except Exception as error:
        print("Ducking failed:", type(error).__name__)


def restore():
    try:
        if _paused["done"]:
            from tools import media_control
            media_control("play_pause")
            _paused["done"] = False
            return
        if not _saved:
            return
        for key, session in _sessions():
            if key in _saved:
                session.SimpleAudioVolume.SetMasterVolume(_saved[key], None)
    except Exception as error:
        print("Restoring volume failed:", type(error).__name__)
    finally:
        _saved.clear()
