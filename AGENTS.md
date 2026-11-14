# ATOM voice assistant

Windows desktop voice assistant at `C:\Users\USER\atom-assistant`. Use `\.venv\Scripts\python.exe`; it has no local GPU/LLM requirement. Never open, print, log, or commit `groq_key.txt`.

## Status

- Working before the current, untested changes: “Hey Jarvis” wake detection, speaker verification, Groq transcription, the CustomTkinter UI, Groq fast chat/tool calling, and Windows SAPI speech.
- Wake threshold is `0.30`; the temporary `Wake peak` debug output was removed. A restart is required to load it.
- Voice lock default threshold is now `0.20` and can be tuned with `ATOM_VOICE_THRESHOLD`; observed valid scores in the 0.20–0.35 range were being rejected by the older `0.40` cutoff.
- Temporary latency testing override: set `ATOM_DISABLE_VOICELOCK=1` to skip the voice check while measuring reply latency or debugging the mic pipeline.
- Long-form capture is now enabled with no fixed 5-second cap, and the app can show partial transcript text while speech is still being captured; live-mic validation is still pending.
- Unverified in a real run: adaptive silence-based recording, GUI Cancel/Stop, one follow-up turn, memory context, and new safe tool handlers.
- Groq credentials are now resolved from `GROQ_API_KEY` before the local key file; no secret values are placed in UI or logs.
- Offline validation passed: all changed Python files parse, `tools.py` imports, and all eight tool schemas load. No live microphone, TTS, or Groq request was made.
- Voice lock is strict on every activation. Speaker verification and transcription run concurrently after recording, so Atom does not wait for them one after another.
- The concurrent strict-lock pipeline passed a syntax check but is untested on the real microphone and Groq connection.
- Wake listening now recovers from a stopped PortAudio stream instead of terminating the wake loop. End-of-speech delay is 0.65 seconds, with an eight-second capture cap.

## Changelog

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
- [ ] Add `.gitignore` before any Git use.
- [ ] Build a custom “Hey Atom” wake model later; do not rename the existing Jarvis model and claim it detects Atom.

## Rules

- Add new PC actions as explicit functions and schemas in `tools.py`; never pass model text to an arbitrary shell.
- Keep destructive/outward actions (delete, send, install, shutdown, restart, settings changes) unavailable until there is an explicit confirmation flow.
- Keep spoken replies short and plain: no markdown or emojis.
- After every change, update this file’s Status, Changelog, and To do sections concisely.
