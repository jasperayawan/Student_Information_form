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
        (SELECT COUNT(*) FROM sections s WHERE s.subject_id = sub.id) AS section_count,
        (SELECT COUNT(*) FROM enrollments e JOIN sections s ON s.id = e.section_id
         WHERE s.subject_id = sub.id) AS enrolled_count
    FROM subjects sub JOIN courses c ON c.id = sub.course_id
"""


def assigned_instructor(user) -> int | None:
    """Instructors only see the subjects they are assigned to teach. Returns
    their instructor id (0 if the account isn't linked to one, which matches
    nothing), or None for roles that see every subject."""
    if user["role"] != "instructor":
        return None
    return user["instructor_id"] or 0


def section_scope(user) -> tuple[str, int] | None:
    """Which sections limit what a user sees of the subjects, as an SQL
    condition on a sections row aliased `s` plus its parameter: instructors
    see the subjects they teach, students the subjects they are enrolled in,
    and every other role sees all subjects (None)."""
    if user["role"] == "instructor":
        return "s.instructor_id = ?", user["instructor_id"] or 0
    if user["role"] == "student":
        return "s.id IN (SELECT section_id FROM enrollments WHERE student_id = ?)", user["student_id"] or 0
    return None


def _subject_query(scope: tuple[str, int] | None) -> tuple[str, list]:
    """SELECT for subjects plus its parameters. With a scope, only subjects
    that have a matching section are listed, and the section/enrolled counts
    cover only those sections."""
    if scope is None:
        return SUBJECT_SELECT + " WHERE 1 = 1", []
    condition, who = scope
    return f"""
        SELECT sub.*, c.code AS course_code,
            (SELECT COUNT(*) FROM sections s WHERE s.subject_id = sub.id AND {condition}) AS section_count,
            (SELECT COUNT(*) FROM enrollments e JOIN sections s ON s.id = e.section_id
             WHERE s.subject_id = sub.id AND {condition}) AS enrolled_count
        FROM subjects sub JOIN courses c ON c.id = sub.course_id
        WHERE EXISTS (SELECT 1 FROM sections s WHERE s.subject_id = sub.id AND {condition})
    """, [who, who, who]


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
    sql, params = _subject_query(section_scope(user))
    if course_id:
        sql += " AND sub.course_id = ?"
        params.append(course_id)
    subjects = fetch_all(conn, sql + " ORDER BY c.code, sub.code", tuple(params))

    per_day = offerings_per_day(conn)
    for subject in subjects:
        days = per_day.get(subject["id"], {})
        meeting_days = [n for n in days.values() if n > 0]
        subject["offerings_per_day"] = days
        subject["meets_offering_minimum"] = bool(meeting_days) and min(meeting_days) >= MIN_OFFERINGS_PER_DAY
    return {"success": True, "data": subjects, "min_offerings_per_day": MIN_OFFERINGS_PER_DAY}


@router.get("/{subject_id}")
def get_subject(subject_id: int, user=Depends(require("subjects.view")), conn=Depends(get_db)) -> dict[str, Any]:
    scope = section_scope(user)
    sql, params = _subject_query(scope)
    subject = fetch_one_or_404(conn, sql + " AND sub.id = ?", (*params, subject_id), "Subject not found.")
    condition, extra = (f" AND {scope[0]}", (scope[1],)) if scope else ("", ())
    subject["sections"] = fetch_all(
        conn, "SELECT s.* FROM v_sections s WHERE s.subject_id = ?" + condition
        + " ORDER BY s.pattern, s.start_time, s.section_code",
        (subject_id, *extra),
    )
    return {"success": True, "data": subject}


@router.get("/{subject_id}/students")
def get_subject_students(subject_id: int, user=Depends(require("subjects.view")),
                         conn=Depends(get_db)) -> dict[str, Any]:
    """Students enrolled in a subject. Instructors get only the students in
    their own sections; enrollment staff get every section; anyone else
    (e.g. students) may not see other students."""
    teacher = assigned_instructor(user)
    if teacher is None and "enrollments.view" not in user["permissions"]:
        raise HTTPException(status_code=403, detail="You do not have permission to view enrolled students.")
    sql, params = _subject_query(None if teacher is None else ("s.instructor_id = ?", teacher))
    fetch_one_or_404(conn, sql + " AND sub.id = ?", (*params, subject_id), "Subject not found.")
    section_filter = "" if teacher is None else " AND v.instructor_id = ?"
    students = fetch_all(
        conn,
        """SELECT e.id AS enrollment_id, e.enrolled_at, st.id AS student_id, st.student_number, st.name,
                  st.email, st.year_level, v.id AS section_id, v.section_code, v.pattern, v.start_time,
                  v.end_time, v.room_code, v.instructor_name
           FROM enrollments e
           JOIN students st ON st.id = e.student_id
           JOIN v_sections v ON v.id = e.section_id
           WHERE v.subject_id = ?""" + section_filter + " ORDER BY st.name",
        (subject_id,) if teacher is None else (subject_id, teacher),
    )
    return {"success": True, "data": students}


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
