"""The shared admin-key guard for every team-only endpoint (admin actions and the /chat test door)."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.core.config import get_settings


def get_admin_api_key() -> str:
    """FastAPI dependency. Tests replace it through `app.dependency_overrides`."""
    return get_settings().admin_api_key


def require_admin(
    configured_key: Annotated[str, Depends(get_admin_api_key)],
    x_admin_key: Annotated[str | None, Header()] = None,
) -> None:
    """Closed entirely when no key is configured; otherwise the X-Admin-Key header must match."""
    if not configured_key:
        raise HTTPException(status_code=503, detail="This endpoint is disabled: set ADMIN_API_KEY")
    if x_admin_key is None or not hmac.compare_digest(configured_key, x_admin_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")
