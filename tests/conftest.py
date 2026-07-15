import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dreamweaver_enhanced import DreamStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    db = DreamStore(db_path=str(tmp_path / "test.db"))
    yield db
    db.close()


class FakeCoach:
    """Minimal stand-in for GrokCoach used by the Flask tests."""

    def __init__(self, configured=True, tokens=None, error=None):
        self._configured = configured
        self._tokens = tokens or ["Hello", " dreamer"]
        self._error = error

    @property
    def is_configured(self):
        return self._configured

    def stream(self, question, intention=None):
        if self._error is not None:
            raise self._error
        for token in self._tokens:
            yield token


@pytest.fixture
def fake_coach():
    return FakeCoach()
