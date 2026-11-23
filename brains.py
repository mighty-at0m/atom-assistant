"""ATOM's brain chain: if one AI is rate-limited or down, the next one answers.

Order: Groq -> Gemini -> Cerebras -> OpenRouter. A provider is used only when its key exists
(environment variable or a key file beside atom.py). All key files are git-ignored.
Change a model with ATOM_<NAME>_MODEL, e.g. ATOM_GEMINI_MODEL.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).parent

PROVIDERS = [
    {"name": "groq", "env": "GROQ_API_KEY", "file": "groq_key.txt",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "model": os.getenv("ATOM_GROQ_MODEL", "openai/gpt-oss-20b"),
     "extra": {"reasoning_effort": "low", "parallel_tool_calls": False}},
    {"name": "gemini", "env": "GEMINI_API_KEY", "file": "gemini_key.txt",
     "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "model": os.getenv("ATOM_GEMINI_MODEL", "gemini-flash-lite-latest"), "extra": {}},
    {"name": "cerebras", "env": "CEREBRAS_API_KEY", "file": "cerebras_key.txt",
     "url": "https://api.cerebras.ai/v1/chat/completions",
     "model": os.getenv("ATOM_CEREBRAS_MODEL", "gpt-oss-120b"), "extra": {}},
    {"name": "openrouter", "env": "OPENROUTER_API_KEY", "file": "openrouter_key.txt",
     "url": "https://openrouter.ai/api/v1/chat/completions",
     "model": os.getenv("ATOM_OPENROUTER_MODEL", "openai/gpt-oss-20b:free"), "extra": {}},
]
_resting = {}          # provider name -> time it may be tried again
LAST = {"name": ""}    # which brain answered last (shown on the HUD)


class AllBrainsDown(Exception):
    pass


class Offline(ConnectionError):
    pass


def _key(provider):
    key = os.environ.get(provider["env"])
    path = HERE / provider["file"]
    if not key and path.exists():
        key = path.read_text(encoding="utf-8").strip()
    return key


def available():
    return [p["name"] for p in PROVIDERS if _key(p)]


def _wrap(message):
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        arguments = function.get("arguments") or "{}"
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        calls.append(SimpleNamespace(id=call.get("id") or ("call_%d" % len(calls)),
                                     function=SimpleNamespace(name=function.get("name", ""), arguments=arguments)))
    return SimpleNamespace(content=message.get("content") or "", tool_calls=calls or None)


def chat(messages, tools=None, tool_choice="auto", max_tokens=400):
    """Return the first answer from the chain, as an object with .content and .tool_calls."""
    offline_count = 0
    tried = 0
    for provider in PROVIDERS:
        key = _key(provider)
        if not key or _resting.get(provider["name"], 0) > time.time():
            continue
        tried += 1
        body = {"model": provider["model"], "messages": messages, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
            body.update(provider["extra"])
        elif "reasoning_effort" in provider["extra"]:
            body["reasoning_effort"] = provider["extra"]["reasoning_effort"]
        request = urllib.request.Request(provider["url"], data=json.dumps(body).encode("utf-8"), headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "ATOM"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8"))
            LAST["name"] = provider["name"]
            return _wrap(data["choices"][0]["message"])
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "ignore")[:200]
            print(f"Brain {provider['name']} HTTP {error.code}: {detail}")
            if error.code == 429:
                _resting[provider["name"]] = time.time() + 60
            elif error.code in (401, 403):
                _resting[provider["name"]] = time.time() + 3600  # bad key: stop trying for an hour
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"Brain {provider['name']} unreachable: {type(error).__name__}")
            offline_count += 1
        except (KeyError, IndexError, ValueError) as error:
            print(f"Brain {provider['name']} odd reply: {type(error).__name__}")
    if tried and offline_count == tried:
        raise Offline("No internet")
    if not tried:
        raise AllBrainsDown("No brain keys, or all are resting after rate limits.")
    raise AllBrainsDown("Every brain failed.")
