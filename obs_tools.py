"""Control OBS Studio by voice: record, pause, switch scenes, stream.

In OBS: Tools > WebSocket Server Settings > Enable. If you set a password, put it in obs_password.txt
(git-ignored) beside atom.py. Needs: pip install obsws-python
"""

import os
from pathlib import Path

PASSWORD_FILE = Path(__file__).with_name("obs_password.txt")


def _client():
    import obsws_python as obs
    password = os.environ.get("OBS_PASSWORD") or (PASSWORD_FILE.read_text(encoding="utf-8").strip() if PASSWORD_FILE.exists() else "")
    return obs.ReqClient(host="localhost", port=int(os.getenv("OBS_PORT", "4455")), password=password, timeout=4)


def _go_live():
    _client().start_stream()
    return {"ok": True, "message": "You're live."}


def obs_control(action, scene=""):
    try:
        client = _client()
    except Exception:
        return {"ok": False, "message": "I can't reach OBS. Open OBS and turn on its WebSocket server under Tools."}
    if action == "start_recording":
        client.start_record()
        return {"ok": True, "message": "Recording."}
    if action == "stop_recording":
        result = client.stop_record()
        path = getattr(result, "output_path", "")
        return {"ok": True, "message": "Recording stopped." + (f" Saved as {Path(path).name}." if path else "")}
    if action == "pause_recording":
        client.pause_record()
        return {"ok": True, "message": "Recording paused."}
    if action == "resume_recording":
        client.resume_record()
        return {"ok": True, "message": "Recording resumed."}
    if action == "switch_scene":
        names = [s["sceneName"] for s in client.get_scene_list().scenes]
        match = next((n for n in names if n.lower() == scene.lower()), None) or next((n for n in names if scene.lower() in n.lower()), None)
        if not match:
            return {"ok": False, "message": "Your scenes are: " + ", ".join(names)}
        client.set_current_program_scene(match)
        return {"ok": True, "message": f"Switched to {match}."}
    if action == "start_streaming":
        from tools import hold_for_yes
        return hold_for_yes("go live on your stream", _go_live)
    if action == "stop_streaming":
        client.stop_stream()
        return {"ok": True, "message": "Stream ended."}
    if action == "status":
        record = client.get_record_status()
        return {"ok": True, "message": ("Recording, " + record.output_timecode.split(".")[0]) if record.output_active else "Not recording."}
    return {"ok": False, "message": "I can start, stop, pause or resume recording, switch scenes, or stream."}
