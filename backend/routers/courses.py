from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import fetch_all, fetch_one_or_404, update_row
from core.scheduling import MIN_SUBJECTS_PER_COURSE
from core.security import require
from database import get_db
from schemas.catalog import CourseUpdate

# The system offers a fixed set of four courses, so courses can be renamed
# and described but not created or deleted through the API.
router = APIRouter(prefix="/courses", tags=["Courses"])

COURSE_SELECT = """
    SELECT c.*,
        (SELECT COUNT(*) FROM subjects s WHERE s.course_id = c.id) AS subject_count,
        (SELECT COUNT(*) FROM students st WHERE st.course_id = c.id) AS student_count
    FROM courses c
"""


def _with_rule(course: dict[str, Any]) -> dict[str, Any]:
    course["meets_subject_minimum"] = course["subject_count"] >= MIN_SUBJECTS_PER_COURSE
    return course


@router.get("/")
def get_courses(user=Depends(require("courses.view")), conn=Depends(get_db)) -> dict[str, Any]:
    courses = [_with_rule(c) for c in fetch_all(conn, COURSE_SELECT + " ORDER BY c.id")]
    return {"success": True, "data": courses, "min_subjects": MIN_SUBJECTS_PER_COURSE}


@router.get("/{course_id}")
def get_course(course_id: int, user=Depends(require("courses.view")), conn=Depends(get_db)) -> dict[str, Any]:
    course = _with_rule(fetch_one_or_404(conn, COURSE_SELECT + " WHERE c.id = ?", (course_id,),
                                         "Course not found."))
    course["subjects"] = fetch_all(
        conn, "SELECT * FROM subjects WHERE course_id = ? ORDER BY code", (course_id,)
    )
    return {"success": True, "data": course}


@router.put("/{course_id}")
def update_course(course_id: int, course: CourseUpdate, user=Depends(require("courses.manage")),
                  conn=Depends(get_db)) -> dict[str, Any]:
    existing = fetch_one_or_404(conn, "SELECT code FROM courses WHERE id = ?", (course_id,), "Course not found.")
    if conn.execute(
        "SELECT 1 FROM courses WHERE code = ? AND id <> ?", (course.code, course_id)
    ).fetchone():
        raise HTTPException(status_code=409, detail=f"Course code {course.code} is already used.")
    update_row(conn, "courses", course_id, course.model_dump())
    # Instructor departments are stored by course code, so follow a rename.
    conn.execute("UPDATE instructors SET department = ? WHERE department = ?", (course.code, existing["code"]))
    conn.commit()
    return {"success": True, "message": "Course updated successfully."}
