from typing import Literal, Optional
from pydantic import Field

from core.scheduling import MAX_SECTION_CAPACITY, TIME_PATTERN
from schemas.common import CleanModel


class TimeSlotCreate(CleanModel):
    pattern: Literal["MWF", "TTH"]
    start_time: str = Field(pattern=TIME_PATTERN, description="24-hour HH:MM")
    end_time: str = Field(pattern=TIME_PATTERN, description="24-hour HH:MM")
    is_exception: bool = False
    note: str = Field(default="", max_length=200)


class SectionBase(CleanModel):
    subject_id: int
    section_code: str = Field(min_length=1, max_length=10)
    time_slot_id: int
    instructor_id: Optional[int] = None
    classroom_id: Optional[int] = None
    capacity: int = Field(default=MAX_SECTION_CAPACITY, ge=1, le=MAX_SECTION_CAPACITY)


class SectionCreate(SectionBase):
    pass


class SectionUpdate(SectionBase):
    pass


class EnrollmentCreate(CleanModel):
    student_id: int
    section_id: int


class SelfEnrollmentCreate(CleanModel):
    section_id: int


class SettingsUpdate(CleanModel):
    room_open_time: str = Field(pattern=TIME_PATTERN)
    room_close_time: str = Field(pattern=TIME_PATTERN)
    mwf_duration_minutes: int = Field(ge=15, le=300)
    tth_duration_minutes: int = Field(ge=15, le=300)
    student_enrollment_enabled: bool
