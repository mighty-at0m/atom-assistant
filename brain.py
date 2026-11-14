import shutil
import subprocess

OPENCLAW = shutil.which("openclaw.cmd") or shutil.which("openclaw")  # Windows needs the .cmd

def ask(text, timeout=180):
    try:
        return ask_raw(text, timeout)
    except subprocess.TimeoutExpired:
        return "Sorry, my brain took too long. Groq may be rate limiting me, so try again in a minute."


def ask_raw(text, timeout=180):
    """Send text to the OpenClaw main agent and return its reply."""
    result = subprocess.run(
        [OPENCLAW, "agent", "--agent", "main", "--message", text],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    reply = result.stdout.strip()
    if result.returncode != 0 and not reply:
        reply = "Brain error: " + result.stderr.strip()[-300:]
    return reply


if __name__ == "__main__":
    from stt import record, to_wav_bytes, transcribe

    heard = transcribe(to_wav_bytes(record(5)))
    print("You said:", heard)
    print("Thinking...")
    print("ATOM:", ask(heard))