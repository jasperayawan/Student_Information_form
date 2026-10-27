from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException

from core.db_helpers import count, fetch_all, fetch_one_or_404, insert_row, update_row
from core.scheduling import slots_overlap
from core.security import require
from core.settings import get_settings
from database import get_db
from schemas.catalog import ClassroomCreate, ClassroomUpdate

router = APIRouter(prefix="/classrooms", tags=["Classrooms"])

CLASSROOM_SELECT = """
    SELECT r.*,
        (SELECT COUNT(*) FROM sections s WHERE s.classroom_id = r.id) AS section_count
    FROM classrooms r
"""


def _check_code(conn, room_code: str, classroom_id: int | None = None) -> None:
    if conn.execute(
        "SELECT 1 FROM classrooms WHERE room_code = ? AND id IS NOT ?", (room_code, classroom_id)
    ).fetchone():
        raise HTTPException(status_code=409, detail=f"Room {room_code} already exists.")


@router.get("/")
def get_classrooms(user=Depends(require("classrooms.view")), conn=Depends(get_db)) -> dict[str, Any]:
    return {"success": True, "data": fetch_all(conn, CLASSROOM_SELECT + " ORDER BY r.room_code")}


@router.get("/availability")
def room_availability(pattern: Literal["MWF", "TTH"] = "MWF", user=Depends(require("classrooms.view")),
                      conn=Depends(get_db)) -> dict[str, Any]:
    """Grid of rooms x configured time slots: each cell is either free or
    the section occupying (overlapping) that slot."""
    slots = fetch_all(conn, "SELECT * FROM time_slots WHERE pattern = ? ORDER BY start_time, end_time", (pattern,))
    sections = fetch_all(conn, "SELECT * FROM v_sections WHERE classroom_id IS NOT NULL")
    rooms = fetch_all(conn, "SELECT * FROM classrooms ORDER BY room_code")
    for room in rooms:
        booked = [s for s in sections if s["classroom_id"] == room["id"]]
        room["cells"] = []
        for slot in slots:
            occupant = next((s for s in booked if slots_overlap(slot, s)), None)
            room["cells"].append({
                "time_slot_id": slot["id"],
                "free": bool(room["is_active"]) and occupant is None,
                "section": occupant,
            })
    return {"success": True, "data": {"time_slots": slots, "rooms": rooms, "settings": get_settings(conn)}}


@router.get("/{classroom_id}")
def get_classroom(classroom_id: int, user=Depends(require("classrooms.view")),
                  conn=Depends(get_db)) -> dict[str, Any]:
    room = fetch_one_or_404(conn, CLASSROOM_SELECT + " WHERE r.id = ?", (classroom_id,), "Classroom not found.")
    room["sections"] = fetch_all(
        conn, "SELECT * FROM v_sections WHERE classroom_id = ? ORDER BY pattern, start_time", (classroom_id,)
    )
    return {"success": True, "data": room}


@router.post("/", status_code=201)
def create_classroom(room: ClassroomCreate, user=Depends(require("classrooms.manage")),
                     conn=Depends(get_db)) -> dict[str, Any]:
    _check_code(conn, room.room_code)
    new_id = insert_row(conn, "classrooms", room.model_dump())
    conn.commit()
    return {"success": True, "message": f"Room {room.room_code} added.", "data": {"id": new_id}}


@router.put("/{classroom_id}")
def update_classroom(classroom_id: int, room: ClassroomUpdate, user=Depends(require("classrooms.manage")),
                     conn=Depends(get_db)) -> dict[str, Any]:
    existing = fetch_one_or_404(conn, CLASSROOM_SELECT + " WHERE r.id = ?", (classroom_id,), "Classroom not found.")
    _check_code(conn, room.room_code, classroom_id)
    if not room.is_active and existing["section_count"]:
        raise HTTPException(
            status_code=409,
            detail=f"Room is assigned to {existing['section_count']} class section(s). "
                   "Move those sections to another room before marking it unavailable.",
        )
    too_big = count(
        conn, "SELECT COUNT(*) FROM sections WHERE classroom_id = ? AND capacity > ?",
        (classroom_id, room.capacity),
    )
    if too_big:
        raise HTTPException(
            status_code=409,
            detail=f"{too_big} section(s) in this room have more seats than {room.capacity}. "
                   "Lower their capacity or move them first.",
        )
    update_row(conn, "classrooms", classroom_id, room.model_dump())
    conn.commit()
    return {"success": True, "message": "Classroom updated successfully."}


@router.delete("/{classroom_id}")
def delete_classroom(classroom_id: int, user=Depends(require("classrooms.manage")),
                     conn=Depends(get_db)) -> dict[str, Any]:
    fetch_one_or_404(conn, "SELECT id FROM classrooms WHERE id = ?", (classroom_id,), "Classroom not found.")
    assigned = count(conn, "SELECT COUNT(*) FROM sections WHERE classroom_id = ?", (classroom_id,))
    if assigned:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: room is assigned to {assigned} class section(s). Reassign them first.",
        )
    conn.execute("DELETE FROM classrooms WHERE id = ?", (classroom_id,))
    conn.commit()
    return {"success": True, "message": "Classroom deleted successfully."}
