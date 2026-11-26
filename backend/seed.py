"""Seed Firebase with the demo content shown in the app designs.

Usage:  python seed.py   (run from the backend folder, with your .env loaded)
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.accounts import email_ref, username_ref
from app.config import get_settings
from app.firebase import db
from app.security import hash_password
from app.serializers import clinic_date, clinic_today

DEMO_PASSWORD = "Patient2026!"
ADMIN_PASSWORD = "Admin2026!"


def at(days: int, hour: int = 0, minute: int = 0) -> datetime:
    """A moment in the clinic's timezone, `days` from today, stored as UTC."""
    zone = ZoneInfo(get_settings().clinic_timezone)
    target = date.fromisoformat(clinic_today()) + timedelta(days=days)
    return datetime.combine(target, time(hour, minute), tzinfo=zone).astimezone(timezone.utc)


def appointment(patient_id: str, doctor_id: str, doctor_name: str, department: str,
                department_id: str, when: datetime, slot: str, status: str,
                queue_number: int | None = None) -> dict[str, Any]:
    return {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "department": department,
        "department_id": department_id,
        "date": when,
        "date_key": clinic_date(when),
        "time": slot,
        "status": status,
        "queue_number": queue_number,
    }


def save_account(client: Any, doc_id: str, data: dict[str, Any]) -> None:
    """Write a patient plus the reservation docs that enforce unique email/username."""
    client.collection("patients").document(doc_id).set(data, merge=True)
    email_ref(data["email"]).set({"patient_id": doc_id, "email": data["email"]})
    username_ref(data["username"]).set({"patient_id": doc_id, "username": data["username"]})


def set_if_missing(reference: Any, data: dict[str, Any]) -> None:
    """Counters must never be reset by re-running the seed."""
    if not reference.get().exists:
        reference.set(data)


def main() -> None:
    client = db()
    now = datetime.now(timezone.utc)

    departments = [
        ("dept_general", {"name": "General Medicine", "order": 1}),
        ("dept_dental", {"name": "Dental Care", "order": 2}),
        ("dept_pedia", {"name": "Pediatrics", "order": 3}),
    ]
    for doc_id, payload in departments:
        client.collection("departments").document(doc_id).set(payload, merge=True)

    doctors = [
        ("doc_001", {"name": "Dr. Anaya Reyes", "department": "General Medicine", "department_id": "dept_general"}),
        ("doc_002", {"name": "Dr. Mark Villanueva", "department": "General Medicine", "department_id": "dept_general"}),
        ("doc_003", {"name": "Dr. Miguel Santos", "department": "Dental Care", "department_id": "dept_dental"}),
        ("doc_004", {"name": "Dr. Elena Cruz", "department": "Pediatrics", "department_id": "dept_pedia"}),
    ]
    for doc_id, payload in doctors:
        client.collection("doctors").document(doc_id).set(payload, merge=True)

    save_account(client, "pt_001", {
        "patient_code": "MIA-2026-014",
        "name": "Juan Santos",
        "email": "juan.santos@example.com",
        "username": "juan.santos",
        "phone": "+63 917 000 0142",
        "role": "patient",
        "password_hash": hash_password(DEMO_PASSWORD),
        "created_at": now,
    })
    save_account(client, "adm_001", {
        "patient_code": "MIA-STAFF-001",
        "name": "Infirmary Administrator",
        "email": "admin@montalban-infirmary.example",
        "username": "admin",
        "phone": "",
        "role": "administrator",
        "password_hash": hash_password(ADMIN_PASSWORD),
        "created_at": now,
    })

    # Patient-code sequence continues after the demo patient (MIA-2026-014).
    set_if_missing(client.collection("counters").document("patients-2026"), {"last": 14})

    appointments = [
        appointment("pt_001", "doc_001", "Dr. Anaya Reyes", "General Medicine", "dept_general", at(2, 9), "09:00", "confirmed", 15),
        appointment("pt_001", "doc_003", "Dr. Miguel Santos", "Dental Care", "dept_dental", at(18, 10, 30), "10:30", "confirmed", 1),
        appointment("pt_001", "doc_004", "Dr. Elena Cruz", "Pediatrics", "dept_pedia", at(-21, 14), "14:00", "completed"),
        appointment("pt_001", "doc_001", "Dr. Anaya Reyes", "General Medicine", "dept_general", at(-46, 8, 30), "08:30", "completed"),
        appointment("pt_001", "doc_003", "Dr. Miguel Santos", "Dental Care", "dept_dental", at(-9, 11), "11:00", "cancelled"),
    ]
    for index, payload in enumerate(appointments, start=1):
        client.collection("appointments").document(f"ap_{index:03d}").set(payload, merge=True)
        if payload["queue_number"] is not None:
            counter = client.collection("queue_counters").document(
                f"{payload['date_key']}__{payload['department_id']}"
            )
            set_if_missing(counter, {"last": payload["queue_number"]})

    announcements = [
        {
            "category": "Health Advisory",
            "title": "Free flu vaccination this Friday",
            "body": "Available for registered patients from 8:00 AM to 3:00 PM.",
            "published_at": at(-2, 8),
            "pinned": True,
        },
        {
            "category": "Vaccination Drive",
            "title": "Community vaccination registration is open",
            "body": "Reserve a slot for the October community vaccination drive.",
            "published_at": at(-4, 8),
            "pinned": False,
        },
        {
            "category": "Schedule Change",
            "title": "Updated outpatient clinic hours",
            "body": "The outpatient department is now open Monday to Saturday.",
            "published_at": at(-6, 8),
            "pinned": False,
        },
    ]
    for index, payload in enumerate(announcements, start=1):
        client.collection("announcements").document(f"an_{index:03d}").set(payload, merge=True)

    client.collection("queues").document("dept_general").set(
        {
            "department": "General Medicine",
            "now_serving": 12,
            "last_issued": 15,
            "avg_service_minutes": 7,
            "is_live": True,
        },
        merge=True,
    )

    client.collection("settings").document("nurse_on_duty").set(
        {
            "name": "Nurse Maria Santos",
            "title": "Registered Nurse",
            "available": True,
            "shift": "Monday–Saturday",
            "hours": "7:00 AM – 6:00 PM",
            "photo_url": "https://cdn.enter.pro/resources/uid_100728652/nurse-maria-santos_87bdff7e.png",
        },
        merge=True,
    )

    print("Seed complete.")
    print(f"Patient login:  juan.santos / {DEMO_PASSWORD}")
    print(f"Admin login:    admin / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
