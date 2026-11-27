"""The Morning Brief: one spoken summary to start the day.

"Good morning" / "morning brief" -> greeting, date and time, weather, Gmail headlines,
today's reminders, and (only when their data exists) YouTube channel stats and a markets
line. Every section is guarded on its own: a dead network or a missing setup turns that
section into one plain line, never a failed brief.
"""

from datetime import datetime

import greetings


def _section(fetch):
    """Run one brief section; any failure becomes a short plain note, never an exception."""
    try:
        return fetch() or ""
    except Exception as error:
        print("Brief section failed:", type(error).__name__, str(error)[:100])
        return ""


def _weather():
    import webtools
    result = webtools.get_weather()
    return ("Weather: " + result["message"]) if result.get("ok") else ""


def _gmail():
    import gmail_tools
    result = gmail_tools.check_email(3, unread_only=True)
    return result["message"] if result.get("ok") else ""


def _reminders():
    import reminders
    items = reminders._load()
    today = datetime.now().date()
    todays = [item for item in items if not item.get("app")
              and datetime.fromtimestamp(item["due"]).date() == today]
    if not todays:
        return "No reminders due today."
    spoken = "; ".join(f"{item['text']} at {reminders._spoken(datetime.fromtimestamp(item['due']))}"
                       for item in todays[:5])
    return f"Today's reminders: {spoken}."


def _youtube_stats():
    """Live stats from the YouTube Data API when a key is configured (youtube_tools),
    else whatever channel_stats.json beside atom.py already holds. None if neither."""
    try:
        import youtube_tools
        stats = youtube_tools.channel_stats()
        if stats:
            return stats
    except Exception:
        pass
    import json
    from pathlib import Path
    stats_file = Path(__file__).with_name("channel_stats.json")
    if not stats_file.exists():
        return None
    try:
        return json.loads(stats_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _youtube_line(stats):
    if not stats:
        return ""
    parts = []
    if stats.get("subscribers") is not None:
        parts.append(f"{int(stats['subscribers']):,} subscribers")
    if stats.get("views") is not None:
        parts.append(f"{int(stats['views']):,} total views")
    return ("ATOM LABS: " + ", ".join(parts) + ".") if parts else ""


def _youtube():
    return _youtube_line(_youtube_stats())


def _markets():
    import hud_feeds
    ticker = hud_feeds.ticker()
    if not ticker:
        return ""
    parts = []
    if ticker.get("usd_ngn"):
        parts.append(f"dollar at {round(ticker['usd_ngn']):,} naira")
    if ticker.get("btc"):
        parts.append(f"Bitcoin at ${round(ticker['btc']):,}")
    return ("Markets: " + ", ".join(parts) + ".") if parts else ""


def morning_brief():
    now = datetime.now()
    parts = [greetings.greeting_for(now.hour),
             "It is " + now.strftime("%A, %B %d, %I:%M %p").replace(" 0", " ") + "."]
    stats = _section(_youtube_stats) or None
    for fetch in (_weather, _gmail, _reminders, _markets):
        text = _section(fetch)
        if text:
            parts.append(text)
    if stats:
        parts.append(_youtube_line(stats))
    celebration = _section(lambda: greetings.milestone_line(stats))
    if celebration:
        parts.append(celebration)
    return {"ok": True, "message": " ".join(parts)[:1700]}
