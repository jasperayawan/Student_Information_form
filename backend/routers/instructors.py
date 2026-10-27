from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import count, fetch_all, fetch_one_or_404, insert_row, update_row
from core.ids import INSTRUCTOR_ID_DIGITS, generate_unique_number
from core.security import require
from database import get_db
from schemas.instructor import InstructorCreate, InstructorUpdate

router = APIRouter(prefix="/instructors", tags=["Instructors"])

INSTRUCTOR_SELECT = """
    SELECT i.*,
        (SELECT COUNT(*) FROM sections s WHERE s.instructor_id = i.id) AS section_count
    FROM instructors i
"""


def get_instructor(conn, instructor_id: int) -> dict[str, Any]:
    return fetch_one_or_404(
        conn, INSTRUCTOR_SELECT + " WHERE i.id = ?", (instructor_id,),
        f"Instructor with ID {instructor_id} not found."
    )


def teaching_schedule(conn, instructor_id: int) -> list[dict[str, Any]]:
    return fetch_all(
        conn, "SELECT * FROM v_sections WHERE instructor_id = ? ORDER BY pattern, start_time",
        (instructor_id,),
    )


GENERAL_EDUCATION = "General Education"


def department_options(conn) -> list[dict[str, str]]:
    """Departments follow the course offerings (by course code), plus General
    Education. Placeholder courses (COURSE1-4) are left out until renamed."""
    options = [
        {"value": row["code"], "label": row["code"] if row["name"] == row["code"] else f"{row['code']} — {row['name']}"}
        for row in conn.execute("SELECT code, name FROM courses ORDER BY code")
        if not (row["code"].upper().startswith("COURSE") and row["code"][6:].isdigit())
    ]
    return options + [{"value": GENERAL_EDUCATION, "label": GENERAL_EDUCATION}]


def _check_department(conn, department: str) -> None:
    if department not in {option["value"] for option in department_options(conn)}:
        raise HTTPException(status_code=422, detail="Please choose a department from the list.")


def _check_email(conn, email: str, instructor_id: int | None = None) -> None:
    if conn.execute(
        "SELECT 1 FROM instructors WHERE email = ? AND id IS NOT ?", (email, instructor_id)
    ).fetchone():
        raise HTTPException(status_code=409, detail="Another instructor already uses this email address.")


@router.get("/me")
def my_teaching_schedule(user=Depends(require("self.teaching")), conn=Depends(get_db)) -> dict[str, Any]:
    if not user["instructor_id"]:
        raise HTTPException(status_code=404, detail="No instructor record is linked to this account.")
    instructor = get_instructor(conn, user["instructor_id"])
    instructor["sections"] = teaching_schedule(conn, user["instructor_id"])
    return {"success": True, "data": instructor}


@router.get("/departments")
def get_departments(user=Depends(require("instructors.view")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": department_options(conn)}


@router.get("/")
def get_instructors(user=Depends(require("instructors.view")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": fetch_all(conn, INSTRUCTOR_SELECT + " ORDER BY i.name")}


@router.get("/{instructor_id}")
def get_instructor_detail(instructor_id: int, user=Depends(require("instructors.view")),
                          conn=Depends(get_db)) -> dict[str, Any]:
    instructor = get_instructor(conn, instructor_id)
    instructor["sections"] = teaching_schedule(conn, instructor_id)
    return {"success": True, "data": instructor}


@router.post("/", status_code=201)
def create_instructor(instructor: InstructorCreate, user=Depends(require("instructors.manage")),
                      conn=Depends(get_db)) -> dict[str, Any]:
    _check_email(conn, instructor.email)
    _check_department(conn, instructor.department)
    values = instructor.model_dump()
    values["instructor_number"] = generate_unique_number(conn, "instructors", "instructor_number", INSTRUCTOR_ID_DIGITS)
    new_id = insert_row(conn, "instructors", values)
    conn.commit()
    return {
        "success": True,
        "message": f"Instructor registered with ID {values['instructor_number']}.",
        "data": get_instructor(conn, new_id),
    }


@router.put("/{instructor_id}")
def update_instructor(instructor_id: int, instructor: InstructorUpdate,
                      user=Depends(require("instructors.manage")), conn=Depends(get_db)) -> dict[str, Any]:
    existing = get_instructor(conn, instructor_id)
    _check_email(conn, instructor.email, instructor_id)
    _check_department(conn, instructor.department)
    if not instructor.is_active and existing["section_count"]:
        raise HTTPException(
            status_code=409,
            detail=f"This instructor is assigned to {existing['section_count']} class section(s). "
                   "Reassign them before marking the instructor inactive.",
        )
    update_row(conn, "instructors", instructor_id, instructor.model_dump())
    conn.commit()
    return {"success": True, "message": "Instructor updated successfully.",
            "data": get_instructor(conn, instructor_id)}


@router.delete("/{instructor_id}")
def delete_instructor(instructor_id: int, user=Depends(require("instructors.manage")),
                      conn=Depends(get_db)) -> dict[str, Any]:
    get_instructor(conn, instructor_id)
    assigned = count(conn, "SELECT COUNT(*) FROM sections WHERE instructor_id = ?", (instructor_id,))
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: this instructor is assigned to {assigned} class section(s). "
                   "Reassign those sections to another instructor first.",
        )
    conn.execute("DELETE FROM instructors WHERE id = ?", (instructor_id,))
    conn.commit()
    return {"success": True, "message": "Instructor deleted successfully."}
