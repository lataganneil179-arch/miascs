"""Administrator-only appointment and patient-account management."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..accounts import email_ref, username_ref
from ..deps import CurrentUser, get_admin_user
from ..firebase import db, query_equals
from ..schemas import AdminAppointmentOut, AdminUserOut, UserStatusUpdate
from ..serializers import to_iso

router = APIRouter(prefix="/api/admin", tags=["admin"])

MAX_ADMIN_ROWS = 500
MAX_DELETE_WRITES = 500


def _admin_user_out(doc_id: str, data: dict[str, Any]) -> AdminUserOut:
    return AdminUserOut(
        id=doc_id,
        patient_code=data.get("patient_code", ""),
        name=data.get("name", ""),
        username=data.get("username", ""),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
        role=data.get("role", "patient"),
        is_active=data.get("is_active", True),
        created_at=to_iso(data.get("created_at")),
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(_: CurrentUser = Depends(get_admin_user)) -> list[AdminUserOut]:
    users = []
    for snapshot in db().collection("patients").limit(MAX_ADMIN_ROWS).stream():
        data = snapshot.to_dict() or {}
        if data.get("role", "patient") == "patient":
            users.append(_admin_user_out(snapshot.id, data))
    users.sort(key=lambda user: user.created_at, reverse=True)
    return users


@router.patch("/users/{patient_id}", response_model=AdminUserOut)
def set_user_status(
    patient_id: str,
    payload: UserStatusUpdate,
    admin: CurrentUser = Depends(get_admin_user),
) -> AdminUserOut:
    if patient_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own account status",
        )

    reference = db().collection("patients").document(patient_id)
    snapshot = reference.get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    data = snapshot.to_dict() or {}
    if data.get("role", "patient") != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patient accounts can be managed here",
        )

    reference.update(
        {
            "is_active": payload.is_active,
            "updated_at": datetime.now(timezone.utc),
        }
    )
    return _admin_user_out(
        patient_id,
        {**data, "is_active": payload.is_active},
    )


@router.delete("/users/{patient_id}")
def delete_user(
    patient_id: str,
    admin: CurrentUser = Depends(get_admin_user),
) -> dict[str, bool]:
    if patient_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    client = db()
    patient_ref = client.collection("patients").document(patient_id)
    snapshot = patient_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    data = snapshot.to_dict() or {}
    if data.get("role", "patient") != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patient accounts can be deleted here",
        )

    reservation_refs = []
    for reference in (email_ref(data.get("email", "")), username_ref(data.get("username", ""))):
        reservation = reference.get()
        if reservation.exists and (reservation.to_dict() or {}).get("patient_id") == patient_id:
            reservation_refs.append(reference)

    appointments = list(query_equals("appointments", patient_id=patient_id).stream())
    write_count = 1 + len(reservation_refs) + len(appointments)
    if write_count > MAX_DELETE_WRITES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account has too many appointment records to delete at once. Deactivate it instead.",
        )

    batch = client.batch()
    batch.delete(patient_ref)
    for reference in reservation_refs:
        batch.delete(reference)
    for appointment in appointments:
        batch.delete(appointment.reference)
    batch.commit()
    return {"ok": True}


@router.get("/appointments", response_model=list[AdminAppointmentOut])
def list_all_appointments(_: CurrentUser = Depends(get_admin_user)) -> list[AdminAppointmentOut]:
    appointment_docs = list(
        db().collection("appointments").limit(MAX_ADMIN_ROWS).stream()
    )
    patient_ids = {doc.to_dict().get("patient_id", "") for doc in appointment_docs}
    patient_docs = {
        snapshot.id: snapshot.to_dict() or {}
        for snapshot in db().collection("patients").stream()
        if snapshot.id in patient_ids
    }

    items = []
    for snapshot in appointment_docs:
        data = snapshot.to_dict() or {}
        patient_id = data.get("patient_id", "")
        patient = patient_docs.get(patient_id, {})
        items.append(
            AdminAppointmentOut(
                id=snapshot.id,
                patient_id=patient_id,
                patient_name=patient.get("name", "Unknown account"),
                patient_code=patient.get("patient_code", ""),
                doctor_name=data.get("doctor_name", ""),
                department=data.get("department", ""),
                date=to_iso(data.get("date")),
                time=data.get("time", ""),
                status=data.get("status", "confirmed"),
                queue_number=data.get("queue_number"),
            )
        )
    items.sort(key=lambda appointment: (appointment.date, appointment.time))
    return items
