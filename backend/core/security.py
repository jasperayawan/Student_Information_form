import hashlib
import hmac
import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException

from core.permissions import ROLE_PERMISSIONS
from database import get_db

PBKDF2_ITERATIONS = 200_000
SESSION_HOURS = 12


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def _hash_token(token: str) -> str:
    # Only a hash of the session token is stored, so a leaked database
    # can't be used to log in.
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) "
        "VALUES (?, ?, datetime('now', ?))",
        (_hash_token(token), user_id, f"+{SESSION_HOURS} hours"),
    )
    return token


def delete_session(conn, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return authorization.removeprefix("Bearer ").strip()


def get_current_user(authorization: str | None = Header(default=None),
                     conn=Depends(get_db)) -> dict[str, Any]:
    token = bearer_token(authorization)
    row = conn.execute(
        """SELECT u.id, u.username, u.role, u.student_id, u.instructor_id
           FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token_hash = ? AND s.expires_at > datetime('now') AND u.is_active = 1""",
        (_hash_token(token),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    user = dict(row)
    user["permissions"] = sorted(ROLE_PERMISSIONS[user["role"]])
    return user


def require(permission: str):
    """Dependency factory: `user = Depends(require("students.manage"))`."""
    def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if permission not in user["permissions"]:
            raise HTTPException(status_code=403, detail="You do not have permission to do this.")
        return user
    return checker
