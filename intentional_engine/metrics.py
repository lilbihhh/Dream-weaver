"""Pure, bounded simulation metrics. Values are software proxies, never neural measurements."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


@dataclass(frozen=True)
class CoherenceCalibration:
    weights: tuple[float, float, float, float] = (0.35, 0.30, 0.20, 0.15)
    collapse_threshold: float = 0.20

    def __post_init__(self) -> None:
        if len(self.weights) != 4 or any(not math.isfinite(w) or w < 0 for w in self.weights):
            raise ValueError("coherence weights must be four finite nonnegative numbers")
        if not math.isclose(sum(self.weights), 1.0, abs_tol=1e-9):
            raise ValueError("coherence weights must sum to 1")
        _unit(self.collapse_threshold, "collapse_threshold")


@dataclass(frozen=True)
class BroadcastCalibration:
    weights: tuple[float, float, float] = (0.50, 0.30, 0.20)
    expansion_threshold: float = 0.65

    def __post_init__(self) -> None:
        if len(self.weights) != 3 or any(not math.isfinite(w) or w < 0 for w in self.weights):
            raise ValueError("broadcast weights must be three finite nonnegative numbers")
        if not math.isclose(sum(self.weights), 1.0, abs_tol=1e-9):
            raise ValueError("broadcast weights must sum to 1")
        _unit(self.expansion_threshold, "expansion_threshold")


def _unit(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    return float(value)


def coherence_proxy(features: Mapping[str, float], calibration: CoherenceCalibration = CoherenceCalibration()) -> float:
    """Compute C(S) from four declared, normalized software-summary features.

    Required keys are consistency, continuity, provenance, and agreement. Missing or
    malformed data raises ValueError rather than manufacturing a default estimate.
    """
    keys = ("consistency", "continuity", "provenance", "agreement")
    if not isinstance(features, Mapping) or any(key not in features for key in keys):
        raise ValueError("all coherence features are required")
    values = tuple(_unit(features[key], key) for key in keys)
    return min(1.0, max(0.0, sum(w * v for w, v in zip(calibration.weights, values))))


def broadcast_density(features: Mapping[str, float], calibration: BroadcastCalibration = BroadcastCalibration()) -> float:
    """Compute normalized I_broadcast from semantic, motor-label, and recurrence proxies."""
    keys = ("semantic", "motor_label", "recurrence")
    if not isinstance(features, Mapping) or any(key not in features for key in keys):
        raise ValueError("all broadcast features are required")
    values = tuple(_unit(features[key], key) for key in keys)
    return min(1.0, max(0.0, sum(w * v for w, v in zip(calibration.weights, values))))
