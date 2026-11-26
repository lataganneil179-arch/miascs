"""Shared serialisation and date helpers."""

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .config import get_settings
from .schemas import AppointmentOut, AppointmentStatus, PatientOut


def to_iso(value: Any) -> str:
    """Normalise a Firestore timestamp into an ISO-8601 string."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat()
    if isinstance(value, str):
        return value
    return ""


def parse_date(value: str) -> datetime:
    """Parse a client-supplied ISO date into an aware UTC datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clinic_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def clinic_now() -> datetime:
    """Current moment as an aware datetime in the infirmary's timezone."""
    return datetime.now(_clinic_zone())


def clinic_today() -> str:
    """Current calendar date at the infirmary."""
    return clinic_now().date().isoformat()


def clinic_date(instant: datetime) -> str:
    """Calendar date of an instant in the infirmary's timezone."""
    return instant.astimezone(_clinic_zone()).date().isoformat()


def parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(hour=int(hours), minute=int(minutes))


def slot_start(date_key: str, slot: str) -> datetime:
    """Start of an appointment slot as an aware datetime in the clinic timezone."""
    return datetime.combine(date.fromisoformat(date_key), parse_time(slot), tzinfo=_clinic_zone())


def patient_out(doc_id: str, data: dict[str, Any]) -> PatientOut:
    return PatientOut(
        id=doc_id,
        patient_code=data.get("patient_code", ""),
        name=data.get("name", ""),
        username=data.get("username", ""),
        email=data.get("email", ""),
        phone=data.get("phone", ""),
    )


def appointment_out(doc_id: str, data: dict[str, Any]) -> AppointmentOut:
    status: AppointmentStatus = data.get("status", "confirmed")
    return AppointmentOut(
        id=doc_id,
        doctor_name=data.get("doctor_name", ""),
        department=data.get("department", ""),
        date=to_iso(data.get("date")),
        time=data.get("time", ""),
        status=status,
        queue_number=data.get("queue_number"),
    )
