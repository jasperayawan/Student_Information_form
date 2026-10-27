from datetime import date
from typing import Literal, Optional
from pydantic import Field, field_validator

from schemas.common import CleanModel, EMAIL_PATTERN, PHONE_PATTERN, to_text


class StudentBase(CleanModel):
    # Personal background
    name: str = Field(min_length=2, max_length=120)
    age: int = Field(ge=5, le=120)
    birth_date: date
    sex: Literal["Male", "Female"]
    address: str = Field(min_length=2, max_length=255)
    contact_number: str = Field(pattern=PHONE_PATTERN)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)

    # Educational background
    previous_school: str = Field(min_length=2, max_length=200)
    previous_attainment: str = Field(min_length=2, max_length=120)
    course_id: int
    year_level: Optional[int] = Field(default=None, ge=1, le=6)

    _contact_text = field_validator("contact_number", mode="before")(to_text)

    @field_validator("birth_date")
    @classmethod
    def birth_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Birth date cannot be in the future.")
        return value


class StudentCreate(StudentBase):
    pass


class StudentUpdate(StudentBase):
    pass


class StudentSelfUpdate(CleanModel):
    """The fields a student may change on their own record."""
    address: str = Field(min_length=2, max_length=255)
    contact_number: str = Field(pattern=PHONE_PATTERN)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)

    _contact_text = field_validator("contact_number", mode="before")(to_text)


class StudentResponse(StudentBase):
    id: int
    student_number: str
