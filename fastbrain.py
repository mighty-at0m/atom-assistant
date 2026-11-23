"""Fast conversational brain with a small, safe set of local PC tools."""

import json
import threading

import brains
from memory import context as memory_context
from tools import TOOL_DEFINITIONS, PENDING, cancel_pending, confirm_pending, run_tool

YES = {"yes", "yeah", "yep", "yes please", "do it", "go ahead", "confirm", "confirmed", "sure", "okay", "ok",
       "yes do it", "yes go ahead", "i approve", "approved", "proceed"}
NO = {"no", "nope", "cancel", "stop", "don't", "dont", "never mind", "no thanks"}

MODEL = "openai/gpt-oss-20b"
MAX_TOOL_ROUNDS = 8  # enough for look -> click -> look -> click tasks

SYSTEM = """You are ATOM, a concise voice assistant on a Windows laptop.
Reply in one to three short spoken sentences. Do not use markdown, lists, or emojis.
You are a helpful general assistant: answer everyday questions (money, school, tech, life advice, facts)
directly and practically from your own knowledge. Never refuse normal, harmless questions.
Use a tool only when it is needed to fulfil a real PC request. You may only use the tools provided.
Never claim to have performed an action unless its tool result confirms it.
Only save a memory when the user explicitly asks you to remember it. Memories stay on this PC.
Only read the clipboard when the user explicitly asks about it.
Every tool you have is pre-approved and safe: call it immediately when asked. Never ask the user
for permission or confirmation before opening apps, websites, folders, screenshots, or setting the volume.
For web searches or websites (YouTube, Netflix, Google), use open_website.
To play music use play_music (one call only, don't also open the app or a website); for pause, skip or resume use media_control.
Describe only what the tool results say happened.
To work inside an app (click buttons, open playlists, use a website): open it if needed, then read_screen,
then click by number, then read_screen again to check, and repeat until the job is done. Use press_keys for
shortcuts and type_text for typing. Use look_at_screen only when read_screen doesn't show what you need.
Don't narrate each step; after finishing, say in one short sentence what you did.
If an app fails to open, offer to open its website instead.
Shutting down, restarting, sleep, closing apps and deleting files go through request_action, which asks
the user to say yes; speak its question exactly and never claim it is done before then.
Call the user "sir" now and then, like Jarvis. Installing software is not available yet.
Messages: to send WhatsApp messages use reply_message; for email use check_email/read_email/reply_email/send_email.
Sending always waits for the user's spoken yes: speak the tool's question exactly. Never say a message was sent
until a tool result says so. When the user dictates a reply ("tell him I'll be there by 6"), write it naturally in
the first person as the user ("I'll be there by 6pm") and call reply_message once.
Reminders and timers: set_reminder. Weather: get_weather. News: get_news. Current facts: web_search.
OBS: obs_control. Routines like 'start my day' or 'recording mode': run_routine.
For creator help ("titles for this video", "explain this error on my screen"), use look_at_screen with a clear question,
then answer from what it sees.
ATOM's own screen has panels: chat, news, live (live TV news), music, inbox, reminders, markets, briefing. To open or
close them ("open chat and music", "close everything", "show my desk", "put the news up") call show_panels ONCE with
every panel in it, then reply in a few words, like "Opening chat and music, sir." Don't read the panel contents aloud
unless asked. 'Show my desk' or 'my briefing' = briefing. 'Start my day' = run_routine (it opens the briefing itself)."""

history = []


def _assistant_dict(message):
    """Keep only fields Groq accepts back; gpt-oss adds a reasoning field."""
    data = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        data["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in message.tool_calls
        ]
    return data


def _prune_old_screens(messages):
    """Keep only the newest read_screen list so long tasks stay under Groq's per-minute token limit."""
    screens = [m for m in messages if m.get("role") == "tool" and '"message": "Window:' in m.get("content", "")]
    for old in screens[:-1]:
        old["content"] = '{"ok": true, "message": "(older screen list removed)"}'


def _call(messages, tool_choice):
    _prune_old_screens(messages)
    return brains.chat(messages, tools=TOOL_DEFINITIONS, tool_choice=tool_choice, max_tokens=400)


def _finish(reply):
    history.append({"role": "assistant", "content": reply})
    return reply


def _words(text):
    return " ".join(text.lower().replace(",", " ").replace(".", " ").replace("!", " ").split())


_brain_lock = threading.Lock()  # voice and Telegram take turns, so the history stays in order


def ask(text, should_stop=None):
    with _brain_lock:
        return _ask(text, should_stop)


def _ask(text, should_stop=None):
    """Reply to text, allowing tool rounds, then a spoken summary."""
    # A waiting risky action is confirmed or cancelled here in code, never by the model,
    # so the model can't approve its own request.
    if PENDING:
        said = _words(text)
        if said in YES or said.startswith(("yes ", "yeah ", "go ahead", "do it")):
            history.append({"role": "user", "content": text})
            result = confirm_pending()
            return _finish(result["message"] if result else "That request expired. Ask me again.")
        if said in NO or said.startswith(("no ", "cancel", "don't")):
            cancel_pending()
            history.append({"role": "user", "content": text})
            return _finish("Okay, cancelled.")
        cancel_pending()  # anything else drops the waiting action

    # Plain panel commands ("open chat and music", "close everything") skip the brain: instant.
    import ui_bridge
    command = ui_bridge.parse_command(text)
    if command and hasattr(ui_bridge.get_ui(), "show_panels"):
        history.append({"role": "user", "content": text})
        result = ui_bridge.show_panels(*command)
        return _finish(result["message"].replace(".", ", sir.", 1) if result["ok"] else result["message"])

    history.append({"role": "user", "content": text})
    del history[:-12]
    import notifications
    from datetime import datetime
    system = (SYSTEM + "\n\nNow: " + datetime.now().strftime("%A %d %B %Y, %I:%M %p")
              + "\nSaved preferences:\n" + memory_context() + "\n" + notifications.context())
    messages = [{"role": "system", "content": system}] + history[:]
    last_result = None

    try:
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            if should_stop and should_stop():
                return _finish("Okay, stopping.")
            # The last round forbids tools so the model must speak the result.
            choice = "auto" if round_number < MAX_TOOL_ROUNDS else "none"
            message = _call(messages, choice)
            if not message.tool_calls:
                reply = (message.content or "").strip()
                if not reply:
                    reply = last_result["message"] if last_result else "Sorry, I couldn't come up with a reply."
                return _finish(reply)

            messages.append(_assistant_dict(message))
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    result = {"ok": False, "message": "The tool arguments were invalid."}
                else:
                    result = run_tool(call.function.name, arguments)
                print("Tool:", call.function.name, "->", result.get("ok"), "|", str(result.get("message", ""))[:120])
                last_result = result
                if result.get("needs_confirmation"):
                    # Speak the exact question; don't let the model rephrase or act on it.
                    return _finish(result["message"])
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)[:1800]})
    except Exception as error:
        name = type(error).__name__
        print("Brain error:", name)
        if isinstance(error, brains.Offline) or "Connection" in name or "Timeout" in name:
            return _finish("I can't reach the internet right now, sir. Basic commands still work offline.")
        if isinstance(error, brains.AllBrainsDown):
            return _finish("All my brains are busy or rate limited. Give me a minute.")
        return _finish("Something went wrong with my brain. Check the log.")

    return _finish(last_result["message"] if last_result else "Done.")


if __name__ == "__main__":
    import time
    for question in ["What's my battery level?", "How do I open a bank account?"]:
        started = time.time()
        print("You:", question)
        print("ATOM:", ask(question), f"({time.time() - started:.1f}s)")
