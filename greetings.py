"""Small personality touches: a rotating greeting, and milestone celebrations.

Greetings are plain text in the Abeo voice style (short, warm, a little Nigerian flavour).
Milestones live in milestones.json (git-ignored): {"subscribers": <last count seen>,
"celebrated": <highest hundred/thousand already celebrated>}. The subscriber count itself
comes from an optional channel_stats.json ({"subscribers": 123}) that anything external
(a stats fetcher, or Mighty by hand) may drop beside atom.py; with no count, no fuss.
"""

import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
MILESTONES_FILE = HERE / "milestones.json"
STATS_FILE = HERE / "channel_stats.json"

MORNING = [
    "Good morning, sir. Rise and shine, we move.",
    "Morning, sir. New day, new wins. How body?",
    "Good morning, sir. Hope you slept well. Plenty work, plenty grace today.",
    "Morning, sir. The day is fresh and so are we. Let's go.",
    "Good morning, sir. Small small, we will finish everything today.",
]
AFTERNOON = [
    "Good afternoon, sir. Hope the day is treating you well.",
    "Afternoon, sir. We are still moving. How is it going?",
    "Good afternoon, sir. Sun is up, work is on. I dey here.",
]
EVENING = [
    "Good evening, sir. Hope today was a good one.",
    "Evening, sir. Day is winding down, I am still here.",
    "Good evening, sir. Welcome back. How did today go?",
]
NIGHT = [
    "Evening, sir. Burning the midnight oil, I see.",
    "Still up, sir? I dey awake with you.",
    "Late night, sir. Let's make it count, then rest.",
]


def greeting_for(hour=None):
    """One greeting, rotating by day so it doesn't repeat back-to-back days."""
    from datetime import datetime
    hour = datetime.now().hour if hour is None else hour
    if 5 <= hour < 12:
        choices = MORNING
    elif 12 <= hour < 17:
        choices = AFTERNOON
    elif 17 <= hour < 22:
        choices = EVENING
    else:
        choices = NIGHT
    return choices[date.today().toordinal() % len(choices)]


def _load_milestones():
    try:
        return json.loads(MILESTONES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_milestones(data):
    try:
        MILESTONES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def subscriber_count(stats=None):
    """The latest subscriber count from channel_stats.json, or None if nobody recorded one."""
    if stats and stats.get("subscribers") is not None:
        try:
            return int(stats["subscribers"])
        except (TypeError, ValueError):
            return None
    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        return int(data["subscribers"])
    except Exception:
        return None


def milestone_line(stats=None):
    """If the count crossed a new hundred (or thousand) since the last check, celebrate it.

    Updates milestones.json either way so the same crossing is only celebrated once.
    Returns "" when there is nothing new to celebrate. Never raises.
    """
    try:
        count = subscriber_count(stats)
        if count is None:
            return ""
        data = _load_milestones()
        celebrated = int(data.get("celebrated") or 0)
        data["subscribers"] = count
        step = 1000 if count >= 1000 else 100
        crossed = (count // step) * step
        line = ""
        if crossed > celebrated and crossed > 0:
            data["celebrated"] = crossed
            line = (f"And sir, big news: ATOM LABS just crossed {crossed:,} subscribers! "
                    f"You are at {count:,} now. Congratulations, the work is showing.")
        _save_milestones(data)
        return line
    except Exception:
        return ""
