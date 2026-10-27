from typing import Any
from fastapi import HTTPException


def fetch_one_or_404(conn, sql: str, params: tuple, message: str) -> dict[str, Any]:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=message)
    return dict(row)


def fetch_all(conn, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def count(conn, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


# Table and column names below always come from our own code, never from
# user input; values are passed as parameters.
def insert_row(conn, table: str, data: dict[str, Any]) -> int:
    columns = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    cursor = conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(data.values())
    )
    return cursor.lastrowid


def update_row(conn, table: str, row_id: int, data: dict[str, Any]) -> None:
    assignments = ", ".join(f"{column} = ?" for column in data)
    conn.execute(
        f"UPDATE {table} SET {assignments} WHERE id = ?", (*data.values(), row_id)
    )
