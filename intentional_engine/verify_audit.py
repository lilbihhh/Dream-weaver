"""NEXUS JSONL verification: schema, hash chain, append-only simulation, and field allow-list."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from intentional_engine.policy_graph import _validate_event, run_policy

DEFAULT_LEDGER = Path(__file__).resolve().parent / "nexus_ledger.jsonl"


def verify(path: Path) -> int:
    previous = None
    allowed = {"ts", "event_id", "regime", "safety_decision", "intent_summary", "envelope_id", "inputs_hash", "notes", "prev_hash", "event_hash"}
    count = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank ledger line {number}")
        event = json.loads(line)
        _validate_event(event)
        if set(event) != allowed or event["prev_hash"] != previous:
            raise ValueError(f"field allow-list or hash-chain mismatch at line {number}")
        expected = hashlib.sha256(json.dumps({k: v for k, v in event.items() if k != "event_hash"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if event["event_hash"] != expected:
            raise ValueError(f"event hash mismatch at line {number}")
        previous = event["event_hash"]
        count += 1
    return count


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.jsonl"
        args = {"consent_state": "granted", "consent_override": False, "input_valid": True, "input_fresh": True, "liberty_ok": True, "stop_requested": False, "arousal_ok": True, "arousal": .2, "arousal_max": .8, "coherence": .8, "broadcast": .2, "context": "CoreLayer"}
        run_policy(args, path)
        first = path.read_bytes()
        run_policy(args, path)
        if not path.read_bytes().startswith(first):
            raise AssertionError("ledger was rewritten rather than appended")
        if verify(path) != 2:
            raise AssertionError("expected two verified ledger events")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", nargs="?", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    print(f"NEXUS verification passed: {verify(args.ledger) if args.ledger.exists() else 0} event(s)")
