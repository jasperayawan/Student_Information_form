from pydantic import Field, field_validator

from schemas.common import CleanModel, EMAIL_PATTERN, PHONE_PATTERN, to_text


class InstructorBase(CleanModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    contact_number: str = Field(pattern=PHONE_PATTERN)
    department: str = Field(min_length=1, max_length=120)
    is_active: bool = True

    _contact_text = field_validator("contact_number", mode="before")(to_text)


class InstructorCreate(InstructorBase):
    pass


class InstructorUpdate(InstructorBase):
    pass
