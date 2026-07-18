"""Optional HTTP Basic Auth, enabled only when credentials are configured.

Rationale: the deployed instance is wired to real (paid) LLM API keys, and the
repository is public — an unprotected URL invites credit-burn. Setting
APP_USER + APP_PASSWORD (e.g. in the Railway dashboard) locks the whole app
behind a browser login. Leaving them unset (local dev) keeps it open, so
there is zero friction when running on your own machine.
"""

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_USER = os.environ.get("APP_USER")
_PASSWORD = os.environ.get("APP_PASSWORD")
_ENABLED = bool(_USER and _PASSWORD)


def require_auth(
    credentials: HTTPBasicCredentials | None = Depends(
        HTTPBasic(auto_error=False)
    ),
) -> None:
    """FastAPI dependency: no-op unless APP_USER/APP_PASSWORD are set."""
    if not _ENABLED:
        return
    ok_user = credentials and secrets.compare_digest(credentials.username, _USER)
    ok_pass = credentials and secrets.compare_digest(credentials.password, _PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
