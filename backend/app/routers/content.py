"""Read-only content: live queue, announcements, nurse on duty, departments."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import CurrentUser, get_current_user
from ..firebase import db, query_equals
from ..schemas import AnnouncementOut, DepartmentOut, DoctorOut, NurseOut, QueueOut
from ..serializers import clinic_today, to_iso

router = APIRouter(prefix="/api", tags=["content"])


def _documents(collection: str) -> list[dict[str, Any]]:
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in db().collection(collection).stream()]


@router.get("/queue", response_model=QueueOut)
def read_queue(
    department: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> QueueOut:
    queues = _documents("queues")
    if not queues:
        return QueueOut(
            department=department or "General Medicine",
            now_serving=0,
            your_number=0,
            patients_ahead=0,
            estimated_wait_mins=0,
            is_live=False,
        )

    # The patient's confirmed visits today.
    today_visits = [
        item
        for item in (
            doc.to_dict() or {}
            for doc in query_equals("appointments", patient_id=user.id, date_key=clinic_today()).stream()
        )
        if item.get("status") == "confirmed"
    ]

    if department:
        selected = next((item for item in queues if item.get("department") == department), None)
        if selected is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No queue found for that department"
            )
    else:
        # Default to the department the patient is actually visiting today.
        visiting = {item.get("department") for item in today_visits}
        selected = next((item for item in queues if item.get("department") in visiting), queues[0])

    now_serving = int(selected.get("now_serving", 0))
    average_service = int(selected.get("avg_service_minutes", 7))

    numbers = [
        int(item.get("queue_number") or 0)
        for item in today_visits
        if item.get("department") == selected.get("department")
    ]
    numbers = [number for number in numbers if number > 0]

    # No ticket today in this department -> your_number stays 0 (never someone else's number).
    your_number = min(numbers) if numbers else 0
    patients_ahead = max(your_number - now_serving, 0) if numbers else 0

    return QueueOut(
        department=selected.get("department", "General Medicine"),
        now_serving=now_serving,
        your_number=your_number,
        patients_ahead=patients_ahead,
        estimated_wait_mins=patients_ahead * average_service,
        is_live=bool(selected.get("is_live", True)),
        has_ticket=bool(numbers),
    )


@router.get("/announcements", response_model=list[AnnouncementOut])
def read_announcements() -> list[AnnouncementOut]:
    items = [
        AnnouncementOut(
            id=doc["id"],
            category=doc.get("category", "Announcement"),
            title=doc.get("title", ""),
            body=doc.get("body", ""),
            published_at=to_iso(doc.get("published_at")),
            pinned=bool(doc.get("pinned", False)),
        )
        for doc in _documents("announcements")
    ]
    items.sort(key=lambda item: item.published_at, reverse=True)
    return items


@router.get("/nurse-on-duty", response_model=NurseOut)
def read_nurse() -> NurseOut:
    snapshot = db().collection("settings").document("nurse_on_duty").get()
    data = snapshot.to_dict() if snapshot.exists else None
    if not data:
        return NurseOut(
            name="Nurse on duty",
            title="Registered Nurse",
            available=False,
            shift="Monday–Saturday",
            hours="7:00 AM – 6:00 PM",
            photo_url=None,
        )
    return NurseOut(
        name=data.get("name", ""),
        title=data.get("title", ""),
        available=bool(data.get("available", True)),
        shift=data.get("shift", ""),
        hours=data.get("hours", ""),
        photo_url=data.get("photo_url"),
    )


@router.get("/departments", response_model=list[DepartmentOut])
def read_departments() -> list[DepartmentOut]:
    departments = sorted(_documents("departments"), key=lambda item: item.get("order", 0))
    doctors = _documents("doctors")
    return [
        DepartmentOut(
            id=department["id"],
            name=department.get("name", ""),
            doctors=[
                DoctorOut(
                    id=doctor["id"],
                    name=doctor.get("name", ""),
                    department=doctor.get("department", department.get("name", "")),
                )
                for doctor in doctors
                if doctor.get("department_id") == department["id"]
            ],
        )
        for department in departments
    ]
