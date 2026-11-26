"""Request/response models. JSON keys are camelCase to match the React client."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _normalise_email(value: str) -> str:
    return value.strip().lower()


def _check_iso_date(value: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Date must be an ISO-8601 date") from error
    return value


Email = Annotated[EmailStr, AfterValidator(_normalise_email)]
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9._-]{3,30}$"
    ),
]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
SlotTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
IsoDate = Annotated[str, AfterValidator(_check_iso_date)]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


Role = Literal["patient", "administrator"]
AppointmentStatus = Literal["confirmed", "completed", "cancelled"]


class LoginRequest(ApiModel):
    identifier: str
    password: str
    role: Role = "patient"


class RegisterRequest(ApiModel):
    name: PersonName
    email: Email
    username: Username
    password: str = Field(min_length=6, max_length=72)
    phone: Phone = ""

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, value: str) -> str:
        # bcrypt only uses the first 72 bytes; reject instead of silently truncating.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return value


class PatientOut(ApiModel):
    id: str
    patient_code: str
    name: str
    username: str = ""
    email: str
    phone: str = ""


class LoginResponse(ApiModel):
    token: str
    patient: PatientOut
    role: Role


class ProfileUpdate(ApiModel):
    name: PersonName | None = None
    phone: Phone | None = None
    email: Email | None = None


class DoctorOut(ApiModel):
    id: str
    name: str
    department: str


class DepartmentOut(ApiModel):
    id: str
    name: str
    doctors: list[DoctorOut] = Field(default_factory=list)


class AppointmentOut(ApiModel):
    id: str
    doctor_name: str
    department: str
    date: str
    time: str
    status: AppointmentStatus
    queue_number: int | None = None


class AppointmentCreate(ApiModel):
    doctor_id: str
    date: IsoDate
    time: SlotTime


class AppointmentUpdate(ApiModel):
    date: IsoDate
    time: SlotTime


class AdminUserOut(ApiModel):
    id: str
    patient_code: str = ""
    name: str = ""
    username: str = ""
    email: str = ""
    phone: str = ""
    role: Role
    is_active: bool = True
    created_at: str = ""


class AdminAppointmentOut(ApiModel):
    id: str
    patient_id: str
    patient_name: str
    patient_code: str = ""
    doctor_name: str
    department: str
    date: str
    time: str
    status: AppointmentStatus
    queue_number: int | None = None


class UserStatusUpdate(ApiModel):
    is_active: bool


class QueueOut(ApiModel):
    department: str
    now_serving: int
    your_number: int
    patients_ahead: int
    estimated_wait_mins: int
    is_live: bool
    has_ticket: bool = False


class AnnouncementOut(ApiModel):
    id: str
    category: str
    title: str
    body: str
    published_at: str
    pinned: bool = False


class NurseOut(ApiModel):
    name: str
    title: str
    available: bool = True
    shift: str
    hours: str
    photo_url: str | None = None
