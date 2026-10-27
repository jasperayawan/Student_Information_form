from typing import Literal, Optional
from pydantic import Field

from schemas.common import CleanModel

Role = Literal["student", "instructor", "admin", "college_admin"]


class LoginRequest(CleanModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class PasswordChange(CleanModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class UserCreate(CleanModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)
    role: Role
    student_id: Optional[int] = None
    instructor_id: Optional[int] = None


class UserUpdate(CleanModel):
    role: Role
    student_id: Optional[int] = None
    instructor_id: Optional[int] = None
    is_active: bool = True
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)
