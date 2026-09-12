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
import urllib.error
import urllib.request

from backend.nessie import config  # noqa: F401  — importing it loads .env

log = logging.getLogger("treasurer.agent.gemini")

BASE_URL = os.environ.get(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")
TIMEOUT = 30.0
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

def generate(system: str, contents: list[dict], tool_schema: list[dict],
             max_tokens: int = 2048) -> dict:
    """One `:generateContent` call. Raises GeminiError on anything but a 200."""
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "tools": [{"functionDeclarations": declarations(tool_schema)}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
            # gemini-flash-latest thinks by default, and thinking is billed out of
            # maxOutputTokens — a long think returns finishReason MAX_TOKENS with
            # zero text parts. This is a two-sentence answer over tool results, so
            # there is nothing to think about and everything to lose by waiting.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        return _post(body)
    except GeminiError as exc:
        # Models that cannot turn thinking off reject the field with a bare
        # "Request contains an invalid argument" — the response never says which
        # argument, so the retry keys on the status, not on the wording. Dropping
        # thinkingConfig is the only thing here a model can refuse this way, and a
        # 400 for any other reason simply fails again below.
        if "HTTP 400" not in str(exc) or "thinkingConfig" not in json.dumps(body):
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        # Thinking is billed out of maxOutputTokens, so a budget sized for two
        # sentences of prose now has to cover the reasoning as well. Left at
        # 1024 the answer comes back cut off mid-sentence — "your flight home on
        # 202" — which is worse than no answer at all when the sentence is about
        # someone's money.
        body["generationConfig"]["maxOutputTokens"] = max(max_tokens, THINKING_TOKENS)
        return _post(body)


def _post(body: dict) -> dict:
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
