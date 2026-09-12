"""One seam between P3's API and P2's engine.

P2 owns `backend.engine`. Until it lands — or for any single function it has not
written yet — this falls back to `backend.api.reference`, P3's stand-in, which
reproduces P1's published projection.

Resolution is per function and re-checked on every call, so P2's engine takes
over as soon as the module imports cleanly. Nothing has to restart, and
`/api/health` reports which side answered each capability.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

from backend.api import reference

log = logging.getLogger("treasurer.engine")

#: Every capability the API needs, in the names P2 committed to.
CAPABILITIES = (
    "summary", "forecast", "bills", "credit", "affordability", "can_afford",
    "check_transfer", "alerts", "detect_anomalies", "activity", "profile",
    "suggest_fixes",
)

_warned: set[str] = set()


def _p2():
    """P2's engine module, or None while it does not import."""
    try:
        from backend import engine  # noqa: PLC0415 — deliberately late and re-tried
        return engine
    except Exception as exc:  # ImportError, or a half-written module mid-edit
        if "import" not in _warned:
            _warned.add("import")
            # A warning, not info: the reference reproduces P1's calibration but not
            # P2's full contract (no already_short, max_safe_through or days_gained),
            # so a demo that quietly lands here answers with thinner numbers than the
            # screens were built for. The engine also ships as sourceless .pyc built
            # for one Python version — run a different one and the import fails here
            # with nothing else to see. /api/health reports the same thing in
            # engine_module.
            log.warning(
                "backend.engine did not import (%s); falling back to P3's reference. "
                "Every number is now the reference projection, not P2's engine.", exc)
        return None


def resolve(name: str) -> tuple[Callable[..., Any], str]:
    """Return (function, owner) for a capability. P2 wins whenever it has one."""
    engine = _p2()
    fn = getattr(engine, name, None) if engine else None
    if callable(fn):
        return fn, "backend.engine"

    fallback = getattr(reference, name, None)
    if not callable(fallback):
        raise NotImplementedError(f"No engine or reference implementation for {name!r}")
    return fallback, "p3-reference"


def accepts(name: str, kwarg: str) -> bool:
    """Does whichever implementation is live take this keyword argument?

    Callers that would otherwise get a silently wrong answer (the confirmation
    gate measuring an action's effect with `extra_events`) ask first.
    """
    try:
        fn, _ = resolve(name)
        params = inspect.signature(fn).parameters
    except (NotImplementedError, TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return kwarg in params


def call(name: str, conn, *args, **kwargs):
    """Call a capability, dropping kwargs the implementation does not accept.

    P2 and the reference agree on names today. Tolerating a signature drift is
    cheaper than a 3 a.m. TypeError in the middle of the demo.
    """
    fn, owner = resolve(name)
    try:
        params = inspect.signature(fn).parameters
        if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            dropped = [k for k in kwargs if k not in params]
            for key in dropped:
                kwargs.pop(key)
            if dropped:
                log.warning(
                    "%s.%s does not accept %s — dropped. A caller relying on it must "
                    "check accepts() rather than trust the result.", owner, name, dropped)
    except (TypeError, ValueError):
        pass

    result = fn(conn, *args, **kwargs)
    if isinstance(result, dict):
        result.setdefault("_engine", owner)
    return result


def status() -> dict:
    """Who answers what, for /api/health. Honest about the fallback."""
    engine = _p2()
    owners = {}
    for name in CAPABILITIES:
        try:
            owners[name] = resolve(name)[1]
        except NotImplementedError:
            owners[name] = "missing"
    live = sorted(n for n, o in owners.items() if o == "backend.engine")
    return {
        "engine_module": "backend.engine" if engine else None,
        "capabilities": owners,
        "from_p2": live,
        "from_reference": sorted(n for n, o in owners.items() if o == "p3-reference"),
        "note": (
            "P2's engine is live for the capabilities listed in from_p2."
            if live else
            "P2's engine is not loaded. Every number below comes from P3's reference "
            "projection, which reproduces P1's published calibration."
        ),
    }
