from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import fetch_all, fetch_one_or_404
from core.scheduling import student_conflicts
from core.security import require
from core.settings import get_settings
from database import get_db
from schemas.schedule import EnrollmentCreate, SelfEnrollmentCreate

router = APIRouter(prefix="/enrollments", tags=["Enrollments"])

ENROLLMENT_SELECT = """
    SELECT e.id AS enrollment_id, e.enrolled_at, e.student_id,
        st.student_number, st.name AS student_name, v.*
    FROM enrollments e
    JOIN students st ON st.id = e.student_id
    JOIN v_sections v ON v.id = e.section_id
"""


def enroll_student(conn, student_id: int, section_id: int) -> int:
    """All enrollment rules in one place. BEGIN IMMEDIATE takes the write
    lock first, so two people can't grab the last seat at the same time."""
    conn.execute("BEGIN IMMEDIATE")
    student = fetch_one_or_404(conn, "SELECT * FROM students WHERE id = ?", (student_id,), "Student not found.")
    section = fetch_one_or_404(conn, "SELECT * FROM v_sections WHERE id = ?", (section_id,),
                               "Class section not found.")

    if section["course_id"] != student["course_id"]:
        raise HTTPException(
            status_code=422,
            detail=f"{section['subject_code']} belongs to {section['course_code']}, "
                   "which is not this student's course.",
        )
    if conn.execute(
        """SELECT 1 FROM enrollments e JOIN sections s ON s.id = e.section_id
           WHERE e.student_id = ? AND s.subject_id = ?""",
        (student_id, section["subject_id"]),
    ).fetchone():
        raise HTTPException(status_code=409,
                            detail=f"Already enrolled in a section of {section['subject_code']}.")
    if section["available_slots"] <= 0:
        raise HTTPException(
            status_code=409,
            detail=f"{section['subject_code']} section {section['section_code']} is full "
                   f"({section['enrolled_count']}/{section['capacity']}).",
        )
    clashes = student_conflicts(conn, student_id, section)
    if clashes:
        raise HTTPException(status_code=409, detail=" ".join(clashes))

    new_id = conn.execute(
        "INSERT INTO enrollments (student_id, section_id) VALUES (?, ?)", (student_id, section_id)
    ).lastrowid
    conn.commit()
    return new_id


def _enrollment(conn, enrollment_id: int) -> dict[str, Any]:
    return fetch_one_or_404(conn, ENROLLMENT_SELECT + " WHERE e.id = ?", (enrollment_id,), "Enrollment not found.")


def _require_enrollment_open(conn) -> None:
    if not get_settings(conn)["student_enrollment_enabled"]:
        raise HTTPException(status_code=403, detail="Student self-enrollment is currently closed.")


def _my_student_id(user) -> int:
    if not user["student_id"]:
        raise HTTPException(status_code=404, detail="No student record is linked to this account.")
    return user["student_id"]


# ---------- Student self-service ----------

@router.get("/me")
def my_enrollments(user=Depends(require("self.enroll")), conn=Depends(get_db)) -> dict[str, Any]:
    student_id = _my_student_id(user)
    rows = fetch_all(conn, ENROLLMENT_SELECT + " WHERE e.student_id = ? ORDER BY v.pattern, v.start_time",
                     (student_id,))
    return {"success": True, "data": rows,
            "enrollment_enabled": get_settings(conn)["student_enrollment_enabled"]}


@router.post("/me", status_code=201)
def enroll_myself(body: SelfEnrollmentCreate, user=Depends(require("self.enroll")),
                  conn=Depends(get_db)) -> dict[str, Any]:
    _require_enrollment_open(conn)
    new_id = enroll_student(conn, _my_student_id(user), body.section_id)
    return {"success": True, "message": "You are enrolled.", "data": _enrollment(conn, new_id)}


@router.delete("/me/{enrollment_id}")
def drop_my_enrollment(enrollment_id: int, user=Depends(require("self.enroll")),
                       conn=Depends(get_db)) -> dict[str, Any]:
    _require_enrollment_open(conn)
    enrollment = _enrollment(conn, enrollment_id)
    if enrollment["student_id"] != _my_student_id(user):
        raise HTTPException(status_code=403, detail="You can only drop your own enrollments.")
    conn.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
    conn.commit()
    return {"success": True, "message": "Enrollment dropped."}


# ---------- Administration ----------

@router.get("/")
def get_enrollments(section_id: int | None = None, student_id: int | None = None,
                    user=Depends(require("enrollments.view")), conn=Depends(get_db)) -> dict[str, Any]:
    conditions, params = [], []
    if section_id:
        conditions.append("e.section_id = ?")
        params.append(section_id)
    if student_id:
        conditions.append("e.student_id = ?")
        params.append(student_id)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = fetch_all(conn, ENROLLMENT_SELECT + where + " ORDER BY e.enrolled_at DESC", tuple(params))
    return {"success": True, "data": rows}


@router.post("/", status_code=201)
def create_enrollment(body: EnrollmentCreate, user=Depends(require("enrollments.manage")),
                      conn=Depends(get_db)) -> dict[str, Any]:
    new_id = enroll_student(conn, body.student_id, body.section_id)
    return {"success": True, "message": "Student enrolled.", "data": _enrollment(conn, new_id)}


@router.delete("/{enrollment_id}")
def delete_enrollment(enrollment_id: int, user=Depends(require("enrollments.manage")),
                      conn=Depends(get_db)) -> dict[str, Any]:
    _enrollment(conn, enrollment_id)
    conn.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
    conn.commit()
    return {"success": True, "message": "Enrollment dropped."}
