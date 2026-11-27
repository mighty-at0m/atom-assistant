"""YouTube Data API v3 for ATOM: channel stats and latest comments (optional).

Uses the API only when Mighty adds a key the repo's usual way: a plain-text file
youtube_key.txt beside atom.py (same convention as groq_key.txt / gemini_key.txt), or
the YOUTUBE_API_KEY environment variable. The channel is named in youtube_channel.txt
(a channel id, UC...) beside atom.py, or as "channel_id" inside channel_stats.json.
With no key or no channel id, every function returns None and callers simply skip the
YouTube section — nothing crashes, nothing is required. Successful stats are cached
back into channel_stats.json so the brief and milestones can reuse them.
Get a key: Google Cloud Console > APIs & Services > Library > YouTube Data API v3 >
Enable, then Credentials > Create credentials > API key.
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
KEY_FILE = HERE / "youtube_key.txt"
CHANNEL_FILE = HERE / "youtube_channel.txt"
STATS_FILE = HERE / "channel_stats.json"
API = "https://www.googleapis.com/youtube/v3"


def _key():
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    return key or None


def _channel_id():
    if CHANNEL_FILE.exists():
        value = CHANNEL_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8")).get("channel_id")
    except Exception:
        return None


def configured():
    return bool(_key() and _channel_id())


def _get(path, **params):
    params["key"] = _key()
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def channel_stats():
    """{'subscribers', 'views', 'videos'} from the API, cached to channel_stats.json.
    None when the API isn't configured or the call fails."""
    if not configured():
        return None
    try:
        data = _get("channels", part="statistics", id=_channel_id())
        items = data.get("items") or []
        if not items:
            return None
        stats = items[0]["statistics"]
        out = {"subscribers": int(stats["subscriberCount"]),
               "views": int(stats["viewCount"]),
               "videos": int(stats["videoCount"])}
        try:
            cached = {}
            if STATS_FILE.exists():
                cached = json.loads(STATS_FILE.read_text(encoding="utf-8"))
            cached.update(out)
            STATS_FILE.write_text(json.dumps(cached, indent=2), encoding="utf-8")
        except Exception:
            pass
        return out
    except Exception as error:
        print("YouTube stats failed:", type(error).__name__)
        return None


def latest_comments(count=3):
    """Newest comments on the latest video: [{'author', 'text'}]. None if not configured."""
    if not configured():
        return None
    try:
        channel = _get("channels", part="contentDetails", id=_channel_id())
        uploads = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        videos = _get("playlistItems", part="snippet", playlistId=uploads, maxResults=1)
        video_id = videos["items"][0]["snippet"]["resourceId"]["videoId"]
        threads = _get("commentThreads", part="snippet", videoId=video_id,
                       order="time", maxResults=max(1, min(int(count), 10)))
        out = []
        for item in threads.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            out.append({"author": top.get("authorDisplayName", ""),
                        "text": " ".join((top.get("textDisplay") or "").split())[:200]})
        return out
    except Exception as error:
        print("YouTube comments failed:", type(error).__name__)
        return None
