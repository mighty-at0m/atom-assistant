"""Data for the web screen: ticker, USD/NGN history, weather, news, now playing, inbox, reminders.

Every network call is cached (10+ minutes) and never raises: on failure the last good value
(or None) comes back, so the screen just shows a dash. No API keys are needed.
"""

import json
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
FX_FILE = HERE / "fx_history.json"   # git-ignored cache of daily USD/NGN rates

# YouTube channel ids for the live news video (embed/live_stream?channel=ID).
NEWS_CHANNELS = {
    "channels": {"name": "CHANNELS TV", "id": "UCEXGDNclvmg6RW0vipJYsTQ"},
    "arise": {"name": "ARISE NEWS", "id": "UCyEJX-kSj0kOOCS7Qlq2G7g"},
}
NEWS_CHANNEL = os.getenv("ATOM_NEWS_CHANNEL", "channels").lower()

_cache = {}
_lock = threading.Lock()


def cached(key, seconds, fetch):
    """Return fetch() at most once per `seconds`; on errors keep the last good value."""
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < seconds:
        return hit[1]
    try:
        value = fetch()
    except Exception as error:
        print("Screen data", key, "failed:", type(error).__name__)
        with _lock:
            if hit:  # try again in a minute, show the old value meanwhile
                _cache[key] = (time.time() - seconds + 60, hit[1])
            else:
                _cache[key] = (time.time() - seconds + 60, None)
        return hit[1] if hit else None
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def _json(url, timeout=8):
    from webtools import _get
    return json.loads(_get(url, timeout=timeout))


def channel():
    found = NEWS_CHANNELS.get(NEWS_CHANNEL)
    if found:
        return found
    if NEWS_CHANNEL.startswith("uc"):  # a raw channel id in ATOM_NEWS_CHANNEL
        return {"name": "LIVE NEWS", "id": os.getenv("ATOM_NEWS_CHANNEL")}
    return NEWS_CHANNELS["channels"]


# ---- Markets ---------------------------------------------------------------------------

def _usd_rates(day):
    """All rates against USD for one day (fawazahmed0 currency-api on jsDelivr, free, no key)."""
    stamp = day.isoformat() if isinstance(day, date) else day
    for url in (f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{stamp}/v1/currencies/usd.min.json",
                f"https://{stamp}.currency-api.pages.dev/v1/currencies/usd.min.json"):
        try:
            return _json(url)["usd"]
        except Exception:
            continue
    raise ConnectionError("currency-api unreachable")


def _fx_history_fetch(days=30, step=3):
    try:
        saved = json.loads(FX_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        saved = {}
    today = date.today()
    wanted = [today - timedelta(days=d) for d in range(days, -1, -step)]
    if wanted[-1] != today:
        wanted.append(today)
    for day in wanted + [today - timedelta(days=1)]:
        key = day.isoformat()
        if key in saved and key != today.isoformat():
            continue
        try:
            saved[key] = round(float(_usd_rates(day)["ngn"]), 2)
        except Exception:
            if day == today:  # today's file may not exist yet
                continue
    cutoff = (today - timedelta(days=days + 5)).isoformat()
    saved = {k: v for k, v in saved.items() if k >= cutoff}
    try:
        FX_FILE.write_text(json.dumps(saved, indent=0), encoding="utf-8")
    except OSError:
        pass
    return sorted(saved.items())


def fx_history():
    """[(YYYY-MM-DD, rate)] for about 30 days; refreshed every 6 hours."""
    return cached("fx_history", 6 * 3600, _fx_history_fetch) or []


def _ticker_fetch():
    out = {}
    try:
        now = _json("https://open.er-api.com/v6/latest/USD")
        out["usd_ngn"] = float(now["rates"]["NGN"])
    except Exception:
        pass
    try:
        rates = _usd_rates("latest")
        out.setdefault("usd_ngn", float(rates["ngn"]))
        if rates.get("xau"):
            out["gold"] = 1.0 / float(rates["xau"])
    except Exception:
        pass
    try:
        before = _usd_rates(date.today() - timedelta(days=1))
        if "usd_ngn" in out:
            out["usd_ngn_change"] = (out["usd_ngn"] / float(before["ngn"]) - 1) * 100
        if "gold" in out and before.get("xau"):
            out["gold_change"] = (out["gold"] * float(before["xau"]) - 1) * 100
    except Exception:
        pass
    try:
        coins = _json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum"
                      "&vs_currencies=usd&include_24hr_change=true")
        out["btc"], out["btc_change"] = coins["bitcoin"]["usd"], coins["bitcoin"].get("usd_24h_change")
        out["eth"], out["eth_change"] = coins["ethereum"]["usd"], coins["ethereum"].get("usd_24h_change")
    except Exception:
        pass
    if not out:
        raise ConnectionError("no market data")
    return out


def ticker():
    """{'usd_ngn', 'usd_ngn_change', 'btc', 'btc_change', 'eth', 'eth_change', 'gold', 'gold_change'}."""
    return cached("ticker", 10 * 60, _ticker_fetch) or {}


# ---- Weather and news -------------------------------------------------------------------

def _weather_fetch():
    import urllib.parse
    from webtools import CODES, _default_city
    city = _default_city()
    place = cached("geo:" + city, 7 * 86400,
                   lambda: _json("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(city))["results"][0])
    if not place:
        raise ConnectionError("no place")
    data = _json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=auto"
                 "&current=temperature_2m,weather_code&daily=precipitation_probability_max&forecast_days=1"
                 % (place["latitude"], place["longitude"]))
    return {"city": place["name"], "temp": round(data["current"]["temperature_2m"]),
            "text": CODES.get(data["current"]["weather_code"], ""),
            "rain": data["daily"]["precipitation_probability_max"][0]}


def weather():
    return cached("weather", 15 * 60, _weather_fetch)


def news(count=8):
    from webtools import news_items
    return cached("news", 10 * 60, lambda: news_items(count=count)) or []


# ---- Local things (cheap, no network) ----------------------------------------------------

def _age(seconds):
    seconds = max(0, time.time() - seconds)
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def inbox(limit=8):
    import notifications
    items = list(notifications.RECENT)[-limit:][::-1]
    return {"items": [{"app": n.get("app", ""), "sender": n.get("sender", ""), "text": n.get("text", ""),
                       "age": _age(n.get("at", time.time()))} for n in items],
            "status": notifications.STATUS.get("text", "off")}


def reminders(limit=6):
    import reminders as reminder_store
    return [{"text": text, "when": when} for text, when in reminder_store.upcoming(limit)]


def battery():
    try:
        from tools import get_battery_status
        result = get_battery_status()
    except Exception:
        return None
    if not result.get("ok"):
        return None
    message = result["message"]
    digits = "".join(ch for ch in message.split("%")[0] if ch.isdigit())
    return {"percent": int(digits) if digits else None, "plugged": "plugged" in message}


# ---- Now playing (Windows media controls) ------------------------------------------------

def _media_module():
    try:
        from winsdk.windows.media import control
    except ImportError:
        from winrt.windows.media import control
    return control


_media_loop = {"loop": None}


def now_playing():
    """{'title', 'artist', 'app', 'playing'} or {'error': ...}. Needs winsdk (or winrt) on Windows."""
    try:
        control = _media_module()
    except ImportError:
        return {"error": "Install winsdk to see what's playing. The buttons still work."}
    import asyncio

    async def read():
        manager = await control.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session is None:
            return {"title": "", "artist": "", "app": "", "playing": False}
        props = await session.try_get_media_properties_async()
        status = session.get_playback_info().playback_status
        app = (session.source_app_user_model_id or "").split("!")[-1].replace(".exe", "")
        return {"title": props.title or "", "artist": props.artist or "", "app": app,
                "playing": int(status) == 4}  # 4 = Playing
    try:
        if _media_loop["loop"] is None:
            _media_loop["loop"] = asyncio.new_event_loop()
        return _media_loop["loop"].run_until_complete(read())
    except Exception as error:
        return {"error": "Couldn't read the player (" + type(error).__name__ + ")."}
