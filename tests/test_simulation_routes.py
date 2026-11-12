"""Flask tests for the /simulation section and its NEXUS ledger view."""

import json

import pytest

from app import create_app
from dreamweaver_enhanced import DreamStore
from tests.conftest import FakeCoach

VALID_FORM = {
    "consent_state": "granted",
    "input_valid": "on",
    "input_fresh": "on",
    "liberty_ok": "on",
    "arousal": "0.30",
    "arousal_max": "0.80",
    "coherence": "0.82",
    "broadcast": "0.25",
    "context": "CoreLayer",
}


@pytest.fixture
def ledger(tmp_path):
    return tmp_path / "nexus_ledger.jsonl"


@pytest.fixture
def app(tmp_path, ledger):
    store = DreamStore(db_path=str(tmp_path / "app.db"))
    application = create_app(store=store, coach=FakeCoach(), nexus_ledger=str(ledger))
    application.config.update(TESTING=True)
    yield application
    store.close()


@pytest.fixture
def client(app):
    with app.test_client() as client:
        client.store = app.config["STORE"]
        yield client


def _post(client, **overrides):
    data = dict(VALID_FORM, **overrides)
    return client.post("/simulation", data=data, follow_redirects=True)


def test_simulation_page_renders_form_and_disclaimer(client):
    resp = client.get("/simulation")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Intentionality Engine" in body
    assert "Non-medical, non-actuating" in body
    assert 'name="coherence"' in body
    assert 'name="consent_state"' in body
    assert "No events yet" in body


def test_nav_links_to_simulation_from_dashboard(client):
    resp = client.get("/")
    assert b'href="/simulation"' in resp.data


def test_policy_pass_shows_allow_decision_and_appends_ledger_event(client, ledger):
    resp = _post(client)
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "ALLOW" in body
    assert "Consolidation" in body
    assert "CORE_CONSOLIDATION" in body
    assert "envelope_id null" in body

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["safety_decision"] == "ALLOW"
    assert event["regime"] == "Consolidation"
    assert event["notes"] == "CORE_CONSOLIDATION"
    assert event["envelope_id"] is None
    # The recent-events table now shows this event.
    assert event["event_id"][:8] in body


def test_stop_request_vetoes_and_still_audits(client, ledger):
    resp = _post(client, stop_requested="on")
    body = resp.data.decode()
    assert "VETO" in body
    assert "STOP_REQUESTED" in body
    assert "Safe-State" in body
    event = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert event["safety_decision"] == "VETO"
    assert event["notes"] == "STOP_REQUESTED"


def test_withdrawn_consent_vetoes(client):
    body = _post(client, consent_state="withdrawn").data.decode()
    assert "CONSENT_NOT_EXPLICIT_OR_OVERRIDDEN" in body


def test_coherence_collapse_vetoes(client):
    body = _post(client, coherence="0.05").data.decode()
    assert "VETO" in body
    assert "COHERENCE_COLLAPSE" in body


def test_arousal_above_ceiling_vetoes(client):
    body = _post(client, arousal="0.95", arousal_max="0.80").data.decode()
    assert "AROUSAL_BOUND_VIOLATION" in body


def test_adaptive_expansion_requires_review_only_proposal(client):
    body = _post(client, coherence="0.95", broadcast="0.80", context="AdaptiveLayer").data.decode()
    assert "Expansion" in body
    assert "ADAPTIVE_HIGH_COHERENCE_DENSITY" in body
    assert "ADAPTIVE_REVIEW_ONLY" in body


def test_invalid_numeric_input_returns_styled_400(client, ledger):
    resp = client.post("/simulation", data=dict(VALID_FORM, coherence="abc"))
    assert resp.status_code == 400
    assert "between 0 and 1" in resp.data.decode()
    assert not ledger.exists()


def test_invalid_context_returns_styled_400(client):
    resp = client.post("/simulation", data=dict(VALID_FORM, context="Moon"))
    assert resp.status_code == 400
    assert "Context must be one of" in resp.data.decode()


def test_ledger_survives_app_restart(tmp_path, ledger):
    store = DreamStore(db_path=str(tmp_path / "restart.db"))
    first = create_app(store=store, coach=FakeCoach(), nexus_ledger=str(ledger))
    first.config.update(TESTING=True)
    with first.test_client() as client:
        client.post("/simulation", data=VALID_FORM)
    store.close()

    second_store = DreamStore(db_path=str(tmp_path / "restart2.db"))
    second = create_app(store=second_store, coach=FakeCoach(), nexus_ledger=str(ledger))
    second.config.update(TESTING=True)
    with second.test_client() as client:
        body = client.get("/simulation").data.decode()
    second_store.close()
    assert "CORE_CONSOLIDATION" in body
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 1


def test_existing_flows_still_work(client):
    resp = client.get("/record")
    assert resp.status_code == 200
    resp = client.post(
        "/record",
        data={"title": "Ocean", "intention": "Swim", "scene": "Blue"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Ocean" in resp.data.decode()
    assert client.get("/tmr").status_code == 200
    assert client.get("/coach").status_code == 200
    assert client.get("/healthz").json == {"status": "ok"}
