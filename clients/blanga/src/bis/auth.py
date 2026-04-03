from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from bis.settings import get_settings

security = HTTPBasic(auto_error=False)


def require_bis_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    settings = get_settings()
    if not settings.require_auth:
        return

    if credentials is None:
        raise HTTPException(status_code=401, detail="authentication required")

    user_ok = secrets.compare_digest(credentials.username, settings.app_username)
    pw_ok = secrets.compare_digest(credentials.password, settings.app_password)
    if not (user_ok and pw_ok):
        raise HTTPException(status_code=401, detail="invalid credentials")
