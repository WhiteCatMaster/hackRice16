"""A model key the user brought with them, good for exactly one turn.

`/api/chat` normally answers with whatever key is in the server's `.env`. That is
fine for the team's own laptop and useless for anyone else: a judge, a teammate
on the train, or a phone on someone else's wifi has no key on our machine and no
way to put one there. So the client may send its own with the request:

    X-Model-Provider: gemini | anthropic | openai
    X-Model-Key:      the key itself
    X-Model-Name:     optional, the model to use
    X-Model-Base-URL: optional, an OpenAI-compatible endpoint

What the key is *not*: persisted. Nothing here writes to disk, to the sqlite
cache or to a log line. It lives in the `Credential` for the length of the turn
and is garbage two statements after the reply is built. The device that sent it
is the only thing that remembers it — `mobile/lib/secrets.ts` and
`frontend/lib/model-key.ts` are the two stores, and both are the user's own.

Headers rather than the body, for one reason: a body is the thing most likely to
end up echoed into an error message or a debug print. A header is not, and
neither of the transports we speak puts a key in a URL either — Gemini takes
`X-goog-api-key`, OpenAI takes `Authorization`.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

#: Lowercase, because every header map we read from is case-insensitive except
#: the plain dict the tests pass in.
HEADER_PROVIDER = "x-model-provider"
HEADER_KEY = "x-model-key"
HEADER_MODEL = "x-model-name"
HEADER_BASE_URL = "x-model-base-url"

HEADERS = (HEADER_PROVIDER, HEADER_KEY, HEADER_MODEL, HEADER_BASE_URL)

PROVIDERS = ("gemini", "anthropic", "openai")

#: Long enough for every key any of the three issues today, short enough that a
#: pasted file cannot arrive as one.
MAX_KEY = 400
MAX_MODEL = 120

#: How each provider's keys start, where that is distinctive enough to go on.
#: Only used when the client did not say which provider it meant — a paste into
#: the wrong field is the likeliest mistake here, and this catches it before it
#: becomes a 401 the user cannot explain.
PREFIXES = (
    ("sk-ant-", "anthropic"),
    ("AIza", "gemini"),
    ("sk-", "openai"),
)


class BadKey(ValueError):
    """The client sent something that cannot be a key. Answer 400, not 500."""


@dataclass(frozen=True)
class Credential:
    """One user's model access, for one request."""

    provider: str
    key: str
    model: str | None = None
    base_url: str | None = None

    def redacted(self) -> str:
        """The key as it is safe to say out loud — for an error, never a log."""
        return f"…{self.key[-4:]}" if len(self.key) > 8 else "…"

    def __repr__(self) -> str:  # pragma: no cover - a guard, not a feature
        # The default dataclass repr prints every field, which is how a key ends
        # up in a traceback. This one cannot.
        return f"Credential(provider={self.provider!r}, key={self.redacted()!r})"


def _get(headers, name: str) -> str:
    """One header, however the caller's map spells it."""
    if headers is None:
        return ""
    value = None
    # http.client.HTTPMessage and Starlette's Headers are both case-insensitive
    # and both answer .get(); a plain dict from a test is not, so try the
    # lowercase name and then walk the items.
    try:
        value = headers.get(name)
    except AttributeError:
        value = None
    if value is None:
        try:
            items = headers.items()
        except AttributeError:
            items = []
        for key, candidate in items:
            if str(key).lower() == name:
                value = candidate
                break
    return (value or "").strip()


def infer_provider(key: str) -> str | None:
    for prefix, provider in PREFIXES:
        if key.startswith(prefix):
            return provider
    return None


def _clean_key(raw: str) -> str:
    key = raw.strip()
    if not key:
        raise BadKey("The key is empty.")
    if len(key) > MAX_KEY:
        raise BadKey(f"That is longer than a key ({len(key)} characters).")
    # An API key is printable ASCII with no spaces. Anything else is a paste
    # accident — a whole .env file, a curl command, a newline from the clipboard
    # — and sending it on would only turn into a 401 the user cannot read.
    if not all(33 <= ord(char) <= 126 for char in key):
        raise BadKey("A key has no spaces or line breaks in it. Check the paste.")
    return key


def _clean_base_url(raw: str) -> str | None:
    """An OpenAI-compatible endpoint, if the client named one.

    The rule is https, or http only to this machine. A model server running on
    localhost is a real thing people do — Ollama, llama.cpp, LM Studio — and
    worth supporting; letting a request name any http host would make this
    backend a way to reach whatever else is on its network, which is not.
    """
    if not raw:
        return None
    url = raw.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BadKey("The model endpoint must be an http(s) URL.")
    local = parts.hostname in ("localhost", "127.0.0.1", "::1", "[::1]")
    if parts.scheme == "http" and not local:
        raise BadKey("Use https for a model endpoint that is not on this machine.")
    return url


def from_headers(headers) -> Credential | None:
    """The credential this request carries, or None if it carries none.

    Raises BadKey on something that is present but unusable, so the caller can
    say which of the two it is. "No key" means answer with the server's own
    setup; "bad key" means tell the user, because they just typed it.
    """
    raw_key = _get(headers, HEADER_KEY)
    provider = _get(headers, HEADER_PROVIDER).lower()
    if not raw_key:
        if provider:
            raise BadKey(f"A provider ({provider}) with no key.")
        return None

    key = _clean_key(raw_key)
    if not provider:
        provider = infer_provider(key) or ""
        if not provider:
            raise BadKey(
                "Could not tell which provider that key is for. Send "
                f"{HEADER_PROVIDER}: {' | '.join(PROVIDERS)}.")
    if provider not in PROVIDERS:
        raise BadKey(f"Unknown provider {provider!r}. One of: {', '.join(PROVIDERS)}.")

    model = _get(headers, HEADER_MODEL)[:MAX_MODEL] or None
    base_url = _clean_base_url(_get(headers, HEADER_BASE_URL))
    if base_url and provider != "openai":
        # Gemini and Anthropic both have one endpoint each, configured in .env.
        # Silently ignoring the field would leave someone waiting for a local
        # model that was never called.
        raise BadKey("A custom endpoint only applies to the openai provider.")

    return Credential(provider=provider, key=key, model=model, base_url=base_url)
