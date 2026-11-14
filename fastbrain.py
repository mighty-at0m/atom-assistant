"""Fast conversational brain with a small, safe set of local PC tools."""

import json
import os
from pathlib import Path

from groq import Groq

from memory import context as memory_context
from tools import TOOL_DEFINITIONS, run_tool


SYSTEM = """You are ATOM, a concise voice assistant on a Windows laptop.
Reply in one to three short spoken sentences. Do not use markdown, lists, or emojis.
Use a tool only when it is needed to fulfil a real PC request. You may only use the tools provided.
Never claim to have performed an action unless its tool result confirms it.
Only save a memory when the user explicitly asks you to remember it. Memories stay on this PC.
For deleting files, sending messages, installing software, restarting, shutting down, or changing settings,
say that ATOM needs an explicit confirmation; those actions are not available yet."""

key_file = Path(__file__).with_name("groq_key.txt")
key = os.environ.get("GROQ_API_KEY") or (key_file.read_text().strip() if key_file.exists() else None)
client = Groq(api_key=key)
history = []
MODEL = "openai/gpt-oss-20b"


def _message_dict(message):
    return message.model_dump(exclude_none=True)


def ask(text):
    """Reply to text, allowing at most two rounds of approved local tools."""
    history.append({"role": "user", "content": text})
    del history[:-12]
    system = SYSTEM + "\n\nSaved preferences:\n" + memory_context()
    messages = [{"role": "system", "content": system}] + history[:]

    for _ in range(2):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            parallel_tool_calls=False,
            max_completion_tokens=300,
            extra_body={"reasoning_effort": "low"},
        )
        message = response.choices[0].message
        messages.append(_message_dict(message))
        if not message.tool_calls:
            reply = (message.content or "Sorry, I couldn't generate a reply.").strip()
            history.append({"role": "assistant", "content": reply})
            return reply

        for call in message.tool_calls:
            try:
                arguments = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                result = {"ok": False, "message": "The tool arguments were invalid."}
            else:
                result = run_tool(call.function.name, arguments)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})

    reply = "I completed the available steps, but I need a simpler request to continue."
    history.append({"role": "assistant", "content": reply})
    return reply
