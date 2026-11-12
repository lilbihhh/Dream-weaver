"""Tests for the vendored Intentionality Engine (policy graph, metrics, NEXUS schema)."""

import json

import pytest

from intentional_engine import (
    BroadcastCalibration,
    CoherenceCalibration,
    Regime,
    broadcast_density,
    coherence_proxy,
    run_policy,
    select_regime,
)
from intentional_engine.fixtures import calibrations_from_config, load_config, load_sequences
from intentional_engine.policy_graph import _validate_event
from intentional_engine.verify_audit import verify

SAFE = {
    "consent_state": "granted",
    "consent_override": False,
    "input_valid": True,
    "input_fresh": True,
    "liberty_ok": True,
    "stop_requested": False,
    "arousal_ok": True,
    "arousal": 0.2,
    "arousal_max": 0.8,
    "coherence": 0.8,
    "broadcast": 0.2,
    "context": "CoreLayer",
}


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "nexus_ledger.jsonl"


def _run(ledger, **overrides):
    return run_policy(dict(SAFE, **overrides), ledger)


def test_safe_core_pass_allows_consolidation_and_appends_valid_event(ledger):
    result = _run(ledger)
    assert result["safety_decision"] == "ALLOW"
    assert result["regime"] == "Consolidation"
    assert result["reason_code"] == "CORE_CONSOLIDATION"
    assert result["envelope_id"] is None
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    _validate_event(event)
    assert event["intent_summary"] == "synthetic_policy_pass"
    assert event["prev_hash"] is None
    assert verify(ledger) == 1


def test_ledger_is_append_only_and_hash_chained(ledger):
    _run(ledger)
    first = ledger.read_bytes()
    _run(ledger)
    second = ledger.read_bytes()
    assert second.startswith(first)
    events = [json.loads(line) for line in second.decode().splitlines()]
    assert events[0]["event_hash"] == events[1]["prev_hash"]
    assert verify(ledger) == 2


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"coherence": 0.0}, "COHERENCE_COLLAPSE"),
        ({"stop_requested": True}, "STOP_REQUESTED"),
        ({"consent_state": "withdrawn"}, "CONSENT_NOT_EXPLICIT_OR_OVERRIDDEN"),
        ({"consent_override": True}, "CONSENT_NOT_EXPLICIT_OR_OVERRIDDEN"),
        ({"input_fresh": False}, "INPUT_OR_LIBERTY_CHECK_FAILED"),
        ({"liberty_ok": False}, "INPUT_OR_LIBERTY_CHECK_FAILED"),
        ({"arousal": 0.9}, "AROUSAL_BOUND_VIOLATION"),
        ({"context": "Unknown"}, "CONTEXT_MISSING_OR_INVALID"),
        ({"broadcast": 1.5}, "METRIC_MISSING_OR_INVALID"),
    ],
)
def test_governor_vetoes_fail_closed(ledger, overrides, reason):
    result = _run(ledger, **overrides)
    assert result["safety_decision"] == "VETO"
    assert result["reason_code"] == reason
    assert result["regime"] == "Safe-State"
    assert result["envelope_id"] is None


def test_missing_safety_inputs_veto_without_regime_or_envelope(ledger):
    # Observe fills absent safety flags with fail-closed defaults, so an
    # under-specified pass can never be allowed.
    result = run_policy({"consent_state": "granted", "coherence": 0.8, "broadcast": 0.2}, ledger)
    assert result["safety_decision"] == "VETO"
    assert result["reason_code"] == "INPUT_OR_LIBERTY_CHECK_FAILED"
    assert result["regime"] == "Safe-State"
    assert result["adaptive_proposal"] is None
    assert result["envelope_id"] is None


def test_metrics_are_bounded_and_reject_bad_input():
    zeros = dict.fromkeys(("consistency", "continuity", "provenance", "agreement"), 0)
    ones = dict.fromkeys(("consistency", "continuity", "provenance", "agreement"), 1)
    assert coherence_proxy(zeros) == 0
    assert coherence_proxy(ones) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        coherence_proxy({})
    with pytest.raises(ValueError):
        broadcast_density({"semantic": 1, "motor_label": 1, "recurrence": float("inf")})
    with pytest.raises(ValueError):
        broadcast_density({"semantic": 1.1, "motor_label": 0, "recurrence": 0})


def test_regime_selection_paths_and_adaptive_proposal_is_advisory():
    flags = {
        "input_valid": True,
        "input_fresh": True,
        "liberty_ok": True,
        "stop_requested": False,
        "arousal_ok": True,
    }
    expansion = select_regime(0.9, 0.9, flags, "granted", "AdaptiveLayer")
    assert expansion.regime is Regime.EXPANSION
    assert expansion.adaptive_proposal == "ADAPTIVE_REVIEW_ONLY"
    assert select_regime(0.6, 0.2, flags, "granted", "CoreLayer").regime is Regime.CONSOLIDATION
    assert select_regime(0.4, 0.2, flags, "granted", "CoreLayer").regime is Regime.STABILIZATION


def test_schema_rejects_extra_and_malformed_fields():
    with pytest.raises(ValueError):
        _validate_event({"ts": "not-a-date"})
    with pytest.raises(ValueError):
        _validate_event(
            {
                "ts": "2026-01-01T00:00:00Z",
                "event_id": "not-a-uuid",
                "regime": "Consolidation",
                "safety_decision": "ALLOW",
                "intent_summary": "synthetic_policy_pass",
                "envelope_id": None,
                "inputs_hash": "0" * 64,
                "notes": "SAFETY_ALLOW",
                "prev_hash": None,
                "event_hash": "0" * 64,
                "raw_neural_data": "forbidden",
            }
        )


def test_calibration_fixtures_replay_expected_regimes_and_decisions(ledger):
    config = load_config()
    sequences = load_sequences()
    assert set(config["sequences"]) == set(sequences)
    for name, sequence in sequences.items():
        expected = config["sequences"][name]
        regimes, decisions = [], []
        for step in sequence:
            result = run_policy(step, ledger)
            regimes.append(result["regime"])
            decisions.append(result["safety_decision"])
        assert regimes == expected["expected_regimes"], name
        assert decisions == expected["expected_decisions"], name
    assert verify(ledger) == sum(len(seq) for seq in sequences.values())


def test_calibration_config_matches_engine_defaults():
    coherence, broadcast = calibrations_from_config()
    assert coherence == CoherenceCalibration()
    assert broadcast == BroadcastCalibration()
