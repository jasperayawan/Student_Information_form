"""Schemas for courses, subjects and classrooms."""
from typing import Literal
from pydantic import Field

from schemas.common import CleanModel


class CourseUpdate(CleanModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=500)


class SubjectBase(CleanModel):
    code: str = Field(min_length=2, max_length=20)
    title: str = Field(min_length=2, max_length=200, description="Descriptive title")
    units: Literal[2, 3]
    course_id: int


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(SubjectBase):
    pass


class ClassroomBase(CleanModel):
    room_code: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=100)
    capacity: int = Field(default=30, ge=1, le=500)
    is_active: bool = True


class ClassroomCreate(ClassroomBase):
    pass


class ClassroomUpdate(ClassroomBase):
    pass
