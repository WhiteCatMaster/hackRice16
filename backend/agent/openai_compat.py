"""OpenAI's chat-completions shape, as a third brain for the agent loop.

Same contract as the other two in `loop.py`: the model picks tools from
`tools.SCHEMA`, the tools return the numbers, and the model only writes the prose
around them. Nothing here does arithmetic and nothing here writes to Nessie.

It exists because "bring your own key" is only worth offering if the key someone
already has is one of the ones we accept, and this one shape covers most of
them: OpenAI itself, and — with `X-Model-Base-URL` — OpenRouter, Groq, Together,
vLLM and a model running on the user's own laptop. One transport, several
favourite models.

stdlib only (urllib), like the rest of the backend. `requirements.txt` says P1
installs nothing to run, and P3 keeps that property as a fallback; a second HTTP
library for one POST would break it for no gain. If this call fails for any
reason the caller falls back to the scripted router, so a dead, throttled or
mistyped endpoint never takes the demo down.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("treasurer.agent.openai")

DEFAULT_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
DEFAULT_MODEL = os.environ.get("TREASURER_OPENAI_MODEL", "gpt-4o-mini")
TIMEOUT = 45.0


class OpenAIError(RuntimeError):
    pass


def api_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def model() -> str:
    return DEFAULT_MODEL


# --------------------------------------------------------------------------
# tool schema translation
# --------------------------------------------------------------------------


def declarations(schema: list[dict]) -> list[dict]:
    """`tools.SCHEMA` (Anthropic shape) as OpenAI tool definitions.

    JSON Schema passes through untouched here — unlike Gemini, which takes only
    a subset of it. A tool that takes nothing still needs an object schema; an
    absent `parameters` is read as "unknown arguments" rather than "none".
    """
    out = []
    for tool in schema:
        params = tool.get("input_schema") or {}
        out.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": params.get("properties") or {},
                    "required": list(params.get("required") or []),
                },
            },
        })
    return out


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

# The output cap, in each of the two spellings the API has used. The reasoning
# models refuse `max_tokens` and want `max_completion_tokens`; everything older
# is the other way round, and the endpoints that only clone the old shape
# (llama.cpp, some proxies) take `max_tokens` and nothing else. Which one a model
# accepts is not detectable up front, so it is learned from the rejection — the
# same ladder `gemini.py` climbs for its thinking field.
CAP_FIELDS = ("max_completion_tokens", "max_tokens")
#: Which spelling an endpoint accepted, learned once per process.
_ACCEPTED: dict[str, str] = {}


def generate(system: str, messages: list[dict], tool_schema: list[dict],
             key: str, name: str | None = None, base_url: str | None = None,
             max_tokens: int = 2048) -> dict:
    """One `/chat/completions` call. Raises OpenAIError on anything but a 200."""
    if not key:
        raise OpenAIError("no OpenAI key")
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    name = name or DEFAULT_MODEL
    known = _ACCEPTED.get(base)
    ladder = (known,) if known else CAP_FIELDS

    last: OpenAIError | None = None
    for field in ladder:
        body = {
            "model": name,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": declarations(tool_schema),
            # This is a two-sentence answer over numbers the tools already
            # computed. There is nothing to be creative about.
            "temperature": 0.2,
            field: max_tokens,
        }
        try:
            response = _post(base, key, body)
        except OpenAIError as exc:
            # A rejected cap field comes back as a 400 naming it, so unlike
            # Gemini's mystery 400 this one can be told apart from every other
            # bad request — and a 400 for any other reason should raise now
            # rather than be retried with a second spelling.
            if "HTTP 400" not in str(exc) or field not in str(exc):
                raise
            log.info("openai endpoint rejected %s", field)
            last = exc
            continue
        _ACCEPTED[base] = field
        return response
    raise last  # type: ignore[misc]


def _post(base: str, key: str, body: dict, _retries: int = 1) -> dict:
    """One POST, with a single short retry on 503 — `gemini._post`'s policy.

    "The engine is overloaded" is usually over before the user notices, unlike a
    429, which needs the quota window to roll and is better spent falling back
    to the scripted router. One retry is the whole policy.
    """
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body, default=str).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code == 503 and _retries > 0:
            log.info("openai 503, retrying once")
            time.sleep(1.5)
            return _post(base, key, body, _retries - 1)
        raise OpenAIError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OpenAIError(f"unreachable: {exc.reason}") from exc


def message_of(response: dict) -> dict:
    """The first choice's message, or an explanation of why there is none."""
    choices = response.get("choices") or []
    if not choices:
        raise OpenAIError(f"no choices (response keys: {sorted(response)})")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise OpenAIError(f"no message (finish_reason={choice.get('finish_reason')})")
    # A truncated turn is a failure, not a short answer: the caller would hand a
    # half-finished sentence to someone deciding what to do with their money,
    # and the scripted router's complete one is right there.
    if choice.get("finish_reason") == "length":
        raise OpenAIError("hit the output cap before finishing the reply")
    return message


def calls_in(message: dict) -> list[dict]:
    """The tool calls on a message, as `{id, name, args}` — args already parsed.

    Arguments arrive as a JSON *string*, and a model that emits a broken one
    should not take the turn down: an unparseable argument becomes an empty one,
    the tool answers or errors on its own terms, and the loop carries on.
    """
    out = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw = function.get("arguments") or "{}"
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            log.warning("could not parse arguments for %s", function.get("name"))
            args = {}
        out.append({
            "id": call.get("id") or "",
            "name": function.get("name") or "",
            "args": args if isinstance(args, dict) else {},
        })
    return out


def text_in(message: dict) -> str:
    """The prose on a message, whichever of the two content shapes it uses."""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        # Some endpoints answer with the parts array the vision API uses.
        return "".join(
            part.get("text") or "" for part in content if isinstance(part, dict)
        ).strip()
    return ""
