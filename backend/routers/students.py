from typing import Any
import secrets
from fastapi import APIRouter, HTTPException
from schemas.student import StudentCreate, StudentUpdate
from database import get_connection

students: list = []

router = APIRouter(
    prefix="/students",
    tags=["Students"]
)


@router.post("/")
def create_student_form(student: StudentCreate) -> dict[str, Any]:

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO students 
            (name, age, course, birth_date, address, contact_number) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            student.name, student.age, student.course, student.birth_date, student.address, student.contact_number
        ))

        conn.commit()

        student_id = f"STU-{secrets.token_hex(4)}"

        return {
            "success": True,
            "message": "Student created successfully",
            "data": {
                "id": student_id,
                "name": student.name,
                "age": student.age,
                "course": student.course,
                "birth_date": student.birth_date,
                "address": student.address,
                "contact_number": student.contact_number
            }
        }
    except Exception as exc:
        print(f"DEBUG ERROR: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Unable to create student."
        ) from exc
    finally:
        if conn:
            conn.close()


@router.get("/")
def get_students() -> dict[str, Any]:
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students")
        rows = cursor.fetchall()

        student_list = [dict(row) for row in rows]

        return {
            "success": True,
            "data": student_list
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve students."
        ) from exc
    finally:
        if conn:
            conn.close()


@router.put("/{student_id}")
def update_student(student_id: str, student: StudentUpdate) -> dict[str, Any]:
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM students WHERE id = ?", (student_id,))
        existing_student = cursor.fetchone()

        if not existing_student:
            raise HTTPException(
                status_code=404,
                detail=f"Student with ID {student_id} not found."
            )

        cursor.execute("""
                UPDATE students 
                SET name = ?, age = ?, course = ?, birth_date = ?, address = ?, contact_number = ?
                WHERE id = ?
                """, (
            student.name, student.age, student.course, student.birth_date, student.address, student.contact_number,
            student_id
        ))

        conn.commit()

        return {
            "success": True,
            "message": "Student updated successfully.",
            "data": {
                "id": student_id,
                "name": student.name,
                "age": student.age,
                "course": student.course,
                "birth_date": student.birth_date,
                "address": student.address,
                "contact_number": student.contact_number
            }
        }
    except HTTPException as he:
        raise he
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to update student."
        ) from exc
    finally:
        if conn:
            conn.close()


@router.delete("/{student_id}")
def delete_student(student_id: str) -> dict[str, Any]:
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        conn.commit()

        return {
            "success":  True,
            "message": "Student deleted successfully"
        }

    except HTTPException:
        raise

    except Exception as exc:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to delete student"
        ) from exc
    finally:
        if conn:
            conn.close()
