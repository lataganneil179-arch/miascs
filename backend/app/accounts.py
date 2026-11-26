"""Patient account helpers.

Uniqueness of email/username and the patient-code sequence are enforced with
Firestore transactions (reservation documents + a counter document), so two
simultaneous requests can't create duplicates.
"""

import hashlib
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentSnapshot

from .firebase import db, query_equals
from .security import hash_password

ACCOUNT_CONFLICT = "An account with this email or username already exists"
EMAIL_CONFLICT = "That email is already in use"


def _conflict(detail: str = ACCOUNT_CONFLICT) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def email_ref(email: str) -> Any:
    return db().collection("unique_emails").document(_key(email))


def username_ref(username: str) -> Any:
    return db().collection("unique_usernames").document(_key(username))


def find_patient(field: str, value: str) -> DocumentSnapshot | None:
    """Look up a single patient document by field."""
    for snapshot in query_equals("patients", **{field: value}).limit(1).stream():
        return snapshot
    return None


@firestore.transactional
def _register_txn(
    transaction: Any,
    patient_ref: Any,
    email_doc: Any,
    username_doc: Any,
    counter_ref: Any,
    year: int,
    start: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    # All reads first, then all writes.
    email_snap = email_doc.get(transaction=transaction)
    username_snap = username_doc.get(transaction=transaction)
    counter_snap = counter_ref.get(transaction=transaction)

    if email_snap.exists or username_snap.exists:
        raise _conflict()

    last = int((counter_snap.to_dict() or {}).get("last", start)) if counter_snap.exists else start
    number = last + 1
    saved = {**record, "patient_code": f"MIA-{year}-{number:03d}"}

    transaction.set(counter_ref, {"last": number})
    transaction.set(email_doc, {"patient_id": patient_ref.id, "email": saved["email"]})
    transaction.set(username_doc, {"patient_id": patient_ref.id, "username": saved["username"]})
    transaction.set(patient_ref, saved)
    return saved


def register_patient(
    *, name: str, email: str, username: str, phone: str, password: str
) -> tuple[str, dict[str, Any]]:
    # Accounts created before reservation documents existed are caught here.
    if find_patient("email", email) is not None or find_patient("username", username) is not None:
        raise _conflict()

    year = datetime.now(timezone.utc).year
    counter_ref = db().collection("counters").document(f"patients-{year}")

    # First registration of the year with no counter yet: start after existing patients.
    start = 0
    if not counter_ref.get().exists:
        start = int(db().collection("patients").count().get()[0][0].value)

    patient_ref = db().collection("patients").document()
    record = {
        "name": name,
        "email": email,
        "username": username,
        "phone": phone,
        "role": "patient",
        "is_active": True,
        "password_hash": hash_password(password),  # slow; keep outside the transaction
        "created_at": datetime.now(timezone.utc),
    }
    saved = _register_txn(
        db().transaction(),
        patient_ref,
        email_ref(email),
        username_ref(username),
        counter_ref,
        year,
        start,
        record,
    )
    # Never return the password hash from the API response.
    public_data = {
        key: value
        for key, value in saved.items()
        if key != "password_hash"
    }

    return patient_ref.id, public_data


@firestore.transactional
def _profile_txn(transaction: Any, patient_ref: Any, changes: dict[str, Any]) -> None:
    snapshot = patient_ref.get(transaction=transaction)
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    new_email = changes["email"]
    old_email = (snapshot.to_dict() or {}).get("email", "")
    new_doc = email_ref(new_email)
    reservation = new_doc.get(transaction=transaction)
    if reservation.exists and (reservation.to_dict() or {}).get("patient_id") != patient_ref.id:
        raise _conflict(EMAIL_CONFLICT)

    if old_email and old_email != new_email:
        transaction.delete(email_ref(old_email))
    transaction.set(new_doc, {"patient_id": patient_ref.id, "email": new_email})
    transaction.update(patient_ref, changes)


def update_profile(patient_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Apply profile changes; email changes keep the uniqueness reservation in sync."""
    patient_ref = db().collection("patients").document(patient_id)

    if changes.get("email"):
        existing = find_patient("email", changes["email"])
        if existing is not None and existing.id != patient_id:
            raise _conflict(EMAIL_CONFLICT)
        _profile_txn(db().transaction(), patient_ref, changes)
    elif changes:
        patient_ref.update(changes)

    return patient_ref.get().to_dict() or {}
