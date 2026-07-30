from datetime import date
from pydantic import BaseModel


class StudentBase(BaseModel):
    name: str
    age: int
    course: str
    birth_date: str
    address: str
    contact_number: int


class StudentCreate(StudentBase):
    pass


class StudentUpdate(StudentBase):
    pass


class StudentResponse(StudentBase):
    id: int
