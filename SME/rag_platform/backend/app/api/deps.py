from fastapi import Header, HTTPException

from app.core.config import settings


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    if not x_api_key or x_api_key != settings.widget_api_key:
        raise HTTPException(status_code=401, detail='Invalid API key')
    return x_api_key


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> str:
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail='Invalid admin key')
    return x_admin_key
