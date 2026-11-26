"""The signed-in patient's own profile."""

from fastapi import APIRouter, Depends

from ..accounts import update_profile
from ..deps import CurrentUser, get_current_user
from ..schemas import PatientOut, ProfileUpdate
from ..serializers import patient_out

router = APIRouter(prefix="/api", tags=["patients"])


@router.get("/me", response_model=PatientOut)
def read_me(user: CurrentUser = Depends(get_current_user)) -> PatientOut:
    return patient_out(
        user.id,
        {
            "patient_code": user.patient_code,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
        },
    )


@router.patch("/me", response_model=PatientOut)
def update_me(
    payload: ProfileUpdate, user: CurrentUser = Depends(get_current_user)
) -> PatientOut:
    changes = payload.model_dump(exclude_none=True)
    data = update_profile(user.id, changes)
    return patient_out(user.id, data)
