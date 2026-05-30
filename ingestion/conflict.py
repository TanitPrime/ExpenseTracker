# ingestion/conflict.py
from db.queries import (
    get_conn, get_all_conflicts, get_conflict_count,
    delete_conflict_by_hash, save_resolution,
    insert_expense, update_expense, delete_expense,get_expenses_by_date_range
)
from datetime import date, timedelta
import psycopg2

def get_conflict_queue(db_path: str) -> list:
    conn = get_conn(db_path)
    conflicts = [dict(row) for row in get_all_conflicts(conn)]
    conn.close()
    return conflicts

def get_context_rows(db_url: str, conflict: dict) -> list:
    context_date = conflict.get("context_date") or conflict.get("created_at", "")[:10]
    if not context_date:
        return []

    conn = get_conn(db_url)
    cur = conn.cursor()

    # fetch 5 rows strictly before the conflict date
    cur.execute(
        """SELECT * FROM expenses
           WHERE date <= %s
           ORDER BY date DESC, id DESC
           LIMIT 5""",
        (context_date,)
    )
    rows_before = list(reversed([dict(r) for r in cur.fetchall()]))

    # fetch 5 rows strictly after the conflict date
    cur.execute(
        """SELECT * FROM expenses
           WHERE date > %s
           ORDER BY date ASC, id ASC
           LIMIT 5""",
        (context_date,)
    )
    rows_after = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    conflict_row = {
        "id":          None,
        "date":        context_date,
        "amount":      "",
        "description": conflict["raw_line"],
        "is_conflict": True,
    }

    return rows_before + [conflict_row] + rows_after

def resolve_conflict(db_path: str, conflict_hash: str, grid_original: list, grid_current: list):
    """
    Commit all changes made in the context grid and record the conflict as resolved.

    grid_original: rows as they were when the grid was opened (includes id)
    grid_current:  rows as they are after user edits (may have new rows without id,
                   deleted rows will be absent)
    """
    conn = get_conn(db_path)

    original_ids = {row["id"] for row in grid_original if row.get("id")}
    current_ids  = {row["id"] for row in grid_current if row.get("id")}

    # deletions — rows in original but not in current
    deleted_ids = original_ids - current_ids
    for row_id in deleted_ids:
        delete_expense(conn, row_id)

    # updates — rows present in both, apply any edits
    for row in grid_current:
        if row.get("id") and row["id"] in original_ids:
            update_expense(conn, row["id"], {
                "date":        row["date"],
                "amount":      float(str(row["amount"]).replace(",", ".")),
                "description": row["description"],
            })

    # inserts — new rows added in the grid (no id)
    for row in grid_current:
        if not row.get("id"):
            if not row.get("date") or not row.get("amount") or not row.get("description"):
                continue
            try:
                amount = float(str(row["amount"]).replace(",", "."))
            except ValueError:
                continue
            insert_expense(conn, {
                "date":        row["date"],
                "amount":      amount,
                "description": row["description"],
                "raw_line":    None,
                "source_file": None,
            })

    # record resolution and remove from pending
    save_resolution(conn, conflict_hash, "resolved")
    delete_conflict_by_hash(conn, conflict_hash)

    conn.commit()
    conn.close()