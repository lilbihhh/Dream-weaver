"""Loader for the vendored synthetic calibration fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CALIBRATION_DIR = Path(__file__).resolve().parent / "calibration"


def load_config() -> dict[str, Any]:
    """Return the versionable metric weights/thresholds fixture."""
    return json.loads((CALIBRATION_DIR / "config.json").read_text(encoding="utf-8"))


def load_sequences() -> dict[str, list[dict[str, Any]]]:
    """Return the named synthetic observation sequences."""
    return json.loads((CALIBRATION_DIR / "sequences.json").read_text(encoding="utf-8"))


def calibrations_from_config() -> tuple[Any, Any]:
    """Build ``(CoherenceCalibration, BroadcastCalibration)`` from the fixture."""
    from .metrics import BroadcastCalibration, CoherenceCalibration

    config = load_config()
    coherence = config["coherence"]
    broadcast = config["broadcast"]
    return (
        CoherenceCalibration(
            weights=tuple(coherence["weights"]),
            collapse_threshold=coherence["collapse_threshold"],
        ),
        BroadcastCalibration(
            weights=tuple(broadcast["weights"]),
            expansion_threshold=broadcast["expansion_threshold"],
        ),
    )
