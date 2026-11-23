"""Offline mode: when the internet is down, ATOM still understands basic commands.

Speech is recognised on this PC with the Vosk model already used for the wake word.
Handles: open <app>, time, battery, volume up/down/mute/<number>, pause/play/next/previous, screenshot,
and lock / what's on my reminders.
"""

import json
import re

_recognizer = {"model": None}


def transcribe_offline(audio_int16, rate=16000):
    from vosk import KaldiRecognizer
    import wake
    if _recognizer["model"] is None:
        import os
        from vosk import Model
        folder = os.path.join(wake.HERE, "models", wake.VOSK_NAME)
        if not os.path.isdir(folder):
            return ""  # the model downloads with the wake word on first online run
        _recognizer["model"] = Model(folder)
    recognizer = KaldiRecognizer(_recognizer["model"], rate)
    recognizer.AcceptWaveform(audio_int16.tobytes())
    return json.loads(recognizer.FinalResult()).get("text", "")


def handle(text):
    """Return a spoken reply for a basic command, or None if it needs the internet."""
    from tools import open_application, get_current_time, get_battery_status, set_volume, media_control, take_screenshot
    said = text.lower().strip()
    if not said:
        return None
    import ui_bridge
    command = ui_bridge.parse_command(said)
    if command and hasattr(ui_bridge.get_ui(), "show_panels"):
        return ui_bridge.show_panels(*command)["message"]
    if said.startswith(("open ", "launch ", "start ")):
        return open_application(said.split(" ", 1)[1])["message"]
    if "time" in said:
        return get_current_time()["message"]
    if "battery" in said:
        return get_battery_status()["message"]
    if "volume" in said:
        number = re.search(r"\d+", said)
        if number:
            return set_volume(int(number.group()))["message"]
        if "mute" in said:
            return set_volume(0)["message"]
        try:
            import pyautogui
            pyautogui.press("volumeup" if "up" in said or "increase" in said else "volumedown", presses=5)
            return "Done."
        except Exception:
            return None
    for word, action in (("pause", "pause"), ("resume", "play"), ("play", "play"), ("next", "next"),
                         ("skip", "next"), ("previous", "previous"), ("go back", "previous")):
        if word in said:
            return media_control(action)["message"]
    if "screenshot" in said:
        return take_screenshot()["message"]
    if "reminder" in said:
        from reminders import list_reminders
        return list_reminders()["message"]
    return None
