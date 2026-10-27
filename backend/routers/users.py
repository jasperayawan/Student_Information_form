from typing import Any
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import count, fetch_all, fetch_one_or_404, insert_row, update_row
from core.security import hash_password, require
from database import get_db
from schemas.user import UserCreate, UserUpdate

router = APIRouter(prefix="/users", tags=["Users and Roles"])

USER_SELECT = """
    SELECT u.id, u.username, u.role, u.student_id, u.instructor_id, u.is_active, u.created_at,
        st.name AS student_name, st.student_number,
        i.name AS instructor_name, i.instructor_number
    FROM users u
    LEFT JOIN students st ON st.id = u.student_id
    LEFT JOIN instructors i ON i.id = u.instructor_id
"""


def _validate_links(conn, body, user_id: int | None = None) -> None:
    """Student accounts must point to a student record, instructor accounts
    to an instructor record, and admin accounts to neither."""
    if body.role == "student":
        if not body.student_id or body.instructor_id:
            raise HTTPException(status_code=422, detail="A student account must be linked to one student record.")
        if not conn.execute("SELECT 1 FROM students WHERE id = ?", (body.student_id,)).fetchone():
            raise HTTPException(status_code=422, detail="The selected student does not exist.")
        if conn.execute("SELECT 1 FROM users WHERE student_id = ? AND id IS NOT ?",
                        (body.student_id, user_id)).fetchone():
            raise HTTPException(status_code=409, detail="That student already has an account.")
    elif body.role == "instructor":
        if not body.instructor_id or body.student_id:
            raise HTTPException(status_code=422,
                                detail="An instructor account must be linked to one instructor record.")
        if not conn.execute("SELECT 1 FROM instructors WHERE id = ?", (body.instructor_id,)).fetchone():
            raise HTTPException(status_code=422, detail="The selected instructor does not exist.")
        if conn.execute("SELECT 1 FROM users WHERE instructor_id = ? AND id IS NOT ?",
                        (body.instructor_id, user_id)).fetchone():
            raise HTTPException(status_code=409, detail="That instructor already has an account.")
    elif body.student_id or body.instructor_id:
        raise HTTPException(status_code=422, detail="Administrator accounts are not linked to student or instructor records.")


def _active_admins(conn, excluding: int) -> int:
    return count(conn, "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1 AND id <> ?", (excluding,))


@router.get("/")
def get_users(user=Depends(require("users.manage")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": fetch_all(conn, USER_SELECT + " ORDER BY u.role, u.username")}


@router.post("/", status_code=201)
def create_user(body: UserCreate, user=Depends(require("users.manage")), conn=Depends(get_db)) -> dict[str, Any]:
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (body.username,)).fetchone():
        raise HTTPException(status_code=409, detail=f"Username {body.username} is already taken.")
    _validate_links(conn, body)
    values = body.model_dump(exclude={"password"})
    values["password_hash"] = hash_password(body.password)
    new_id = insert_row(conn, "users", values)
    conn.commit()
    return {"success": True, "message": f"Account {body.username} created.", "data": {"id": new_id}}


@router.put("/{user_id}")
def update_user(user_id: int, body: UserUpdate, user=Depends(require("users.manage")),
                conn=Depends(get_db)) -> dict[str, Any]:
    existing = fetch_one_or_404(conn, "SELECT * FROM users WHERE id = ?", (user_id,), "User not found.")
    _validate_links(conn, body, user_id)
    losing_admin = existing["role"] == "admin" and (body.role != "admin" or not body.is_active)
    if losing_admin and _active_admins(conn, user_id) == 0:
        raise HTTPException(status_code=409, detail="At least one active administrator account is required.")
    values = body.model_dump(exclude={"password"})
    if body.password:
        values["password_hash"] = hash_password(body.password)
    update_row(conn, "users", user_id, values)
    if not body.is_active or body.password:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    return {"success": True, "message": "Account updated."}


@router.delete("/{user_id}")
def delete_user(user_id: int, user=Depends(require("users.manage")), conn=Depends(get_db)) -> dict[str, Any]:
    existing = fetch_one_or_404(conn, "SELECT * FROM users WHERE id = ?", (user_id,), "User not found.")
    if user_id == user["id"]:
        raise HTTPException(status_code=409, detail="You cannot delete your own account.")
    if existing["role"] == "admin" and _active_admins(conn, user_id) == 0:
        raise HTTPException(status_code=409, detail="At least one active administrator account is required.")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return {"success": True, "message": "Account deleted."}
