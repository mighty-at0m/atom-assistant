"""Explain my screen error: screenshot the screen, ask the vision brain what the error
means and how to fix it, and speak a short version.

Vision uses the same Gemini setup as screen.look_at_screen (gemini_key.txt). When no
vision key is configured, ATOM still takes the screenshot and says where it saved it,
so Mighty can look himself. Nothing here can raise into a turn.
"""

import tools


def explain_screen_error():
    shot = tools.take_screenshot()
    if not shot.get("ok"):
        return shot
    path = tools.LAST_SCREENSHOT.get("path")
    try:
        import screen
        if not screen._gemini_key():
            return {"ok": True, "message": "I took a screenshot, but I have no vision key to read it with. "
                                           "Put a Gemini key in gemini_key.txt beside atom.py and ask me again. "
                                           + shot["message"]}
        result = screen.look_at_screen(
            "Find the error message or problem on this screen. In at most three short plain sentences: "
            "what the error means, then the most likely fix. No markdown.")
        if result.get("ok"):
            return {"ok": True, "message": result["message"]}
        return {"ok": True, "message": "I took the screenshot but couldn't read it just now. " + shot["message"]}
    except Exception as error:
        print("Screen error help failed:", type(error).__name__)
        return {"ok": True, "message": "I took a screenshot, but reading it failed. "
                                       f"The screenshot is saved at {path}." if path else shot["message"]}
