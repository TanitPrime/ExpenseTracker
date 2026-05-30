# db/queries.py
from typing import Optional
import psycopg2
from db.init_db import get_conn


# --- expenses ---

def get_latest_expense_date(conn) -> Optional[str]:
    cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    cur.execute("SELECT MAX(date)::text FROM expenses")
    row = cur.fetchone()
    cur.close()
    return row[0] if row and row[0] else None

# db/queries.py
def delete_expenses_by_dates(conn, dates: list[str]):
    """Delete all expenses for a given list of dates. Used when CSV re-import is more truthy."""
    cur = conn.cursor()
    cur.executemany(
        "DELETE FROM expenses WHERE date = %s", [(d,) for d in dates]
    )
    cur.close()

def insert_expense(conn, row: dict):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO expenses (date, amount, description, category, subcategory, raw_line, source_file)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                row["date"],
                row["amount"],
                row.get("description"),
                row.get("category"),
                row.get("subcategory"),
                row.get("raw_line"),
                row.get("source_file"),
            )
        )

def update_expense(conn, expense_id: int, row: dict):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE expenses
               SET date = %s, amount = %s, description = %s
               WHERE id = %s""",
            (row["date"], row["amount"], row["description"], expense_id)
        )

def delete_expense(conn, expense_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))

def delete_expense_by_unique(conn, date: str, amount: float, description: str):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM expenses WHERE date = %s AND amount = %s AND description = %s",
            (date, amount, description)
        )

def get_expenses_by_date_range(conn, date_from: str, date_to: str) -> list:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM expenses
               WHERE date BETWEEN %s AND %s
               ORDER BY date ASC, id ASC""",
            (date_from, date_to)
        )
        return cur.fetchall()

def get_distinct_years(conn) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT EXTRACT(YEAR FROM date) AS year FROM expenses ORDER BY year ASC"
        )
        rows = cur.fetchall()
        return [int(row["year"]) for row in rows]

def get_distinct_months(conn) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT EXTRACT(MONTH FROM date) AS month FROM expenses ORDER BY month ASC"
        )
        rows = cur.fetchall()
        return [int(row["month"]) for row in rows]

def get_expense_stats_rows(conn, year: Optional[int] = None, month: Optional[int] = None) -> list:
    query = "SELECT amount, description, date FROM expenses"
    filters = []
    params = []

    if year:
        filters.append("EXTRACT(YEAR FROM date) = %s")
        params.append(year)
    if month:
        filters.append("EXTRACT(MONTH FROM date) = %s")
        params.append(month)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY date DESC, id DESC"
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()

# --- conflicts ---

def insert_conflict(conn, row: dict):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO conflicts_pending
               (raw_line, source_file, issue, context_date, content_hash)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (content_hash) DO NOTHING""",
            (row["raw_line"], row["source_file"], row["issue"], row["context_date"], row["content_hash"])
        )

def get_all_conflicts(conn) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM conflicts_pending ORDER BY created_at ASC"
        )
        return cur.fetchall()

def get_conflict_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM conflicts_pending"
        )
        row = cur.fetchone()
        return row["count"]

def delete_conflict(conn, conflict_id: int):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conflicts_pending WHERE id = %s", (conflict_id,))

def delete_conflict_by_hash(conn, content_hash: str):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM conflicts_pending WHERE content_hash = %s", (content_hash,)
        )

# --- conflict resolutions ---

def get_resolution(conn, content_hash: str) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT action FROM conflict_resolutions WHERE content_hash = %s", (content_hash,)
        )
        row = cur.fetchone()
        return row["action"] if row else None

def save_resolution(conn, content_hash: str, action: str):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO conflict_resolutions (content_hash, action)
               VALUES (%s, %s)
               ON CONFLICT (content_hash) DO UPDATE SET action = EXCLUDED.action""",
            (content_hash, action)
        )
