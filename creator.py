"""Creator Mode for ATOM LABS work, plus hands-free video-idea capture.

"Creator mode" opens OBS, VS Code and YouTube Studio together (and switches OBS to a
scene when one is named and OBS is reachable). "Note this: ..." saves an idea with a
timestamp to creator_ideas.json (git-ignored) beside atom.py; "read my video ideas"
reads the latest ones back.
"""

import json
from datetime import datetime
from pathlib import Path

IDEAS_FILE = Path(__file__).with_name("creator_ideas.json")


def _load_ideas():
    try:
        return json.loads(IDEAS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def note_idea(text):
    text = (text or "").strip()
    if not text:
        return {"ok": False, "message": "Tell me the idea and I'll save it. Say: note this, then the idea."}
    ideas = _load_ideas()
    ideas.append({"at": datetime.now().isoformat(timespec="seconds"), "text": text})
    try:
        IDEAS_FILE.write_text(json.dumps(ideas, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        return {"ok": False, "message": f"I couldn't save that idea: {error}"}
    return {"ok": True, "message": f"Saved idea number {len(ideas)}: {text}"}


def read_ideas(count=5):
    ideas = _load_ideas()
    if not ideas:
        return {"ok": True, "message": "No video ideas saved yet. Say: note this, then your idea."}
    latest = ideas[-max(1, min(int(count), 20)):]
    lines = [f"{len(ideas) - len(latest) + i + 1}. {idea['text']}" for i, idea in enumerate(latest)]
    return {"ok": True, "message": "Your latest video ideas: " + "; ".join(lines)}


def read_comments(count=3):
    """Latest comments on the newest ATOM LABS video, via the YouTube Data API.
    Needs youtube_key.txt + youtube_channel.txt (see youtube_tools); without them,
    one plain line says what's missing."""
    import youtube_tools
    if not youtube_tools.configured():
        return {"ok": False, "message": "Reading comments needs the YouTube Data API: put an API key in "
                                        "youtube_key.txt and your channel id in youtube_channel.txt, "
                                        "both beside atom.py. Until then I can't see your comments."}
    comments = youtube_tools.latest_comments(count)
    if comments is None:
        return {"ok": False, "message": "I couldn't fetch comments just now. Check the internet and ask again."}
    if not comments:
        return {"ok": True, "message": "No comments on your latest video yet."}
    lines = [f"{c['author']}: {c['text']}" for c in comments]
    return {"ok": True, "message": "Latest comments on your newest video: " + " | ".join(lines)}


def creator_mode(scene=""):
    import tools
    said = []
    for app in ("OBS Studio", "Visual Studio Code"):
        try:
            result = tools.open_application(app)
            said.append(result["message"] if result.get("ok") else f"{app} didn't open.")
        except Exception as error:
            said.append(f"{app} didn't open ({type(error).__name__}).")
    try:
        tools.open_website("youtube", None)
        said.append("YouTube opened; Studio is in the account menu.")
    except Exception:
        said.append("YouTube didn't open.")
    try:
        import obs_tools
        if scene:
            result = obs_tools.obs_control("switch_scene", scene)
            said.append(result["message"])
        else:
            status = obs_tools.obs_status()
            said.append(status["message"] if not status.get("ok") else "OBS is reachable.")
    except Exception:
        said.append("OBS status unknown.")
    return {"ok": True, "message": "Creator mode: " + " ".join(said)}
