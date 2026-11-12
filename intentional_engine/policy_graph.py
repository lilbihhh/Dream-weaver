"""Canonical offline, non-actuating policy control flow (Intentionality Engine).

Vendored from ``lilbihhh/intentional-architecture`` at commit
``8035e2befd93d2f10947e708fc4a021cb1393c5a`` (see ``VENDORED.md``); the only
edits are package-relative imports and a configurable default ledger path. The
governor runs before regime selection and is re-evaluated afterward as the
final veto. The graph emits no actuator commands.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping
import uuid

from .metrics import BroadcastCalibration, CoherenceCalibration, broadcast_density, coherence_proxy
from .regimes import Regime, RegimeDecision, select_regime

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_LEDGER = Path(os.environ.get("NEXUS_LEDGER", str(PACKAGE_ROOT / "nexus_ledger.jsonl")))
SCHEMA_PATH = PACKAGE_ROOT / "schemas" / "audit-log.schema.json"


@dataclass(frozen=True)
class GovernorResult:
    allowed: bool
    reason_code: str


def _valid_unit(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1


def safety_governor(state: Mapping[str, Any]) -> GovernorResult:
    """Hard fail-closed gate; absent, malformed, contradictory data is a veto."""
    required_bools = ("input_valid", "input_fresh", "liberty_ok", "stop_requested", "consent_override", "arousal_ok")
    if any(key not in state or type(state[key]) is not bool for key in required_bools):
        return GovernorResult(False, "SAFETY_INPUT_MISSING_OR_INVALID")
    if state["consent_state"] != "granted" or state["consent_override"]:
        return GovernorResult(False, "CONSENT_NOT_EXPLICIT_OR_OVERRIDDEN")
    if state["stop_requested"]:
        return GovernorResult(False, "STOP_REQUESTED")
    if not state["input_valid"] or not state["input_fresh"] or not state["liberty_ok"]:
        return GovernorResult(False, "INPUT_OR_LIBERTY_CHECK_FAILED")
    if not _valid_unit(state.get("coherence")) or not _valid_unit(state.get("broadcast")):
        return GovernorResult(False, "METRIC_MISSING_OR_INVALID")
    if state["coherence"] <= state["coherence_collapse_threshold"]:
        return GovernorResult(False, "COHERENCE_COLLAPSE")
    if not _valid_unit(state.get("arousal")) or not _valid_unit(state.get("arousal_max")) or state["arousal"] > state["arousal_max"] or not state["arousal_ok"]:
        return GovernorResult(False, "AROUSAL_BOUND_VIOLATION")
    if state.get("context") not in {"CoreLayer", "AdaptiveLayer"}:
        return GovernorResult(False, "CONTEXT_MISSING_OR_INVALID")
    return GovernorResult(True, "SAFETY_ALLOW")


def _observe(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Observe only allow-listed, synthetic values; never retain arbitrary user text."""
    state = dict(raw)
    state.setdefault("consent_state", "unknown")
    state.setdefault("input_valid", False)
    state.setdefault("input_fresh", False)
    state.setdefault("liberty_ok", False)
    state.setdefault("stop_requested", False)
    state.setdefault("consent_override", False)
    state.setdefault("arousal_ok", False)
    state.setdefault("arousal_max", 0.8)
    state.setdefault("context", "")
    return state


def _estimate(state: dict[str, Any]) -> dict[str, Any]:
    if "coherence_features" in state:
        state["coherence"] = coherence_proxy(state["coherence_features"], state.get("coherence_calibration", CoherenceCalibration()))
    if "broadcast_features" in state:
        state["broadcast"] = broadcast_density(state["broadcast_features"], state.get("broadcast_calibration", BroadcastCalibration()))
    state["coherence_collapse_threshold"] = state.get("coherence_calibration", CoherenceCalibration()).collapse_threshold
    return state


def _propose(state: dict[str, Any]) -> dict[str, Any]:
    """Produce a symbolic proposal only; never parameters or device commands."""
    state["proposal"] = {"kind": "simulation_regime_candidate", "actuation": False}
    return state


def _safe_input_digest(state: Mapping[str, Any], reason: str) -> str:
    fields = {k: state.get(k) for k in ("consent_state", "input_valid", "input_fresh", "liberty_ok", "stop_requested", "consent_override", "arousal_ok", "arousal", "arousal_max", "coherence", "broadcast", "context")}
    # Normalize non-JSON values and exclude raw feature maps and all arbitrary strings.
    clean = {k: (v if isinstance(v, (str, bool, int, float)) and (not isinstance(v, float) or math.isfinite(v)) else None) for k, v in fields.items()}
    clean["reason_code"] = reason
    return hashlib.sha256(json.dumps(clean, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load_schema_validator():
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for strict NEXUS audit validation; install requirements.txt") from exc
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_event(event: Mapping[str, Any]) -> None:
    errors = sorted(_load_schema_validator().iter_errors(dict(event)), key=lambda err: list(err.path))
    if errors:
        raise ValueError(f"NEXUS event schema violation: {errors[0].message}")


def _append_audit(event: dict[str, Any], ledger_path: str | Path) -> dict[str, Any]:
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = None
    if path.exists() and path.stat().st_size:
        last_line = path.read_text(encoding="utf-8").splitlines()[-1]
        previous_hash = json.loads(last_line).get("event_hash")
    event["prev_hash"] = previous_hash
    event["event_hash"] = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    _validate_event(event)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
    return event


def run_policy(inputs: Mapping[str, Any] | None = None, ledger_path: str | Path | None = None) -> dict[str, Any]:
    """Run Observe → Estimate → Propose → Governor → SelectRegime → EmitAudit."""
    state = _observe(inputs if isinstance(inputs, Mapping) else {})
    try:
        state = _estimate(state)
        state = _propose(state)
        # First gate precedes all regime selection.
        first_gate = safety_governor(state)
        decision = RegimeDecision(Regime.SAFE_STATE, first_gate.reason_code)
        final_gate = first_gate
        if first_gate.allowed:
            decision = select_regime(
                state["coherence"], state["broadcast"],
                {k: state[k] for k in ("input_valid", "input_fresh", "liberty_ok", "stop_requested", "arousal_ok")},
                state["consent_state"], state["context"],
                state.get("coherence_calibration", CoherenceCalibration()),
                state.get("broadcast_calibration", BroadcastCalibration()),
            )
            # Final governor veto after decision; a regime proposal never authorizes itself.
            final_gate = safety_governor(state)
            if decision.regime is Regime.SAFE_STATE:
                final_gate = GovernorResult(False, decision.reason_code)
        regime = decision.regime.value if final_gate.allowed else Regime.SAFE_STATE.value
        reason = decision.reason_code if final_gate.allowed else final_gate.reason_code
        event = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_id": str(uuid.uuid4()),
            "regime": regime,
            "safety_decision": "ALLOW" if final_gate.allowed else "VETO",
            "intent_summary": "synthetic_policy_pass",
            "envelope_id": None,
            "inputs_hash": _safe_input_digest(state, reason),
            "notes": reason,
        }
        _append_audit(event, ledger_path or DEFAULT_LEDGER)
        return {"regime": regime, "reason_code": reason, "safety_decision": event["safety_decision"], "envelope_id": None, "adaptive_proposal": decision.adaptive_proposal if final_gate.allowed else None, "audit_event": event}
    except Exception:
        # Do not silently continue after computation or audit validation failures.
        raise


def run_governance_pass(intent: str = "synthetic_policy_pass", ledger_path: str | Path | None = None, **kwargs: Any) -> dict[str, Any]:
    """Compatibility wrapper; caller text is intentionally ignored and never audited."""
    return run_policy(kwargs or None, ledger_path)


if __name__ == "__main__":
    demo = {
        "consent_state": "granted", "consent_override": False,
        "input_valid": True, "input_fresh": True, "liberty_ok": True,
        "stop_requested": False, "arousal_ok": True, "arousal": 0.3,
        "arousal_max": 0.8, "coherence": 0.82, "broadcast": 0.25,
        "context": "CoreLayer",
    }
    print(json.dumps(run_policy(demo), indent=2))
