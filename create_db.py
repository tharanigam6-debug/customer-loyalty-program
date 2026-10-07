"""
Create the `loyalty_program` database by executing `schema.sql`.

Usage: python create_db.py

This reads DB credentials from config.DB_CONFIG. If your MySQL server
requires a different user/password, update `config.py` first.
"""
import os
import sys
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def normalize_schema(sql_text):
    # Remove DELIMITER markers used for manual mysql client runs so the
    # connector can execute the CREATE PROCEDURE block as a single statement.
    sql = sql_text.replace("DELIMITER $$", "")
    sql = sql.replace("DELIMITER ;", "")
    sql = sql.replace("END$$", "END;")
    return sql


def main():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        print(f"schema.sql not found at: {schema_path}")
        sys.exit(1)

    sql = load_schema(schema_path)
    sql = normalize_schema(sql)

    cfg = DB_CONFIG.copy()
    # Connect without selecting a database so we can create it
    cfg.pop("database", None)

    try:
        conn = mysql.connector.connect(**cfg)
        cursor = conn.cursor()
        print("Connected to MySQL server, applying schema...")
        for result in cursor.execute(sql, multi=True):
            if result.with_rows:
                try:
                    rows = result.fetchall()
                except Exception:
                    rows = None
        print("Schema applied successfully.")
    except Error as e:
        print(f"[ERROR] Could not apply schema: {e}")
        sys.exit(2)
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
