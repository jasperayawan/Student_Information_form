from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException

from core.security import (bearer_token, create_session, delete_session, get_current_user,
                           hash_password, verify_password)
from core.settings import get_settings
from database import get_db
from schemas.user import LoginRequest, PasswordChange

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(credentials: LoginRequest, conn=Depends(get_db)) -> dict[str, Any]:
    user = conn.execute(
        "SELECT id, password_hash, is_active FROM users WHERE username = ?", (credentials.username,)
    ).fetchone()
    if user is None or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="This account has been deactivated.")
    token = create_session(conn, user["id"])
    conn.commit()
    return {"success": True, "token": token}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), conn=Depends(get_db)) -> dict[str, Any]:
    delete_session(conn, bearer_token(authorization))
    conn.commit()
    return {"success": True, "message": "Logged out."}


@router.get("/me")
def me(user=Depends(get_current_user), conn=Depends(get_db)) -> dict[str, Any]:
    user["enrollment_enabled"] = get_settings(conn)["student_enrollment_enabled"]
    return {"success": True, "data": user}


@router.post("/change-password")
def change_password(body: PasswordChange, user=Depends(get_current_user),
                    conn=Depends(get_db)) -> dict[str, Any]:
    stored = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not verify_password(body.current_password, stored["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), user["id"]))
    conn.commit()
    return {"success": True, "message": "Password changed."}
