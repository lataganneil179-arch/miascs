"""Appointment listing, booking, rescheduling and cancellation.

Booking and rescheduling run inside Firestore transactions so that queue
numbers are never duplicated and a doctor's time slot can't be double-booked.
"""

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from google.cloud import firestore

from ..deps import CurrentUser, ensure_owner, get_current_user
from ..firebase import db, query_equals
from ..schemas import AppointmentCreate, AppointmentOut, AppointmentUpdate
from ..serializers import (
    appointment_out,
    clinic_date,
    clinic_now,
    clinic_today,
    parse_date,
    slot_start,
)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])

COLLECTION = "appointments"
MAX_ADMIN_LIST = 500


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "general"


def _dept_key(data: dict[str, Any]) -> str:
    """Stable key for a department's daily queue counter."""
    return data.get("department_id") or _slugify(data.get("department", ""))


def _validate_slot(date_key: str, slot: str) -> None:
    if date_key < clinic_today():
        raise _bad_request("Choose today or a later date")
    if slot_start(date_key, slot) < clinic_now():
        raise _bad_request("That time has already passed")


def _slot_taken(
    transaction: Any, doctor_id: str, date_key: str, slot: str, exclude_id: str | None = None
) -> bool:
    query = query_equals(COLLECTION, doctor_id=doctor_id, date_key=date_key)
    for doc in query.stream(transaction=transaction):
        if doc.id == exclude_id:
            continue
        data = doc.to_dict() or {}
        if data.get("status") == "confirmed" and data.get("time") == slot:
            return True
    return False


def _issue_ticket(
    transaction: Any, date_key: str, dept_key: str, department_id: str | None
) -> int:
    """Next queue number for a department on a day (reads first, then writes)."""
    counter_ref = db().collection("queue_counters").document(f"{date_key}__{dept_key}")
    counter = counter_ref.get(transaction=transaction)

    is_today = date_key == clinic_today()
    queue_ref = db().collection("queues").document(department_id) if department_id else None
    queue_snap = queue_ref.get(transaction=transaction) if (is_today and queue_ref) else None

    last = int((counter.to_dict() or {}).get("last", 0)) if counter.exists else 0
    if queue_snap is not None and queue_snap.exists:
        # Staff-issued tickets for today live on the queue document; never go below them.
        last = max(last, int((queue_snap.to_dict() or {}).get("last_issued", 0)))

    number = last + 1
    transaction.set(counter_ref, {"last": number})
    if queue_snap is not None and queue_snap.exists:
        transaction.update(queue_ref, {"last_issued": number})
    return number


@firestore.transactional
def _book_txn(
    transaction: Any, record: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    if _slot_taken(transaction, record["doctor_id"], record["date_key"], record["time"]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That time slot is already booked. Please choose another.",
        )
    number = _issue_ticket(
        transaction, record["date_key"], _dept_key(record), record.get("department_id")
    )
    saved = {**record, "queue_number": number}
    reference = db().collection(COLLECTION).document()
    transaction.set(reference, saved)
    return reference.id, saved


@firestore.transactional
def _reschedule_txn(
    transaction: Any,
    reference: Any,
    user: CurrentUser,
    scheduled: datetime,
    date_key: str,
    slot: str,
) -> dict[str, Any]:
    snapshot = reference.get(transaction=transaction)
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    data = snapshot.to_dict() or {}
    ensure_owner(user, data.get("patient_id", ""))
    if data.get("status") != "confirmed":
        raise _bad_request("Only upcoming visits can be rescheduled")

    if _slot_taken(transaction, data.get("doctor_id", ""), date_key, slot, exclude_id=reference.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That time slot is already booked. Please choose another.",
        )

    updates: dict[str, Any] = {
        "date": scheduled,
        "date_key": date_key,
        "time": slot,
        "updated_at": datetime.now(timezone.utc),
    }
    if date_key != data.get("date_key"):
        # A ticket belongs to a single day: moving to another day needs a new one.
        updates["queue_number"] = _issue_ticket(
            transaction, date_key, _dept_key(data), data.get("department_id")
        )

    transaction.update(reference, updates)
    return {**data, **updates}


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    patient_id: str | None = Query(default=None, alias="patientId"),
    include_all: bool = Query(default=False, alias="all"),
    user: CurrentUser = Depends(get_current_user),
) -> list[AppointmentOut]:
    if include_all:
        if user.role != "administrator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
            )
        snapshot = db().collection(COLLECTION).limit(MAX_ADMIN_LIST).stream()
    else:
        if patient_id:
            ensure_owner(user, patient_id)
        snapshot = query_equals(COLLECTION, patient_id=patient_id or user.id).stream()

    items = [appointment_out(doc.id, doc.to_dict() or {}) for doc in snapshot]
    items.sort(key=lambda item: (item.date, item.time))
    return items


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate, user: CurrentUser = Depends(get_current_user)
) -> AppointmentOut:
    doctor_snapshot = db().collection("doctors").document(payload.doctor_id).get()
    if not doctor_snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    doctor = doctor_snapshot.to_dict() or {}
    scheduled = parse_date(payload.date)
    date_key = clinic_date(scheduled)
    _validate_slot(date_key, payload.time)

    record = {
        "patient_id": user.id,
        "doctor_id": payload.doctor_id,
        "doctor_name": doctor.get("name", ""),
        "department": doctor.get("department", ""),
        "department_id": doctor.get("department_id", ""),
        "date": scheduled,
        "date_key": date_key,
        "time": payload.time,
        "status": "confirmed",
        "queue_number": None,
        "created_at": datetime.now(timezone.utc),
    }
    appointment_id, saved = _book_txn(db().transaction(), record)
    return appointment_out(appointment_id, saved)


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def reschedule_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> AppointmentOut:
    scheduled = parse_date(payload.date)
    date_key = clinic_date(scheduled)
    _validate_slot(date_key, payload.time)

    reference = db().collection(COLLECTION).document(appointment_id)
    updated = _reschedule_txn(
        db().transaction(), reference, user, scheduled, date_key, payload.time
    )
    return appointment_out(appointment_id, updated)


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: str, user: CurrentUser = Depends(get_current_user)
) -> AppointmentOut:
    reference = db().collection(COLLECTION).document(appointment_id)
    snapshot = reference.get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    data = snapshot.to_dict() or {}
    ensure_owner(user, data.get("patient_id", ""))

    current = data.get("status")
    if current == "completed":
        raise _bad_request("Completed visits can't be cancelled")
    if current == "cancelled":
        return appointment_out(appointment_id, data)  # already cancelled: idempotent

    reference.update({"status": "cancelled", "cancelled_at": datetime.now(timezone.utc)})
    return appointment_out(appointment_id, {**data, "status": "cancelled"})