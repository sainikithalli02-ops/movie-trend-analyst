"""Read-only SQLite connection + schema introspection for prompt building."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "trendscout.db"


def get_read_only_connection() -> sqlite3.Connection:
    """
    Opens the DB in SQLite's URI read-only mode, so even if a guardrail
    were somehow bypassed, the connection itself physically cannot write.
    """
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_description() -> str:
    """
    Builds a compact CREATE-TABLE summary of the schema to hand to the LLM
    as grounding context -- this is what lets the model write correct SQL
    against *this* database instead of guessing column names.
    """
    conn = get_read_only_connection()
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL"
    ).fetchall()
    conn.close()
    return "\n\n".join(r["sql"] for r in rows)


def run_query(sql: str):
    conn = get_read_only_connection()
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = [dict(row) for row in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()
