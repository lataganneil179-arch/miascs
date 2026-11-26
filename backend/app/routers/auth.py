"""Sign in, registration and account lookup."""

from fastapi import APIRouter, HTTPException, Request, status

from ..accounts import find_patient, register_patient
from ..config import get_settings
from ..ratelimit import LoginThrottle
from ..schemas import LoginRequest, LoginResponse, RegisterRequest
from ..security import create_token, hash_password, verify_password
from ..serializers import patient_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

_settings = get_settings()
_throttle = LoginThrottle(window_seconds=_settings.login_window_seconds)

# Verified against when the account doesn't exist, so response time doesn't
# reveal which emails/usernames are registered.
_DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    identifier = payload.identifier.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    account_key, ip_key = f"account:{identifier}", f"ip:{client_ip}"

    _throttle.ensure_allowed(account_key, _settings.login_max_attempts)
    _throttle.ensure_allowed(ip_key, _settings.login_max_attempts * 4)

    snapshot = find_patient("email", identifier)
    if snapshot is None:
        snapshot = find_patient("username", identifier)

    data = (snapshot.to_dict() or {}) if snapshot is not None else {}
    password_ok = verify_password(payload.password, data.get("password_hash") or _DUMMY_HASH)

    if snapshot is None or not password_ok:
        _throttle.record_failure(account_key)
        _throttle.record_failure(ip_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email, username or password",
        )

    if data.get("is_active", True) is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is deactivated. Contact the infirmary for assistance.",
        )

    role = data.get("role", "patient")
    if role != payload.role:
        # Only reached with the correct password, so this leaks nothing useful.
        article = "an" if role[0] in "aeiou" else "a"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account is registered as {article} {role}.",
        )

    _throttle.clear(account_key)
    return LoginResponse(
        token=create_token(snapshot.id, role),
        patient=patient_out(snapshot.id, data),
        role=role,
    )


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> LoginResponse:
    patient_id, record = register_patient(
        name=payload.name,
        email=payload.email,
        username=payload.username,
        phone=payload.phone,
        password=payload.password,
    )
    return LoginResponse(
        token=create_token(patient_id, "patient"),
        patient=patient_out(patient_id, record),
        role="patient",
    )


@router.post("/logout")
def logout() -> dict[str, bool]:
    """Sessions are stateless; the client discards its token."""
    return {"ok": True}
