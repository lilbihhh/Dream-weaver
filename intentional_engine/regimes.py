"""Auditable, pure regime decision logic; this module has no actuator interface."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .metrics import BroadcastCalibration, CoherenceCalibration


class Regime(str, Enum):
    CONSOLIDATION = "Consolidation"
    EXPANSION = "Expansion"
    STABILIZATION = "Stabilization"
    SAFE_STATE = "Safe-State"


@dataclass(frozen=True)
class RegimeDecision:
    regime: Regime
    reason_code: str
    adaptive_proposal: str | None = None


def select_regime(
    coherence: float,
    broadcast: float,
    safety_flags: Mapping[str, bool],
    consent_state: str,
    context: str,
    coherence_calibration: CoherenceCalibration = CoherenceCalibration(),
    broadcast_calibration: BroadcastCalibration = BroadcastCalibration(),
) -> RegimeDecision:
    """Select a simulation regime. Unsafe inputs resolve to Safe-State fail-closed."""
    required = ("input_valid", "input_fresh", "liberty_ok", "stop_requested", "arousal_ok")
    if (not isinstance(safety_flags, Mapping) or any(k not in safety_flags or type(safety_flags[k]) is not bool for k in required)
            or not all(safety_flags[k] for k in ("input_valid", "input_fresh", "liberty_ok", "arousal_ok"))
            or safety_flags["stop_requested"] or consent_state != "granted"):
        return RegimeDecision(Regime.SAFE_STATE, "REGIME_INPUT_UNSAFE")
    if context not in {"CoreLayer", "AdaptiveLayer"}:
        return RegimeDecision(Regime.SAFE_STATE, "CONTEXT_INVALID")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in (coherence, broadcast)):
        return RegimeDecision(Regime.SAFE_STATE, "METRIC_INVALID")
    if coherence <= coherence_calibration.collapse_threshold:
        return RegimeDecision(Regime.SAFE_STATE, "COHERENCE_COLLAPSE")
    if context == "AdaptiveLayer" and coherence >= 0.70 and broadcast >= broadcast_calibration.expansion_threshold:
        return RegimeDecision(Regime.EXPANSION, "ADAPTIVE_HIGH_COHERENCE_DENSITY", "ADAPTIVE_REVIEW_ONLY")
    if coherence < 0.50 or not safety_flags["arousal_ok"]:
        return RegimeDecision(Regime.STABILIZATION, "COHERENCE_OR_AROUSAL_CAUTION")
    return RegimeDecision(Regime.CONSOLIDATION, "CORE_CONSOLIDATION" if context == "CoreLayer" else "ADAPTIVE_CONSOLIDATION")
