"""Free web info for ATOM: weather (Open-Meteo), news (Google News RSS) and quick web answers.
No keys needed. Default city comes from ATOM_CITY or a saved 'city' preference."""

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "en"}
CODES = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy",
         51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
         66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
         80: "rain showers", 81: "rain showers", 82: "heavy rain showers", 95: "thunderstorms",
         96: "thunderstorms with hail", 99: "thunderstorms with hail"}


def _get(url, timeout=8):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8", "ignore")


def _default_city():
    try:
        from memory import _load
        saved = _load().get("city") or _load().get("my city")
        if saved:
            return saved
    except Exception:
        pass
    return os.getenv("ATOM_CITY", "Abakaliki")


def get_weather(city=None):
    city = city or _default_city()
    found = json.loads(_get("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(city)))
    if not found.get("results"):
        return {"ok": False, "message": f"I couldn't find a place called {city}."}
    place = found["results"][0]
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=auto"
           "&current=temperature_2m,apparent_temperature,weather_code,precipitation"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&forecast_days=2"
           % (place["latitude"], place["longitude"]))
    data = json.loads(_get(url))
    now, day = data["current"], data["daily"]
    text = (f"{place['name']}: {round(now['temperature_2m'])}°C now, feels like {round(now['apparent_temperature'])}, "
            f"{CODES.get(now['weather_code'], 'mixed weather')}. Today {round(day['temperature_2m_min'][0])} to "
            f"{round(day['temperature_2m_max'][0])}°C, {day['precipitation_probability_max'][0]}% chance of rain. "
            f"Tomorrow {CODES.get(day['weather_code'][1], 'mixed')}, up to {round(day['temperature_2m_max'][1])}°C, "
            f"{day['precipitation_probability_max'][1]}% chance of rain.")
    return {"ok": True, "message": text}


def get_news(topic=None, count=5):
    if topic:
        url = "https://news.google.com/rss/search?hl=en-NG&gl=NG&ceid=NG:en&q=" + urllib.parse.quote(topic)
    else:
        url = "https://news.google.com/rss?hl=en-NG&gl=NG&ceid=NG:en"
    try:
        root = ET.fromstring(_get(url))
    except Exception:
        root = ET.fromstring(_get("https://feeds.bbci.co.uk/news/world/rss.xml"))
    titles = [unescape(item.findtext("title") or "") for item in root.iter("item")][:max(1, min(int(count), 8))]
    if not titles:
        return {"ok": False, "message": "I couldn't get the news right now."}
    return {"ok": True, "message": "Headlines: " + " | ".join(titles)}


def web_search(query):
    """Top results as short snippets, so the brain can answer about current things."""
    snippets = []
    try:
        page = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query))
        for title, snippet in re.findall(r'class="result__a"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', page, re.S)[:4]:
            clean = lambda s: unescape(re.sub(r"<[^>]+>", "", s)).strip()
            snippets.append(clean(title) + ": " + clean(snippet))
    except Exception:
        pass
    if not snippets:
        try:
            data = json.loads(_get("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch="
                                   + urllib.parse.quote(query)))
            for hit in data["query"]["search"]:
                snippets.append(hit["title"] + ": " + unescape(re.sub(r"<[^>]+>", "", hit["snippet"])))
        except Exception:
            pass
    if not snippets:
        return {"ok": False, "message": "I couldn't search the web right now."}
    return {"ok": True, "message": " || ".join(snippets)[:1500]}


def _age(published):
    """RSS pubDate -> '5m', '2h', '3d'."""
    try:
        from email.utils import parsedate_to_datetime
        import time
        seconds = max(0, time.time() - parsedate_to_datetime(published).timestamp())
    except Exception:
        return ""
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def news_items(topic=None, count=8):
    """Headlines for the screen: [{'title', 'source', 'age'}] (Google News Nigeria, BBC fallback)."""
    if topic:
        url = "https://news.google.com/rss/search?hl=en-NG&gl=NG&ceid=NG:en&q=" + urllib.parse.quote(topic)
    else:
        url = "https://news.google.com/rss?hl=en-NG&gl=NG&ceid=NG:en"
    try:
        root = ET.fromstring(_get(url))
    except Exception:
        root = ET.fromstring(_get("https://feeds.bbci.co.uk/news/world/rss.xml"))
    items = []
    for item in root.iter("item"):
        title = unescape(item.findtext("title") or "").strip()
        source = unescape(item.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        elif not source and " - " in title:
            title, source = title.rsplit(" - ", 1)
        if title:
            items.append({"title": title, "source": source or "BBC", "age": _age(item.findtext("pubDate") or "")})
        if len(items) >= count:
            break
    return items
