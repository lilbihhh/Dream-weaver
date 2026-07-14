import pytest

from app import create_app
from dreamweaver_enhanced import DreamStore, GrokError
from tests.conftest import FakeCoach


@pytest.fixture
def client(tmp_path):
    store = DreamStore(db_path=str(tmp_path / "app.db"))
    app = create_app(store=store, coach=FakeCoach())
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client.store = store
        yield client
    store.close()


def _seed_dream(client, title="Flying", intention="Recognise the dream"):
    return client.store.add_dream(title, intention, scene="A bright coast")


def test_dashboard_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Welcome, Architect" in resp.data
    assert b"No dreams yet" in resp.data


def test_dashboard_lists_dreams_and_sessions(client):
    dream = _seed_dream(client)
    client.store.start_tmr_session(dream.id)
    resp = client.get("/")
    assert b"Flying" in resp.data


def test_record_get_renders_form(client):
    resp = client.get("/record")
    assert resp.status_code == 200
    assert b"Record Dream" in resp.data


def test_record_post_creates_and_redirects_to_play(client):
    resp = client.post(
        "/record",
        data={"title": "Ocean", "intention": "Swim deep", "scene": "Blue water"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Ocean" in resp.data
    assert b"Blue water" in resp.data
    assert len(client.store.list_dreams()) == 1


def test_record_post_validation_error(client):
    resp = client.post("/record", data={"title": "", "intention": ""})
    assert resp.status_code == 400
    assert b"required" in resp.data


def test_play_renders_animated_scene(client):
    dream = _seed_dream(client)
    resp = client.get(f"/play/{dream.id}")
    assert resp.status_code == 200
    assert b"dreamscape" in resp.data
    assert b"A bright coast" in resp.data


def test_play_missing_dream_returns_404(client):
    resp = client.get("/play/999")
    assert resp.status_code == 404
    assert b"not found" in resp.data


def test_tmr_page(client):
    _seed_dream(client)
    resp = client.get("/tmr")
    assert resp.status_code == 200
    assert b"Targeted Memory Reactivation" in resp.data


def test_tmr_full_flow(client):
    dream = _seed_dream(client)
    start = client.post("/tmr/start", data={"dream_id": dream.id})
    assert start.status_code == 302
    session = client.store.list_tmr_sessions()[0]

    cue = client.post(f"/tmr/{session.id}/cue", follow_redirects=True)
    assert cue.status_code == 200
    assert client.store.get_tmr_session(session.id).cue_count == 1

    done = client.post(f"/tmr/{session.id}/complete", follow_redirects=True)
    assert done.status_code == 200
    assert client.store.get_tmr_session(session.id).status == "completed"


def test_tmr_start_rejects_invalid_dream_id(client):
    resp = client.post("/tmr/start", data={"dream_id": "not-an-id"})
    assert resp.status_code == 400
    assert b"valid dream" in resp.data


def test_tmr_session_view(client):
    dream = _seed_dream(client)
    session = client.store.start_tmr_session(dream.id)
    resp = client.get(f"/tmr/{session.id}")
    assert resp.status_code == 200
    assert b"TMR Session" in resp.data


def test_coach_page(client):
    resp = client.get("/coach")
    assert resp.status_code == 200
    assert b"Grok Dream Coach" in resp.data


def test_coach_ask_streams_tokens(client):
    resp = client.post("/coach/ask", data={"question": "How?", "intention": "fly"})
    assert resp.status_code == 200
    assert resp.data == b"Hello dreamer"


def test_coach_ask_reports_stream_error(tmp_path):
    store = DreamStore(db_path=str(tmp_path / "err.db"))
    coach = FakeCoach(error=GrokError("boom"))
    app = create_app(store=store, coach=coach)
    with app.test_client() as client:
        resp = client.post("/coach/ask", data={"question": "How?"})
        assert resp.status_code == 200
        assert b"[error] boom" in resp.data
    store.close()


def test_coach_ask_returns_503_when_not_configured(tmp_path):
    store = DreamStore(db_path=str(tmp_path / "nc.db"))
    app = create_app(store=store, coach=FakeCoach(configured=False))
    with app.test_client() as client:
        resp = client.post("/coach/ask", data={"question": "How?"})
        assert resp.status_code == 503
    store.close()


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_unknown_route_returns_404_page(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data


def test_create_app_uses_env_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAMWEAVER_DB", str(tmp_path / "default.db"))
    app = create_app(coach=FakeCoach())
    assert app.config["STORE"] is not None
    app.config["STORE"].close()
