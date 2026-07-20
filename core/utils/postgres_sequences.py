"""PostgreSQL sequence helpers for trial/admin cleanup tools."""

from __future__ import annotations

from django.db import connection


def reset_sequence(table: str, pk_column: str = "id") -> int | None:
    """
    Reset a table's sequence.

    - Empty table → next insert gets id=1 (setval(..., 1, false)).
    - Non-empty → next insert gets MAX(pk)+1.

    Returns the next value that will be issued, or None when no sequence exists
    (e.g. SQLite test backend without serial sequences).
    """
    if connection.vendor != "postgresql":
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_serial_sequence(%s, %s)",
            [table, pk_column],
        )
        row = cursor.fetchone()
        sequence_name = row[0] if row else None
        if not sequence_name:
            return None

        cursor.execute(
            f'SELECT COALESCE(MAX("{pk_column}"), 0) FROM "{table}"'
        )
        max_id = int(cursor.fetchone()[0] or 0)

        if max_id <= 0:
            cursor.execute("SELECT setval(%s, 1, false)", [sequence_name])
            return 1

        cursor.execute("SELECT setval(%s, %s, true)", [sequence_name, max_id])
        return max_id + 1
