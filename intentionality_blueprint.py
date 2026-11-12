"""Simulation section: run synthetic Intentionality Engine policy passes.

This blueprint is a thin Flask adapter over the vendored engine in
:mod:`intentional_engine`. A form collects synthetic, observable inputs, the
canonical policy graph (Observe → Estimate → Propose → SafetyGovernor →
SelectRegime → EmitAudit) runs offline, and the resulting event is appended to a
local JSONL NEXUS ledger after strict schema validation.

The section is non-actuating: no envelope, stimulation parameter or device
command is ever produced, and every audit event carries ``envelope_id: null``.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from dreamweaver_enhanced import ValidationError
from intentional_engine import run_policy

RECENT_EVENTS_LIMIT = 10
CONTEXTS = ("CoreLayer", "AdaptiveLayer")
CONSENT_STATES = ("granted", "withdrawn")
TRUE_VALUES = {"on", "true", "1", "yes"}
FALSE_VALUES = {"", "off", "false", "0", "no"}

simulation_bp = Blueprint("simulation", __name__)


def default_ledger_path() -> Path:
    """Resolve the NEXUS ledger location (env override, then a persistent dir)."""
    configured = os.environ.get("DREAMWEAVER_NEXUS_LEDGER")
    if configured:
        return Path(configured)
    data_dir = Path("/data")
    if data_dir.is_dir():
        return data_dir / "nexus_ledger.jsonl"
    return Path("nexus_ledger.jsonl")


def _ledger_path() -> Path:
    return Path(current_app.config["NEXUS_LEDGER"])


def _flag(form: Any, name: str) -> bool:
    raw = (form.get(name) or "").strip().lower()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    raise ValidationError(f"'{name}' must be a yes/no value.")


def _unit(form: Any, name: str, label: str) -> float:
    raw = (form.get(name) or "").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValidationError(f"{label} must be a number between 0 and 1.") from exc
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValidationError(f"{label} must be a number between 0 and 1.")
    return value


def _choice(form: Any, name: str, allowed: tuple[str, ...], label: str) -> str:
    value = (form.get(name) or "").strip()
    if value not in allowed:
        raise ValidationError(f"{label} must be one of: {', '.join(allowed)}.")
    return value


def read_form(form: Any) -> dict[str, Any]:
    """Translate the synthetic form into a policy-graph input state."""
    arousal = _unit(form, "arousal", "Arousal")
    arousal_max = _unit(form, "arousal_max", "Arousal ceiling")
    return {
        "consent_state": _choice(form, "consent_state", CONSENT_STATES, "Consent"),
        "consent_override": False,
        "input_valid": _flag(form, "input_valid"),
        "input_fresh": _flag(form, "input_fresh"),
        "liberty_ok": _flag(form, "liberty_ok"),
        "stop_requested": _flag(form, "stop_requested"),
        # The bound is explicit in the form, so the governor's arousal flag is
        # derived from the entered values rather than asserted separately.
        "arousal_ok": arousal <= arousal_max,
        "arousal": arousal,
        "arousal_max": arousal_max,
        "coherence": _unit(form, "coherence", "Coherence C(S)"),
        "broadcast": _unit(form, "broadcast", "Broadcast density I"),
        "context": _choice(form, "context", CONTEXTS, "Context"),
    }


def read_recent_events(path: Path, limit: int = RECENT_EVENTS_LIMIT) -> list[dict[str, Any]]:
    """Return the newest schema-shaped ledger events, newest first."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(events[-limit:]))


@simulation_bp.route("/simulation", methods=["GET", "POST"])
def simulation():
    ledger = _ledger_path()
    if request.method == "POST":
        inputs = read_form(request.form)
        result = run_policy(inputs, ledger)
        session["simulation_result"] = {
            "safety_decision": result["safety_decision"],
            "regime": result["regime"],
            "reason_code": result["reason_code"],
            "adaptive_proposal": result.get("adaptive_proposal"),
            "envelope_id": result.get("envelope_id"),
            "event": result["audit_event"],
            "inputs": inputs,
        }
        return redirect(url_for("simulation.simulation"))

    stored = session.pop("simulation_result", None)
    return render_template(
        "simulation.html",
        result=stored,
        form=stored["inputs"] if stored else None,
        events=read_recent_events(ledger),
        ledger_path=str(ledger),
        contexts=CONTEXTS,
        consent_states=CONSENT_STATES,
    )
