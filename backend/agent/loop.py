"""The agent loop.

Two modes, chosen by whether there is an API key:

- **llm** — Claude with the tools in `tools.py`. The model picks tools and writes
  the prose; every number in the reply came out of a tool result.
- **scripted** — no key, no network. Routes the question to the same tools by
  keyword and formats the answer from the same numbers.

The scripted mode is not a toy. begin.md's design rule 3 says the demo must not
depend on a live service, and an LLM API is one more thing that can be down or
rate-limited at 9 a.m. on stage. Both modes answer the §9 demo questions with
real numbers, and `/api/health` says which one is running.
"""

from __future__ import annotations

import json
import logging
import os
import re

from backend.agent import prompts, tools
from backend.nessie import repo

log = logging.getLogger("landed.agent")

MODEL = os.environ.get("LANDED_MODEL", "claude-sonnet-5")
MAX_TURNS = 6
MAX_TOKENS = 1024


def _api_key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def status() -> dict:
    key = bool(_api_key())
    try:
        import anthropic  # noqa: F401
        sdk = True
    except ImportError:
        sdk = False
    mode = "llm" if (key and sdk) else "scripted"
    return {
        "mode": mode,
        "model": MODEL if mode == "llm" else None,
        "anthropic_sdk": sdk,
        "api_key_present": key,
        "tools": [t["name"] for t in tools.SCHEMA],
        "note": (
            "Claude picks the tools and writes the prose. Numbers come from tool results only."
            if mode == "llm" else
            "No ANTHROPIC_API_KEY, so replies are composed by the scripted router. "
            "Same tools, same numbers, no model."
        ),
    }


def answer(conn, user: str, message: str, language: str | None = None) -> dict:
    if status()["mode"] == "llm":
        try:
            return _llm(conn, user, message, language)
        except Exception as exc:  # the demo must survive a dead or throttled API
            log.warning("LLM turn failed (%s); falling back to the scripted router", exc)
            out = _scripted(conn, user, message, language)
            out["_fell_back"] = str(exc)
            return out
    return _scripted(conn, user, message, language)


# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------


def _llm(conn, user: str, message: str, language: str | None) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=_api_key())
    system = prompts.system(conn, user, language)
    history = [{"role": "user", "content": message}]
    used: list[str] = []
    proposed = None

    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system,
            tools=tools.SCHEMA, messages=history,
        )
        history.append({"role": "assistant", "content": response.content})

        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return _reply(conn, user, text, used, proposed, language)

        results = []
        for call in calls:
            used.append(call.name)
            try:
                output = tools.run(conn, user, call.name, dict(call.input))
            except Exception as exc:
                log.warning("tool %s failed: %s", call.name, exc)
                output = {"error": str(exc)}
            if call.name.startswith("propose_") and not output.get("error"):
                proposed = output
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(output, default=str),
            })
        history.append({"role": "user", "content": results})

    return _reply(conn, user, "I need more information to answer that safely.", used, proposed, language)


# --------------------------------------------------------------------------
# scripted router
# --------------------------------------------------------------------------

AMOUNT = re.compile(r"(?:\$|usd\s*)?(\d[\d,]*(?:\.\d{1,2})?)\s*(?:\$|dollars|dólares|usd|eur|€)?", re.I)

WORDS = {
    "afford": ("afford", "permitir", "permito", "puedo gastar", "can i spend", "can i go",
               "ir a", "viaje", "trip", "buy", "comprar", "cost", "cuesta"),
    "bills": ("bill", "factura", "recibo", "subscription", "suscripc", "rent", "alquiler",
              "renta", "charge", "cobro", "trial", "prueba"),
    "credit": ("credit", "crédito", "credito", "card", "tarjeta", "score", "utilization",
               "utilizaci", "puntaje"),
    "alerts": ("alert", "alerta", "fraud", "fraude", "scam", "estafa", "suspicious", "sospechos"),
    "activity": ("spent", "gasté", "gaste", "recent", "reciente", "transaction", "transacc",
                 "movimiento", "where did", "en qué", "en que"),
    "fixes": ("fix", "arreglar", "help", "ayuda", "what should", "qué hago", "que hago",
              "advice", "consejo", "shortfall", "gap", "no llego", "run out", "quedo sin"),
    "transfer": ("transfer", "transferir", "transferencia", "move", "mover", "pasar",
                 "send money", "enviar dinero"),
}


ES_MARKS = re.compile(r"[¿¡ñáéíóú]", re.I)
ES_WORDS = re.compile(
    r"\b(qué|que|cuánto|cuanto|puedo|permitirme|dinero|tarjeta|cómo|como|hago|para|"
    r"tengo|mis|mi|el|la|los|las|del|una|por|con|estafa|recibos|gasto|finde|semana)\b", re.I)
EN_WORDS = re.compile(
    r"\b(the|my|how|what|can|i|is|are|do|much|money|card|should|afford|week|weekend|"
    r"bills|spend|going|doing)\b", re.I)


def detect_language(message: str, fallback: str = "en") -> str:
    """Match the language they wrote in; fall back to the persona's own."""
    if ES_MARKS.search(message):
        return "es"
    es, en = len(ES_WORDS.findall(message)), len(EN_WORDS.findall(message))
    if es > en:
        return "es"
    if en > es:
        return "en"
    return fallback


def _hit(text: str, key: str) -> bool:
    return any(word in text for word in WORDS[key])


def _money(value) -> str:
    """Negative money reads as -$12.00, never as $-12.00."""
    value = float(value)
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def _fix_label(fix: dict, es: bool) -> str:
    """A fix's label in the reply's language.

    Only rendered locally where the fix carries the parts as fields — transfers
    give us `amount`, `from` and `to`, so the number is substituted verbatim and
    never goes near a model. A category cap keeps its English label because the
    category and the weekly figure exist only inside that string, and picking
    them back out with a regex is the same guessing that lost the cap line in the
    first place. When the engine publishes `label_parts`, render the rest here.
    """
    label = fix.get("label") or ""
    if not es:
        return label
    if fix.get("type") == "transfer" and fix.get("amount"):
        source = "ahorros" if fix.get("from") in (None, "savings") else fix["from"]
        return f"Mover {_money(fix['amount'])} de {source}"
    return label


def _lasts_phrase(runway_date, es: bool) -> str:
    """How far the money reaches, as a phrase that reads either way.

    The engine returns null for "never runs short before the flight", which is
    the best possible answer — but interpolated raw it renders as "hasta None" on
    the approval card, the one beat the whole demo is built around. The
    preposition lives in here so both branches read as English (and Spanish).
    """
    if runway_date:
        return f"hasta el {runway_date}" if es else f"to {runway_date}"
    return "más allá de tu vuelo de vuelta" if es else "past your flight home"


def _amount_in(text: str) -> float | None:
    matches = AMOUNT.findall(text)
    values = []
    for raw in matches:
        try:
            values.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    values = [v for v in values if v >= 5]
    return max(values) if values else None


def _scripted(conn, user: str, message: str, language: str | None) -> dict:
    text = message.lower()
    persona_language = (repo.resolve_customer(conn, user) or {}).get("language") or "en"
    lang = language or detect_language(message, persona_language)
    es = lang.startswith("es")
    used: list[str] = []
    proposed = None

    def tool(name, args=None):
        used.append(name)
        return tools.run(conn, user, name, args or {})

    # "Can I afford X?" — the §9 demo question.
    if _hit(text, "afford"):
        amount = _amount_in(text)
        summary = tool("get_summary")
        if amount is None:
            afford = tool("suggest_fixes")
            reply = (
                f"Depende de cuánto cueste. Ahora mismo tu dinero llega hasta el "
                f"{summary['runway_date']} y vuelas a casa el {summary['target_date']}, "
                f"así que te faltan {_money(summary['gap'])}. Dime el importe y lo calculo."
                if es else
                f"It depends on the amount. Right now your money lasts until "
                f"{summary['runway_date']} and you fly home on {summary['target_date']}, "
                f"so you are {_money(summary['gap'])} short. Tell me the amount and I'll check it."
            )
            return _reply(conn, user, reply, used, None, lang)

        check = tool("check_affordability", {"amount": amount})

        # The engine writes a better sentence than this router can, and it is
        # written from the same numbers it just computed — so prefer it where the
        # language matches. It is English-only, so Spanish keeps the template.
        if not es and check.get("reason"):
            reply = check["reason"]
            if not check["affordable"]:
                fixes = tool("suggest_fixes")["fixes"]
                transfer = next((f for f in fixes if f["type"] == "transfer"), None)
                if transfer:
                    proposed = tool("propose_transfer", {
                        "amount": transfer["amount"], "from": "savings",
                        "to": "checking", "label": transfer["label"]})
            return _reply(conn, user, reply, used, proposed, lang)

        if check["affordable"]:
            reply = (
                f"Sí. Gastar {_money(amount)} te deja en {_money(check['min_balance_after'])} "
                f"en tu punto más bajo, y tu dinero sigue llegando "
                f"{_lasts_phrase(check.get('runway_date_after'), True)}."
                if es else
                f"Yes. Spending {_money(amount)} leaves you at "
                f"{_money(check['min_balance_after'])} at your lowest point, and your money "
                f"still lasts {_lasts_phrase(check.get('runway_date_after'), False)}."
            )
        else:
            reply = (
                f"Ahora mismo no. Gastar {_money(amount)} adelanta el día en que te quedas "
                f"sin margen del {check['runway_date_before']} al "
                f"{check.get('runway_date_after') or summary['target_date']}, "
                f"y vuelas a casa el {summary['target_date']}. Puedo proponerte cómo cubrirlo."
                if es else
                f"Not right now. Spending {_money(amount)} moves the day you run short from "
                f"{check['runway_date_before']} to "
                f"{check.get('runway_date_after') or summary['target_date']}, "
                f"and you fly home on {summary['target_date']}. I can propose a way to cover it."
            )
            fixes = tool("suggest_fixes")["fixes"]
            transfer = next((f for f in fixes if f["type"] == "transfer"), None)
            if transfer:
                proposed = tool("propose_transfer", {
                    "amount": transfer["amount"], "from": "savings",
                    "to": "checking", "label": transfer["label"]})
        return _reply(conn, user, reply, used, proposed, lang)

    # "What should I do?" — the action card in §9.
    if _hit(text, "fixes") or _hit(text, "transfer"):
        summary = tool("get_summary")
        fixes = tool("suggest_fixes")["fixes"]
        if not fixes:
            reply = ("Vas bien: tu dinero llega hasta el vuelo de vuelta sin cambios."
                     if es else "You're fine — your money reaches your flight home as things stand.")
            return _reply(conn, user, reply, used, None, lang)

        amount = _amount_in(text)

        # Select by the engine's own notion of the plan, not by type name. P2 calls
        # the cap `category_cap` while the reference calls it `spending_cap`, and
        # matching one name silently dropped the second line of the action card —
        # the line that is the entire reason the demo has two fixes.
        plan = [f for f in fixes if f.get("in_plan")]
        pool = plan or fixes
        transfer = (next((f for f in pool if f.get("type") == "transfer"), None)
                    or next((f for f in fixes if f.get("type") == "transfer"), None))
        cap = next((f for f in pool if f is not transfer), None)
        if transfer and amount:
            transfer = {**transfer, "amount": amount, "label": f"Move ${amount:,.0f} from savings to checking"}

        lines = [
            f"Te faltan {_money(summary['gap'])} para llegar al {summary['target_date']}."
            if es else
            f"You are {_money(summary['gap'])} short of reaching {summary['target_date']}."
        ]

        # Propose first, and quote the *proposal's* measured effect rather than the
        # one advertised on the fix. They are not always the same number, and the
        # proposal's is what the approval card shows — so saying anything else puts
        # the chat and the card in contradiction on the one beat that matters.
        if transfer:
            proposed = tool("propose_transfer", {
                "amount": transfer["amount"], "from": "savings",
                "to": "checking", "label": transfer["label"]})
            effect = proposed.get("effect") or {}
            after = effect.get("runway_date_after")
            still_short = float(effect.get("gap_after") or 0)

            spoken = _fix_label(transfer, es)
            if effect.get("measured") is False:
                lines.append(
                    f"{spoken}: no he podido medir el efecto."
                    if es else
                    f"{spoken}: I could not measure the effect of that.")
            else:
                lasts = _lasts_phrase(after, es)
                lines.append(
                    f"{spoken}: tu dinero duraría {lasts}."
                    if es else
                    f"{spoken}: that alone stretches you {lasts}.")
                if still_short > 0:
                    lines.append(
                        f"Aun así te faltarían {_money(still_short)}."
                        if es else
                        f"That still leaves you {_money(still_short)} short.")

        if cap:
            # The engine carries the *combined* outcome on each step of the plan
            # (`effect_with_plan`), so the payoff can be a measured number rather
            # than an unbacked "covers the rest". Only claim it clears the gap if
            # the engine says it does.
            plan = cap.get("effect_with_plan") or {}
            if plan.get("clears_the_gap"):
                lasts = _lasts_phrase(plan.get("runway_date_after"), es)
                lines.append(
                    f"{_fix_label(cap, es)} también, y juntos tu dinero duraría {lasts}."
                    if es else
                    f"{_fix_label(cap, es)} too, and together they stretch you {lasts}.")
            else:
                lines.append(
                    f"Y {cap['label'].lower()} cubre el resto."
                    if es else f"And {cap['label'].lower()} covers the rest.")
        lines.append("Nada se mueve hasta que lo apruebes." if es
                     else "Nothing moves until you approve it.")
        return _reply(conn, user, " ".join(lines), used, proposed, lang)

    if _hit(text, "alerts"):
        found = tool("get_alerts")["alerts"]
        if not found:
            reply = ("No tienes alertas abiertas ahora mismo." if es
                     else "You have no open alerts right now.")
        else:
            first = found[0]
            reply = (
                f"Tienes {len(found)} alerta(s). La más reciente: {first['title'].lower()} de "
                f"{_money(first['amount'])} — {first['reason']}."
                if es else
                f"You have {len(found)} alert(s). Most recent: {first['title'].lower()} for "
                f"{_money(first['amount'])} — {first['reason']}.")
        return _reply(conn, user, reply, used, None, lang)

    if _hit(text, "credit"):
        card = tool("get_credit")
        reply = (
            f"Tu tarjeta tiene {_money(card['balance'])} de un límite de {_money(card['limit'])}, "
            f"un {card['utilization']:.0%}. Pagar {_money(card['suggested_payment'])} la bajaría "
            f"por debajo del 30 %, que es lo que premia el sistema de crédito de EE. UU. "
            f"(El límite es simulado: la API del banco no lo expone.)"
            if es else
            f"Your card is at {_money(card['balance'])} of a {_money(card['limit'])} limit, "
            f"{card['utilization']:.0%}. {card['tip']} (The limit is simulated — the bank API "
            f"has no such field.)")
        return _reply(conn, user, reply, used, None, lang)

    if _hit(text, "bills"):
        found = tool("get_bills")["bills"]
        upcoming = found[:3]
        listed = ", ".join(f"{b['nickname']} {_money(b['amount'])} el {b['next_date']}" if es
                           else f"{b['nickname']} {_money(b['amount'])} on {b['next_date']}"
                           for b in upcoming)
        trial = next((b for b in found if b.get("heads_up")), None)
        reply = (f"Tus próximos recibos: {listed}." if es else f"Your next bills: {listed}.")
        if trial:
            reply += (f" Ojo: {trial['heads_up']}." if es else f" Heads up: {trial['heads_up']}.")
        return _reply(conn, user, reply, used, None, lang)

    if _hit(text, "activity"):
        items = tool("get_activity", {"limit": 5})["items"]
        listed = ", ".join(f"{i['label']} {_money(abs(i['amount']))}" for i in items[:4])
        reply = (f"Tus últimos movimientos: {listed}." if es
                 else f"Your most recent transactions: {listed}.")
        return _reply(conn, user, reply, used, None, lang)

    # Default: the dashboard in one sentence.
    summary = tool("get_summary")
    checking = next((a for a in summary["accounts"] if a["type"] == "Checking"), None)
    reply = (
        f"Tienes {_money(checking['balance'])} en la cuenta corriente. A tu ritmo actual "
        f"({_money(summary['daily_burn'])} al día) te llega hasta el {summary['runway_date']}, "
        f"y vuelas a casa el {summary['target_date']}: te faltan {_money(summary['gap'])}. "
        f"Pregúntame qué hacer y te lo propongo."
        if es else
        f"You have {_money(checking['balance'])} in checking. At your current rate "
        f"({_money(summary['daily_burn'])} a day) that lasts until {summary['runway_date']}, "
        f"and you fly home on {summary['target_date']} — you are {_money(summary['gap'])} short. "
        f"Ask me what to do and I'll propose something."
    )
    return _reply(conn, user, reply, used, None, lang)


def _reply(conn, user, text, used, proposed, language) -> dict:
    out = {
        "reply": text,
        "language": (language or (repo.resolve_customer(conn, user) or {}).get("language") or "en"),
        "used_tools": used,
        "proposed_action": None,
        "_mode": status()["mode"],
    }
    if proposed:
        out["proposed_action"] = {
            "id": proposed["id"],
            "type": proposed["type"],
            "from": proposed.get("from"),
            "to": proposed.get("to"),
            "amount": proposed["amount"],
            "label": proposed.get("label"),
            "effect": proposed.get("effect"),
        }
    return out
