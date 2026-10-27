from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import count, fetch_all, fetch_one_or_404, insert_row, update_row
from core.scheduling import MIN_OFFERINGS_PER_DAY, offerings_per_day
from core.security import require
from database import get_db
from schemas.catalog import SubjectCreate, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["Subjects"])

SUBJECT_SELECT = """
    SELECT sub.*, c.code AS course_code,
        (SELECT COUNT(*) FROM sections s WHERE s.subject_id = sub.id) AS section_count
    FROM subjects sub JOIN courses c ON c.id = sub.course_id
"""


def _validate(conn, subject, subject_id: int | None = None) -> None:
    if not conn.execute("SELECT 1 FROM courses WHERE id = ?", (subject.course_id,)).fetchone():
        raise HTTPException(status_code=422, detail="The selected course does not exist.")
    if conn.execute(
        "SELECT 1 FROM subjects WHERE code = ? AND id IS NOT ?", (subject.code, subject_id)
    ).fetchone():
        raise HTTPException(status_code=409, detail=f"Subject code {subject.code} already exists.")


@router.get("/")
def get_subjects(course_id: int | None = None, user=Depends(require("subjects.view")),
                 conn=Depends(get_db)) -> dict[str, Any]:
    if course_id:
        subjects = fetch_all(conn, SUBJECT_SELECT + " WHERE sub.course_id = ? ORDER BY sub.code", (course_id,))
    else:
        subjects = fetch_all(conn, SUBJECT_SELECT + " ORDER BY c.code, sub.code")

    per_day = offerings_per_day(conn)
    for subject in subjects:
        days = per_day.get(subject["id"], {})
        meeting_days = [n for n in days.values() if n > 0]
        subject["offerings_per_day"] = days
        subject["meets_offering_minimum"] = bool(meeting_days) and min(meeting_days) >= MIN_OFFERINGS_PER_DAY
    return {"success": True, "data": subjects, "min_offerings_per_day": MIN_OFFERINGS_PER_DAY}


@router.get("/{subject_id}")
def get_subject(subject_id: int, user=Depends(require("subjects.view")), conn=Depends(get_db)) -> dict[str, Any]:
    subject = fetch_one_or_404(conn, SUBJECT_SELECT + " WHERE sub.id = ?", (subject_id,), "Subject not found.")
    subject["sections"] = fetch_all(
        conn, "SELECT * FROM v_sections WHERE subject_id = ? ORDER BY pattern, start_time, section_code",
        (subject_id,),
    )
    return {"success": True, "data": subject}


@router.post("/", status_code=201)
def create_subject(subject: SubjectCreate, user=Depends(require("subjects.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    _validate(conn, subject)
    new_id = insert_row(conn, "subjects", subject.model_dump())
    conn.commit()
    return {"success": True, "message": f"Subject {subject.code} created.", "data": {"id": new_id}}


@router.put("/{subject_id}")
def update_subject(subject_id: int, subject: SubjectUpdate, user=Depends(require("subjects.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    existing = fetch_one_or_404(conn, "SELECT * FROM subjects WHERE id = ?", (subject_id,), "Subject not found.")
    _validate(conn, subject, subject_id)
    if subject.course_id != existing["course_id"]:
        enrolled = count(
            conn, "SELECT COUNT(*) FROM enrollments e JOIN sections s ON s.id = e.section_id WHERE s.subject_id = ?",
            (subject_id,),
        )
        if enrolled:
            raise HTTPException(
                status_code=409,
                detail=f"{enrolled} student(s) are enrolled in this subject. "
                       "It cannot be moved to another course while it has enrollments.",
            )
    update_row(conn, "subjects", subject_id, subject.model_dump())
    conn.commit()
    return {"success": True, "message": "Subject updated successfully."}


@router.delete("/{subject_id}")
def delete_subject(subject_id: int, user=Depends(require("subjects.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    fetch_one_or_404(conn, "SELECT id FROM subjects WHERE id = ?", (subject_id,), "Subject not found.")
    sections = count(conn, "SELECT COUNT(*) FROM sections WHERE subject_id = ?", (subject_id,))
    if sections:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: this subject has {sections} scheduled section(s). Remove them first.",
        )
    conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()
    return {"success": True, "message": "Subject deleted successfully."}
