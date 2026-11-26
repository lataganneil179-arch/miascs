"""Shared FastAPI dependencies."""

from dataclasses import dataclass

import jwt
from fastapi import HTTPException, status
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .firebase import db
from .security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise unauthorized

    user_id = claims.get("sub")
    if not isinstance(user_id, str):
        raise unauthorized

    snapshot = db().collection("patients").document(user_id).get()
    if not snapshot.exists:
        raise unauthorized

    account = snapshot.to_dict() or {}
    if account.get("is_active", True) is False:
        raise unauthorized

    return CurrentUser(id=user_id, role=account.get("role", "patient"))


def get_admin_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


def ensure_owner(user: CurrentUser, owner_id: str) -> None:
    """Allow the record's owner or an administrator; otherwise 403."""
    if user.id != owner_id and user.role != "administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this record",
        )