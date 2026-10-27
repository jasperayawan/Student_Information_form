from typing import Any
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from core.db_helpers import count, fetch_all, fetch_one_or_404, insert_row, update_row
from core.ids import generate_student_number
from core.security import get_current_user, require
from core.uploads import MAX_PHOTO_BYTES, MEDIA_TYPES, delete_photo, photo_path, save_photo, validate_photo
from database import get_db
from schemas.student import StudentCreate, StudentSelfUpdate, StudentUpdate

router = APIRouter(
    prefix="/students",
    tags=["Students"]
)

STUDENT_SELECT = """
    SELECT s.*, c.code AS course, c.name AS course_name
    FROM students s JOIN courses c ON c.id = s.course_id
"""


def get_student(conn, student_id: int) -> dict[str, Any]:
    return fetch_one_or_404(
        conn, STUDENT_SELECT + " WHERE s.id = ?", (student_id,),
        f"Student with ID {student_id} not found."
    )


def _validate_student(conn, student, student_id: int | None = None) -> None:
    if not conn.execute("SELECT 1 FROM courses WHERE id = ?", (student.course_id,)).fetchone():
        raise HTTPException(status_code=422, detail="The selected course does not exist.")
    if conn.execute(
        "SELECT 1 FROM students WHERE email = ? AND id IS NOT ?", (student.email, student_id)
    ).fetchone():
        raise HTTPException(status_code=409, detail="Another student already uses this email address.")


def _student_values(student) -> dict[str, Any]:
    values = student.model_dump()
    values["birth_date"] = student.birth_date.isoformat()
    return values


@router.get("/me")
def get_my_record(user=Depends(require("self.profile")), conn=Depends(get_db)) -> dict[str, Any]:
    if not user["student_id"]:
        raise HTTPException(status_code=404, detail="No student record is linked to this account.")
    return {"success": True, "data": get_student(conn, user["student_id"])}


@router.put("/me")
def update_my_record(changes: StudentSelfUpdate, user=Depends(require("self.profile")),
                     conn=Depends(get_db)) -> dict[str, Any]:
    if not user["student_id"]:
        raise HTTPException(status_code=404, detail="No student record is linked to this account.")
    if conn.execute(
        "SELECT 1 FROM students WHERE email = ? AND id IS NOT ?", (changes.email, user["student_id"])
    ).fetchone():
        raise HTTPException(status_code=409, detail="Another student already uses this email address.")
    update_row(conn, "students", user["student_id"], changes.model_dump())
    conn.commit()
    return {
        "success": True,
        "message": "Your information was updated.",
        "data": get_student(conn, user["student_id"]),
    }


@router.post("/", status_code=201)
def create_student_form(student: StudentCreate, user=Depends(require("students.manage")),
                        conn=Depends(get_db)) -> dict[str, Any]:
    _validate_student(conn, student)
    values = _student_values(student)
    # The student ID (current year + random 4 digits) is always generated
    # here, never taken from the client.
    values["student_number"] = generate_student_number(conn)
    new_id = insert_row(conn, "students", values)
    conn.commit()
    return {
        "success": True,
        "message": f"Student registered with ID {values['student_number']}.",
        "data": get_student(conn, new_id),
    }


@router.get("/")
def get_students(
    q: str = "",
    course_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user=Depends(require("students.view")),
    conn=Depends(get_db),
) -> dict[str, Any]:
    conditions, params = [], []
    if q.strip():
        like = f"%{q.strip()}%"
        conditions.append(
            "(s.name LIKE ? OR s.student_number LIKE ? OR s.email LIKE ? "
            "OR s.address LIKE ? OR c.code LIKE ?)"
        )
        params += [like] * 5
    if course_id:
        conditions.append("s.course_id = ?")
        params.append(course_id)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = count(conn, "SELECT COUNT(*) FROM students s JOIN courses c ON c.id = s.course_id" + where,
                  tuple(params))
    students = fetch_all(
        conn, STUDENT_SELECT + where + " ORDER BY s.id LIMIT ? OFFSET ?",
        (*params, page_size, (page - 1) * page_size),
    )
    return {"success": True, "data": students, "total": total, "page": page, "page_size": page_size}


@router.get("/{student_id}")
def get_student_detail(student_id: int, user=Depends(require("students.view")),
                       conn=Depends(get_db)) -> dict[str, Any]:
    student = get_student(conn, student_id)
    student["enrollments"] = fetch_all(
        conn,
        """SELECT e.id AS enrollment_id, v.* FROM enrollments e
           JOIN v_sections v ON v.id = e.section_id WHERE e.student_id = ?
           ORDER BY v.pattern, v.start_time""",
        (student_id,),
    )
    return {"success": True, "data": student}


@router.put("/{student_id}")
def update_student(student_id: int, student: StudentUpdate, user=Depends(require("students.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    existing = get_student(conn, student_id)
    _validate_student(conn, student, student_id)
    if student.course_id != existing["course_id"]:
        enrolled = count(conn, "SELECT COUNT(*) FROM enrollments WHERE student_id = ?", (student_id,))
        if enrolled:
            raise HTTPException(
                status_code=409,
                detail=f"This student is enrolled in {enrolled} class section(s) of their current course. "
                       "Drop those enrollments before changing the course.",
            )
    update_row(conn, "students", student_id, _student_values(student))
    conn.commit()
    return {
        "success": True,
        "message": "Student updated successfully.",
        "data": get_student(conn, student_id),
    }


@router.delete("/{student_id}")
def delete_student(student_id: int, user=Depends(require("students.manage")),
                   conn=Depends(get_db)) -> dict[str, Any]:
    get_student(conn, student_id)
    enrolled = count(conn, "SELECT COUNT(*) FROM enrollments WHERE student_id = ?", (student_id,))
    if enrolled:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: this student is enrolled in {enrolled} class section(s). "
                   "Drop the enrollments first.",
        )
    # The linked login account (if any) is removed by ON DELETE CASCADE.
    photo = conn.execute("SELECT photo FROM students WHERE id = ?", (student_id,)).fetchone()["photo"]
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    delete_photo(photo)
    return {
        "success": True,
        "message": "Student deleted successfully"
    }


# ---------- Student photo ----------

@router.get("/{student_id}/photo")
def get_student_photo(student_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    """Photos are personal data: staff who can view students, or the
    student themselves, may load them."""
    if "students.view" not in user["permissions"] and user["student_id"] != student_id:
        raise HTTPException(status_code=403, detail="You do not have permission to view this photo.")
    student = get_student(conn, student_id)
    path = photo_path(student["photo"])
    if path is None:
        raise HTTPException(status_code=404, detail="This student has no photo.")
    return FileResponse(path, media_type=MEDIA_TYPES[path.suffix],
                        headers={"Cache-Control": "private, max-age=86400"})


@router.put("/{student_id}/photo")
async def upload_student_photo(student_id: int, photo: UploadFile = File(...),
                               user=Depends(require("students.manage")), conn=Depends(get_db)) -> dict[str, Any]:
    old = get_student(conn, student_id)["photo"]
    data = await photo.read(MAX_PHOTO_BYTES + 1)
    name = save_photo(data, validate_photo(data))
    update_row(conn, "students", student_id, {"photo": name})
    conn.commit()
    delete_photo(old)
    return {"success": True, "message": "Photo uploaded.", "data": get_student(conn, student_id)}


@router.delete("/{student_id}/photo")
def remove_student_photo(student_id: int, user=Depends(require("students.manage")),
                         conn=Depends(get_db)) -> dict[str, Any]:
    old = get_student(conn, student_id)["photo"]
    update_row(conn, "students", student_id, {"photo": None})
    conn.commit()
    delete_photo(old)
    return {"success": True, "message": "Photo removed."}
