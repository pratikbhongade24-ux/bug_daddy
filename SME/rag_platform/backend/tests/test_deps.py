import pytest
from fastapi import HTTPException

from app.api.deps import require_admin_key, require_api_key
from app.core.config import settings


def test_require_api_key_accepts_valid_key():
    assert require_api_key(settings.widget_api_key) == settings.widget_api_key


def test_require_api_key_rejects_invalid_key():
    with pytest.raises(HTTPException) as exc:
        require_api_key("wrong-key")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid API key"


def test_require_admin_key_accepts_valid_key():
    assert require_admin_key(settings.admin_api_key) == settings.admin_api_key


def test_require_admin_key_rejects_missing_key():
    with pytest.raises(HTTPException) as exc:
        require_admin_key(None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid admin key"
