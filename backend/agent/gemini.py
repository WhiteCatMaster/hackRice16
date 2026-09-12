"""Gemini, as a second brain for the agent loop.

Same contract as the Anthropic path in `loop.py`: the model picks tools from
`tools.SCHEMA`, the tools return numbers, and the model only writes the prose
around them. Nothing here does arithmetic, and nothing here writes to Nessie.

stdlib only (urllib), like the rest of the backend — `requirements.txt` says P1
installs nothing to run, and a second HTTP library for one POST would break that
for no gain. If this call fails for any reason the caller falls back to the
scripted router, so a dead or throttled Gemini never takes the demo down.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from backend.nessie import config  # noqa: F401  — importing it loads .env

log = logging.getLogger("treasurer.agent.gemini")

BASE_URL = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")
# A thinking model answers in a handful of seconds but occasionally takes twenty,
# and a turn is several of these calls back to back. 30s was cutting off answers
# that were on their way.
TIMEOUT = 45.0
# Output budget for a model that will not let us switch thinking off.
THINKING_TOKENS = 8192


class GeminiError(RuntimeError):
    pass


def api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def model() -> str:
    return os.environ.get("TREASURER_GEMINI_MODEL", "gemini-flash-latest").strip()


# --------------------------------------------------------------------------
# tool schema translation
# --------------------------------------------------------------------------

def _schema(node: dict) -> dict:
    """One JSON-Schema node as Gemini's OpenAPI subset.

    Gemini rejects fields it does not know, so this copies across only the four
    that `tools.SCHEMA` actually uses instead of passing the node through.
    """
    out: dict = {"type": str(node.get("type", "string")).upper()}
    if node.get("description"):
        out["description"] = node["description"]
    if node.get("enum"):
        out["enum"] = list(node["enum"])
    properties = node.get("properties")
    if properties:
        out["properties"] = {k: _schema(v) for k, v in properties.items()}
        if node.get("required"):
            out["required"] = list(node["required"])
    return out


def declarations(schema: list[dict]) -> list[dict]:
    """`tools.SCHEMA` (Anthropic shape) as Gemini function declarations.

    A no-argument tool is declared with no `parameters` at all: Gemini refuses an
    object schema with an empty `properties` map, and half our tools take nothing.
    """
    out = []
    for tool in schema:
        declared = {"name": tool["name"], "description": tool["description"]}
        params = tool.get("input_schema") or {}
        if params.get("properties"):
            declared["parameters"] = _schema(params)
        out.append(declared)
    return out


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

# "Think as little as possible", in each of the two spellings the API has used.
# Gemini 3 took `thinkingLevel` and refuses `thinkingBudget`; everything older is
# the other way round. Neither is detectable up front: `gemini-flash-latest` is a
# server-side alias that today resolves to a Gemini 3 model, so the configured
# name does not say which generation answers.
LOW = {"thinkingLevel": "low"}
OFF = {"thinkingBudget": 0}
# Which spelling a model name actually accepted, learned once per process.
_ACCEPTED: dict[str, dict | None] = {}


def thinking_ladder(name: str) -> list[dict | None]:
    """The thinking settings to try for `name`, best guess first.

    Sending the wrong one does not cost a slower answer, it costs the answer: the
    rejection is a bare HTTP 400 naming no argument, and with no second spelling
    to try the only way on is to drop thinking control altogether — at which point
    a Gemini 3 turn thinks for longer than TIMEOUT and the caller falls back to the
    scripted router. Every turn, silently, with the key sitting right there in
    .env. So both spellings stay in the ladder and `None` is the last resort.

    The name still picks the order, because a wrong guess costs a whole request
    against a free tier that allows twenty.
    """
    if name.startswith("gemini-3") or name.endswith("-latest"):
        return [LOW, OFF, None]
    return [OFF, LOW, None]



def generate(system: str, contents: list[dict], tool_schema: list[dict],
             max_tokens: int = 2048) -> dict:
    """One `:generateContent` call. Raises GeminiError on anything but a 200."""
    name = model()
    if name in _ACCEPTED:
        ladder = [_ACCEPTED[name]]
    else:
        ladder = thinking_ladder(name)

    last: GeminiError | None = None
    for thinking in ladder:
        # Thinking is billed out of maxOutputTokens, so wherever it is not switched
        # fully off the budget has to cover the reasoning as well as the prose.
        # Left at 1024 the answer comes back cut off mid-sentence — "your flight
        # home on 202" — which is worse than no answer when it is about money.
        budget = max_tokens if thinking == OFF else max(max_tokens, THINKING_TOKENS)
        config = {"maxOutputTokens": budget, "temperature": 0.2}
        if thinking is not None:
            # This is a two-sentence answer over numbers the tools already
            # computed. There is nothing to think about and everything to lose by
            # waiting, so ask for the least thinking the model allows.
            config["thinkingConfig"] = thinking
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": declarations(tool_schema)}],
            "generationConfig": config,
        }
        try:
            response = _post(body)
        except GeminiError as exc:
            # A rejected thinking field comes back as a bare "Request contains an
            # invalid argument" that names no argument, so this keys on the status
            # rather than the wording. thinkingConfig is the only thing here a
            # model can refuse this way; a 400 for any other reason exhausts the
            # ladder and raises, which is what we want anyway.
            if "HTTP 400" not in str(exc):
                raise
            log.info("gemini %s rejected thinkingConfig=%s", name, thinking)
            last = exc
            continue
        _ACCEPTED[name] = thinking
        return response
    raise last  # type: ignore[misc]


def _post(body: dict, _retries: int = 1) -> dict:
    """One POST, with a single short retry on 503.

    "This model is currently experiencing high demand" is the one failure here
    that is usually over before the user notices — unlike a 429, which needs the
    quota window to roll and is better spent falling back. One retry is the whole
    policy: a second wait costs more than the scripted answer is worth.
    """
    key = api_key()
    if not key:
        raise GeminiError("no GEMINI_API_KEY")
    url = f"{BASE_URL}/models/{model()}:generateContent"
    request = urllib.request.Request(
        url,
        data=json.dumps(body, default=str).encode(),
        headers={"Content-Type": "application/json", "X-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code == 503 and _retries > 0:
            log.info("gemini 503, retrying once")
            time.sleep(1.5)
            return _post(body, _retries - 1)
        raise GeminiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GeminiError(f"unreachable: {exc.reason}") from exc


def parts_of(response: dict) -> list[dict]:
    """The first candidate's parts, or an explanation of why there are none."""
    candidates = response.get("candidates") or []
    if not candidates:
        feedback = response.get("promptFeedback") or {}
        raise GeminiError(f"no candidates (promptFeedback={feedback})")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    if not parts:
        raise GeminiError(f"empty candidate (finishReason={candidate.get('finishReason')})")
    # A truncated turn is a failure, not a short answer: the caller would hand a
    # half-finished sentence to someone deciding what to do with their money, and
    # the scripted router's complete one is right there. Raising takes it.
    if candidate.get("finishReason") == "MAX_TOKENS":
        raise GeminiError("hit maxOutputTokens before finishing the reply")
    return parts
