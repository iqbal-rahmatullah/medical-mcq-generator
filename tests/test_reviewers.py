from app.core.config import settings
from app.services import _reviewers


def test_reviewer_enabled_flag_disables_default_reviewer(monkeypatch):
    monkeypatch.setattr(settings, "REVIEWER_ENABLED", False)

    assert _reviewers._get_reviewer_client() is None
