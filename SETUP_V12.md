# ATOM v12 setup

Everything is optional except step 1. ATOM skips any feature that isn't set up yet.

## 1. Install (required)
```
cd C:\Users\USER\atom-assistant
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python atom.py
```

## 2. New voice
Works by itself (needs internet). Change voice: `setx ATOM_VOICE en-NG-AbeoNeural` (Nigerian man),
`en-NG-EzinneNeural` (Nigerian woman), `en-GB-RyanNeural` (default, British). `setx ATOM_VOICE windows` = old voice.
Test: `python tts.py`

## 3. Backup brains
Gemini already works with gemini_key.txt. Optional extras: cerebras_key.txt (cloud.cerebras.ai),
openrouter_key.txt (openrouter.ai). Order: Groq > Gemini > Cerebras > OpenRouter.

## 4. Notifications + WhatsApp replies
1. Windows Settings > Privacy > Notifications > turn ON "Allow apps to access your notifications".
2. Install WhatsApp Desktop from the Microsoft Store and keep its notifications on.
3. Optional (most reliable): say "save Navis's number 0803..." so ATOM opens his chat directly.
Phone Link (your Android) notifications are announced too.

## 5. Gmail
1. console.cloud.google.com > new project "ATOM" > enable Gmail API.
2. OAuth consent screen: External, add your Gmail as a test user, then Publish app (In production).
3. Credentials > Create > OAuth client ID > Desktop app > Download JSON > rename to credentials.json beside atom.py.
4. `python gmail_tools.py` > browser opens > Advanced > Go to ATOM > Allow.

## 6. Telegram (replaces the OpenClaw bot)
1. Stop OpenClaw's Telegram, or make a new bot with @BotFather.
2. Put the bot token in telegram_token.txt. Start ATOM, send /start to the bot.
3. Put the chat id it replies with in telegram_chat.txt and restart ATOM.

## 7. OBS
OBS > Tools > WebSocket Server Settings > Enable WebSocket server. If you set a password, put it in obs_password.txt.

## 8. Start with Windows
`python autostart.py on` (or `off`). Closing the window hides ATOM to the tray by the clock.

## Things to say
- "Remind me in 20 minutes to check the oven" / "what are my reminders"
- "What's the weather" / "news about tech" / "who won the match last night"
- "Check my email" / "read number 2" / "reply saying I'll send it tomorrow"
- "Text Navis I'm on my way" / after a message: "tell him I'll be there by 6pm"
- "Start my day" / "recording mode" / "stop recording mode" / "goodnight" (edit routines.json for your own)
- "Start recording" / "switch to my webcam scene"
- "Do not disturb on" / "what did I miss"
- "Go to sleep" / "thank you" = standby. 2 minutes of quiet = standby too.

## 9. The v13 screen (web UI)
ATOM now opens a full-window screen: the animated atom in the middle, and panels that fly in by voice.
```
pip install pywebview
python atom.py
```
- It uses Microsoft Edge WebView2, which Windows 10 usually already has. If the classic window opens instead and
  atom.log says "WebView2 Runtime not found", install the Evergreen runtime from
  https://developer.microsoft.com/microsoft-edge/webview2/ and start ATOM again.
- Old window instead: `setx ATOM_UI classic` (back to the new one: `setx ATOM_UI web`). New PowerShell window after setx.
- Live news channel: `setx ATOM_NEWS_CHANNEL arise` (default `channels`). The video only loads when you press ▶ or
  say "show live news"; closing the news panel stops it.
- Music panel shows the song from any player (Spotify, YouTube in Chrome...) when `winsdk` is installed (already in
  requirements). The buttons work either way.
- Debug the page (right-click > Inspect): `$env:ATOM_UI_DEBUG=1; python atom.py`.
- Keys: Space = talk, Esc = stop. Click the atom to talk. The "core" dock button closes every panel.

Things to say: "open chat and music", "show the news", "show live news", "show my desk" (briefing), "show the naira
chart", "hide chat", "close everything", "start my day" (also opens the briefing).
