import json

import pytest
import requests

import dreamweaver_enhanced as dw
from dreamweaver_enhanced import (
    GrokCoach,
    GrokError,
    NotFoundError,
    ValidationError,
    build_coach_prompt,
    parse_sse_stream,
    utcnow_iso,
)


def test_utcnow_iso_is_seconds_precision():
    ts = utcnow_iso()
    assert "+00:00" in ts
    assert "." not in ts


# -- DreamStore: dreams ---------------------------------------------------


def test_add_and_get_dream_roundtrip(store):
    dream = store.add_dream("Flying", "Recognise the dream", scene="A bright coast")
    assert dream.id is not None
    fetched = store.get_dream(dream.id)
    assert fetched.title == "Flying"
    assert fetched.intention == "Recognise the dream"
    assert fetched.scene == "A bright coast"
    assert fetched.to_dict()["title"] == "Flying"


def test_add_dream_trims_whitespace(store):
    dream = store.add_dream("  Ocean  ", "  swim  ")
    assert dream.title == "Ocean"
    assert dream.intention == "swim"
    assert dream.scene == ""


@pytest.mark.parametrize(
    "title,intention", [("", "x"), ("   ", "x"), ("t", ""), ("t", "  ")]
)
def test_add_dream_validation(store, title, intention):
    with pytest.raises(ValidationError):
        store.add_dream(title, intention)


def test_get_missing_dream_raises(store):
    with pytest.raises(NotFoundError):
        store.get_dream(999)


def test_list_dreams_orders_newest_first_and_respects_limit(store):
    for i in range(3):
        store.add_dream(f"D{i}", "intent")
    dreams = store.list_dreams(limit=2)
    assert len(dreams) == 2
    assert dreams[0].title == "D2"
    assert dreams[1].title == "D1"


# -- DreamStore: TMR sessions --------------------------------------------


def test_tmr_session_lifecycle(store):
    dream = store.add_dream("Lucid", "become aware")
    session = store.start_tmr_session(dream.id)
    assert session.status == "active"
    assert session.cue_count == 0

    session = store.record_cue(session.id)
    session = store.record_cue(session.id)
    assert session.cue_count == 2

    completed = store.complete_tmr_session(session.id)
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert completed.to_dict()["cue_count"] == 2


def test_start_tmr_session_missing_dream(store):
    with pytest.raises(NotFoundError):
        store.start_tmr_session(12345)


def test_record_cue_on_completed_session_raises(store):
    dream = store.add_dream("Lucid", "become aware")
    session = store.start_tmr_session(dream.id)
    store.complete_tmr_session(session.id)
    with pytest.raises(ValidationError):
        store.record_cue(session.id)


def test_complete_is_idempotent(store):
    dream = store.add_dream("Lucid", "become aware")
    session = store.start_tmr_session(dream.id)
    first = store.complete_tmr_session(session.id)
    second = store.complete_tmr_session(session.id)
    assert first.completed_at == second.completed_at


def test_get_missing_session_raises(store):
    with pytest.raises(NotFoundError):
        store.get_tmr_session(4242)


def test_list_tmr_sessions(store):
    dream = store.add_dream("Lucid", "become aware")
    for _ in range(2):
        store.start_tmr_session(dream.id)
    sessions = store.list_tmr_sessions(limit=5)
    assert len(sessions) == 2


def test_persistence_across_store_instances(tmp_path):
    path = str(tmp_path / "persist.db")
    store_a = dw.DreamStore(db_path=path)
    dream = store_a.add_dream("Persisted", "stay")
    store_a.close()

    store_b = dw.DreamStore(db_path=path)
    assert store_b.get_dream(dream.id).title == "Persisted"
    store_b.close()


# -- Prompt building ------------------------------------------------------


def test_build_coach_prompt_without_intention():
    messages = build_coach_prompt("How do I recall dreams?")
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "How do I recall dreams?"}
    assert len(messages) == 2


def test_build_coach_prompt_with_intention():
    messages = build_coach_prompt("Tips?", intention="Fly over mountains")
    assert any("Fly over mountains" in m["content"] for m in messages)
    assert len(messages) == 3


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_build_coach_prompt_requires_question(bad):
    with pytest.raises(ValidationError):
        build_coach_prompt(bad)


# -- SSE parsing ----------------------------------------------------------


def _sse(obj):
    return "data: " + json.dumps(obj)


def test_parse_sse_stream_yields_content_tokens():
    lines = [
        _sse({"choices": [{"delta": {"content": "Hello"}}]}),
        _sse({"choices": [{"delta": {"content": " world"}}]}),
        "data: [DONE]",
        _sse({"choices": [{"delta": {"content": "ignored"}}]}),
    ]
    assert list(parse_sse_stream(lines)) == ["Hello", " world"]


def test_parse_sse_stream_skips_noise_and_bad_json():
    lines = [
        b"data: " + json.dumps({"choices": [{"delta": {"content": "hi"}}]}).encode(),
        "",
        ": keep-alive comment",
        "data: {not json}",
        _sse({"choices": [{"delta": {}}]}),
        _sse({"nochoices": True}),
    ]
    assert list(parse_sse_stream(lines)) == ["hi"]


# -- GrokCoach ------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, payload=None, lines=None, json_error=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._lines = lines or []
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    def iter_lines(self):
        return iter(self._lines)


class FakeSession:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None, stream=False):
        self.calls.append({"url": url, "json": json, "stream": stream})
        if self._error is not None:
            raise self._error
        return self._response


def test_is_configured_rejects_placeholder_and_empty():
    assert GrokCoach(api_key="").is_configured is False
    assert GrokCoach(api_key="YOUR_XAI_API_KEY_HERE").is_configured is False
    assert GrokCoach(api_key="real-key").is_configured is True


def test_ask_returns_message_content():
    resp = FakeResponse(payload={"choices": [{"message": {"content": "Advice"}}]})
    coach = GrokCoach(api_key="k", session=FakeSession(resp))
    assert coach.ask("How?") == "Advice"


def test_ask_requires_configuration():
    coach = GrokCoach(api_key="")
    with pytest.raises(GrokError):
        coach.ask("How?")


def test_ask_raises_on_http_error():
    coach = GrokCoach(api_key="k", session=FakeSession(FakeResponse(status_code=500)))
    with pytest.raises(GrokError):
        coach.ask("How?")


def test_ask_raises_on_bad_shape():
    coach = GrokCoach(api_key="k", session=FakeSession(FakeResponse(payload={"x": 1})))
    with pytest.raises(GrokError):
        coach.ask("How?")


def test_ask_wraps_network_error():
    coach = GrokCoach(
        api_key="k", session=FakeSession(error=requests.ConnectionError("down"))
    )
    with pytest.raises(GrokError, match="Unable to reach"):
        coach.ask("How?")


def test_ask_wraps_invalid_json():
    response = FakeResponse(json_error=requests.JSONDecodeError("bad", "x", 0))
    coach = GrokCoach(api_key="k", session=FakeSession(response))
    with pytest.raises(GrokError, match="invalid JSON"):
        coach.ask("How?")


def test_stream_yields_tokens_and_sets_stream_flag():
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Lucid"}}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": " tips"}}]}),
        "data: [DONE]",
    ]
    session = FakeSession(FakeResponse(lines=lines))
    coach = GrokCoach(api_key="k", session=session)
    assert list(coach.stream("How?", intention="fly")) == ["Lucid", " tips"]
    assert session.calls[0]["stream"] is True
    assert session.calls[0]["json"]["stream"] is True


def test_stream_requires_configuration():
    coach = GrokCoach(api_key="")
    with pytest.raises(GrokError):
        list(coach.stream("How?"))


def test_stream_raises_on_http_error():
    coach = GrokCoach(api_key="k", session=FakeSession(FakeResponse(status_code=429)))
    with pytest.raises(GrokError):
        list(coach.stream("How?"))


def test_stream_wraps_connection_error():
    coach = GrokCoach(
        api_key="k", session=FakeSession(error=requests.ConnectionError("down"))
    )
    with pytest.raises(GrokError, match="Unable to reach"):
        list(coach.stream("How?"))
