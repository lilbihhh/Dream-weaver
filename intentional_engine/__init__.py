"""Vendored DreamWeaver N1 Intentionality Engine (offline, non-actuating).

Source: https://github.com/lilbihhh/intentional-architecture
Pinned commit: 8035e2befd93d2f10947e708fc4a021cb1393c5a (see ``VENDORED.md``).

The policy graph is Observe → Estimate → Propose → SafetyGovernor →
SelectRegime → EmitAudit. The Safety Governor is the first gate and the final
veto; the engine emits no actuator commands and every audit event carries a
null ``envelope_id``.
"""

from __future__ import annotations

from .metrics import (
    BroadcastCalibration,
    CoherenceCalibration,
    broadcast_density,
    coherence_proxy,
)
from .policy_graph import (
    DEFAULT_LEDGER,
    SCHEMA_PATH,
    GovernorResult,
    run_governance_pass,
    run_policy,
    safety_governor,
)
from .regimes import Regime, RegimeDecision, select_regime

__all__ = [
    "BroadcastCalibration",
    "CoherenceCalibration",
    "DEFAULT_LEDGER",
    "GovernorResult",
    "Regime",
    "RegimeDecision",
    "SCHEMA_PATH",
    "broadcast_density",
    "coherence_proxy",
    "run_governance_pass",
    "run_policy",
    "safety_governor",
    "select_regime",
]
