"""
Database connection helper with optional SQLite fallback.

By default the project uses MySQL (mysql-connector-python). For local
development without MySQL you can set the environment variable
`LOYALTY_USE_SQLITE=1` and a SQLite DB `loyalty.db` in the project
folder will be used instead.
"""

import os
import sqlite3
from typing import Any, List, Dict

USE_SQLITE = os.environ.get("LOYALTY_USE_SQLITE") == "1"

if not USE_SQLITE:
    import mysql.connector
    from mysql.connector import Error
    from config import DB_CONFIG


def get_connection():
    """Return a new DB connection (MySQL or SQLite based on env)."""
    if USE_SQLITE:
        db_path = os.path.join(os.path.dirname(__file__), "loyalty.db")
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn
    else:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            return conn
        except Error as e:
            print(f"[DB ERROR] Could not connect to MySQL: {e}")
            raise


def _sqlite_rows_to_dict(rows):
    if rows is None:
        return None
    if isinstance(rows, list):
        return [dict(r) for r in rows]
    return dict(rows)


def run_query(query: str, params=None, fetch: bool = False, many: bool = False, commit: bool = False) -> Any:
    """
    Generic helper to run a query.
    - fetch=True   -> returns list of dict rows (or single dict if many=True)
    - commit=True  -> commits the transaction (for INSERT/UPDATE/DELETE)
    - many=True    -> when fetch=True return a single row (fetchone)
    """
    conn = get_connection()
    try:
        if USE_SQLITE:
            cursor = conn.cursor()
            # convert MySQL-style %s placeholders to SQLite ? placeholders
            q = query.replace("%s", "?")
            cursor.execute(q, params or ())
            result = None
            if fetch:
                if many:
                    row = cursor.fetchone()
                    result = dict(row) if row else None
                else:
                    rows = cursor.fetchall()
                    result = [dict(r) for r in rows]
            if commit:
                conn.commit()
                result = cursor.lastrowid
            return result
        else:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(query, params or ())
                result = None
                if fetch:
                    result = cursor.fetchone() if many else cursor.fetchall()
                if commit:
                    conn.commit()
                    result = cursor.lastrowid
                return result
            except Error as e:
                conn.rollback()
                print(f"[DB ERROR] {e}")
                raise
            finally:
                cursor.close()
    finally:
        conn.close()
