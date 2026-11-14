# ATOM

A Jarvis-style voice assistant for Windows. Say "Hey Jarvis", speak, and ATOM answers out loud.

Pipeline: openWakeWord ("Hey Jarvis") -> SpeechBrain voice lock -> Groq Whisper -> Groq gpt-oss-20b with safe PC tools -> Windows speech.

## Setup (Windows, Python 3.10 or 3.11)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

1. Put your Groq key in `groq_key.txt` beside `atom.py`, or set `GROQ_API_KEY`. Never commit it.
2. Record your voice profile: `python enroll.py`
3. Test the brain without the mic: `python test_brain.py`
4. Run: `python atom.py` (or `pythonw atom.py` for no console window).

## Settings (environment variables)

| Variable | Default | What it does |
|---|---|---|
| `ATOM_WAKE_THRESHOLD` | 0.35 | Wake word sensitivity. Raise if it wakes by itself. |
| `ATOM_VOICE_THRESHOLD` | 0.20 | Voice lock strictness. Raise if others can use it. |
| `ATOM_DISABLE_VOICELOCK` | off | Set to 1 to skip the voice check while testing. |
| `ATOM_MAX_SECONDS` | 15 | Longest single request. |
| `ATOM_SILENCE_SECONDS` | 0.8 | Pause length that ends your request. |
| `ATOM_LIVE_PREVIEW` | off | Set to 1 for live transcript text (uses extra Groq requests). |

## Tools

open_application (any installed app), open_website, open_folder, search_files, get_battery_status, get_current_time, read_clipboard, take_screenshot, set_volume, remember_preference, forget_preference. Files and folders are limited to your user folder. Shutdown, restart, sleep, closing apps and deleting files (to the Recycle Bin) ask first. Say yes within 60 seconds to confirm. Sending and installing aren't available.
