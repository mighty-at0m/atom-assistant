# ATOM voice assistant

Windows desktop voice assistant at `C:\Users\USER\atom-assistant`. Use `\.venv\Scripts\python.exe`; it has no local GPU/LLM requirement. Never open, print, log, or commit `groq_key.txt`.

## Status

- Working before the current, untested changes: “Hey Jarvis” wake detection, speaker verification, Groq transcription, the CustomTkinter UI, Groq fast chat/tool calling, and Windows SAPI speech.
- 2026-11-16: default wake model now prefers the trained local `hey_at_tom.onnx` file in the project root, with the old Jarvis model only as a fallback; the app and test banner both say “hey atom”.
- Wake threshold is `0.35` (code previously said 0.40 while this file said 0.30); override with `ATOM_WAKE_THRESHOLD`.
- Voice lock default threshold is now `0.20` and can be tuned with `ATOM_VOICE_THRESHOLD`; observed valid scores in the 0.20–0.35 range were being rejected by the older `0.40` cutoff.
- Temporary latency testing override: set `ATOM_DISABLE_VOICELOCK=1` to skip the voice check while measuring reply latency or debugging the mic pipeline.
- Capture ends after 0.8 s of silence, with a 15 s hard cap. Live preview is opt-in (`ATOM_LIVE_PREVIEW=1`) because it spends Groq requests.
- Unverified in a real run: adaptive silence-based recording, GUI Cancel/Stop, one follow-up turn, memory context, and new safe tool handlers.
- Groq credentials are now resolved from `GROQ_API_KEY` before the local key file; no secret values are placed in UI or logs.
- Offline validation passed: all changed Python files parse, `tools.py` imports, and all eight tool schemas load. No live microphone, TTS, or Groq request was made.
- Voice lock is strict on every activation. Speaker verification and transcription run concurrently after recording, so Atom does not wait for them one after another.
- The concurrent strict-lock pipeline passed a syntax check but is untested on the real microphone and Groq connection.
- Wake listening now recovers from a stopped PortAudio stream instead of terminating the wake loop.

## Changelog

- 2026-11-14 v7: `ducker.py` (new, pycaw): while ATOM is in a conversation every other app's audio session is turned down to 15% (ATOM_DUCK_LEVEL), and restored afterwards; ATOM's own python process is never ducked. ATOM_DUCK_MODE=pause pauses media only if the peak meter shows audio; off disables. Called from app.run_turn. The wake word itself still has to be heard over full-volume music.

- 2026-11-14 v6: `screen.py` (new): computer control. read_screen lists numbered clickable UI Automation elements of the active window; click by number/name, falling back to Gemini vision (`gemini-flash-lite-latest`, key in gemini_key.txt or GEMINI_API_KEY) for pointing; type_text, press_keys, scroll; risky clicks (send, buy, delete, post...) wait for a spoken yes via `tools.hold_for_yes`. `tools.py`: apps also found through Get-StartApps (Microsoft Store apps via shell:AppsFolder), Spotify Liked Songs via spotify:collection:tracks, a tool crash returns an error instead of crashing ATOM. `fastbrain.py`: up to 8 tool rounds, old screen lists pruned to save Groq tokens, Groq client retries rate limits. `app.py`: rewritten as an Iron Man HUD (animated arc-reactor canvas, captions, TALK/STOP/LOG, clock and battery), 3 follow-up turns, barge-in while thinking adds new words to the command, "Hey Jarvis" interrupts speech. `stt.py`: 1.3 s end-of-speech pause, 25 s cap, mic level callback, listen_for_barge_in. `wake.py`: PAUSE flag and wake_during. All logic stub-tested; untested on Windows.

- 2026-11-14: v4 confirmed on the laptop: apps open (Spotify opened). v5: `play_music(query, app)` plays the first YouTube result automatically (scrapes videoId from the results page) or opens a search in the Spotify app (spotify:search URI; Spotify can't autoplay without Premium + Web API). `media_control` sends media keys (play/pause, next, previous).

- 2026-11-14: Laptop still had the OLD open_application (Popen chrome.exe -> WinError 2), so fix 3 was only partly applied. Full overwrite bundle. `tools.py`: apps open via Start Menu shortcut search (any installed app by name), `request_action` for shutdown/restart/sleep/close_app/delete_file (Recycle Bin, user folder only) that waits in `PENDING` for 60 s. `fastbrain.py`: a spoken yes/no is matched in code (not by the model) to confirm or cancel; the tool log line now prints the result message. Spotify search via open.spotify.com.

- 2026-11-14: Live test: model asked permission for every action, Chrome/Edge would not open, no browser tool. `fastbrain.py`: tools are pre-approved, never ask for confirmation. `tools.py`: apps launch through `cmd /c start` (finds chrome/msedge through App Paths), more app names and fuzzy matching, new `open_website(site, search)` tool using the default browser. `app.py`: a failed voice lock on the follow-up turn ends quietly (it is usually noise).

- 2026-11-14: test_brain.py passed on the laptop (battery 10.1s, time 1.0s, notepad 0.8s, screenshot 2.4s) but refused "How do I open a bank account?". `fastbrain.py`: system prompt now tells the model to answer everyday questions. `tools.py`: battery reads GetSystemPowerStatus via ctypes (instant) instead of PowerShell, and says when plugged in.

- 2026-11-14: Hark review fixes (branch hark-fixes). `groqclient.py` new shared lazy Groq client. `stt.py`: 15 s hard cap, 0.8 s end-of-speech, noise-floor calibration, gives up after 6 s of no speech, live preview off by default (`ATOM_LIVE_PREVIEW=1`). `app.py`: full transcript always wins over the preview, 4 s wait on follow-up. `fastbrain.py`: final no-tools round so tool results get spoken, strips gpt-oss reasoning field when resending, friendly rate-limit and offline replies. `tools.py`: folder/search limited to the user folder with a 4 s search cap, clipboard only when asked, added take_screenshot and set_volume back. `voicelock.py`/`atom.py`: paths relative to the project so the shortcut works from anywhere. `wake.py`: threshold 0.35, `ATOM_WAKE_THRESHOLD` override. `.gitignore`: my_voice.npy, memory.json, models/. Added README.md, requirements.txt, test_brain.py.

- 2026-11-05: `voicelock.py` — lowered the default voice threshold from `0.40` to `0.20`, added `ATOM_VOICE_THRESHOLD` tuning, and added a temporary `ATOM_DISABLE_VOICELOCK` override for latency testing.
- 2026-11-05: `stt.py`, `app.py` — removed the fixed 5-second recording rule, enabled long-form capture until silence, and added a partial live transcription preview while you are still speaking.
- 2026-11-05: `enroll.py` — expanded to more varied enrollment phrases to improve the saved voice profile.
- 2026-11-04: `wake.py` — lowered “Hey Jarvis” detection threshold from 0.50 to 0.30 after measured scores; removed temporary peak-score logging.
- 2026-11-04: `fastbrain.py`, `tools.py`, `app.py` — replaced the default OpenClaw-only response path with Groq fast chat and a small safe-tool layer.
- 2026-11-04: `stt.py`, `app.py`, `tts.py` — added adaptive recording and a Cancel/Stop UI path; awaiting end-to-end testing.
- 2026-11-04: `memory.py`, `fastbrain.py`, `tools.py` — added opt-in local-memory foundations and requested tool schemas; tool handlers still need verification/implementation.
- 2026-11-04: `AGENTS.md` — added project continuity instructions and accurate status tracking.
- 2026-11-04: `tools.py` — implemented bounded, read-only clipboard and file-search handlers plus explicit remember/forget dispatch.
- 2026-11-04: `app.py` — added a single short follow-up listening turn after a spoken reply, so a brief exchange needs only one wake word.
- 2026-11-04: `stt.py`, `app.py` — made key lookup independent of the launch folder and reduced UI/log error detail to avoid leaking request or credential data.
- 2026-11-04: validation — parsed changed modules and loaded safe tool definitions without contacting Groq or reading the local key file.
- 2026-11-04: `app.py`, `atom.py` — added a five-minute trusted voice session to avoid repeated speaker checks; made cancellation safe without voice verification; corrected the stale fixed-duration console message.
- 2026-11-04: `app.py` — removed the trusted-session and cancellation bypass after security review; runs speaker verification and transcription concurrently for every request.
- 2026-11-04: validation — parsed the concurrent voice pipeline without starting audio, transcription, or the speaker model.
- 2026-11-04: `wake.py`, `stt.py` — made microphone stream handoffs recoverable and reduced command end-of-speech latency; real-device verification remains required.

## To do

- [x] Replace fixed five-second capture with adaptive capture (needs real-device test).
- [x] Add visible Cancel/Stop control (needs real-device test).
- [x] Complete safe handlers for clipboard, file search, and explicit remember/forget tools (needs real-world testing).
- [x] Add one short no-wake follow-up turn after a response (needs real-device test).
- [ ] Test normal chat, battery tool call, voice lock, cancellation, long-form capture, live transcript preview, and one follow-up turn on the real microphone after the threshold fix.
- [x] Re-enroll the voice profile with more varied recordings to improve the saved voice embedding.
- [ ] Measure first-turn latency and rejection scores after concurrent verification; tune the voice threshold only from those measurements.
- [ ] Decide whether to adopt a true streaming voice provider for call-like response latency; Groq file transcription cannot start before end-of-speech.
- [x] Add `.gitignore` (now also covers my_voice.npy, memory.json, models/).
- [ ] Remove my_voice.npy and models/ from the public repo history (they were committed in 3765fe9).
- [ ] Live test v6: HUD renders, read_screen in Spotify/Chrome, vision click, barge-in, Hey Jarvis interrupt.
- [ ] Groq free tier is about 8K tokens/min; long screen tasks may hit it. Consider moving the brain to Gemini's OpenAI-compatible endpoint.
- [ ] Live test: TTS was silent during the 2026-11-14 run; check the speaker volume and output device.
- [ ] Run `python test_brain.py` and a live mic test on the hark-fixes code.
- [ ] Build a custom “Hey Atom” wake model later; do not rename the existing Jarvis model and claim it detects Atom.

## Rules

- Add new PC actions as explicit functions and schemas in `tools.py`; never pass model text to an arbitrary shell.
- Risky actions go through `request_action` + `PENDING` and only run after a spoken yes matched in code. Sending messages and installing software stay unavailable.
- Keep spoken replies short and plain: no markdown or emojis.
- After every change, update this file’s Status, Changelog, and To do sections concisely.
