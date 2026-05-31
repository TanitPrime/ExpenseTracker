# ingestion/pipeline.py
import csv
import re
from datetime import date, datetime
from typing import Optional
from db.queries import (
    get_conn, get_latest_expense_date, insert_expenses_batch,
    insert_conflicts_batch, get_resolution, delete_expenses_by_dates
)
from parser import parse_contents, ParsedRow, ConflictRow

CSV_FIELDS = {
    "date":        ["Date", "date"],
    "description": ["Purchase", "Description", "purchase", "description"],
    "category":    ["Category", "category"],
    "subcategory": ["Sub-category", "subcategory"],
    "amount":      ["Amount", "amount"],
    # Notes column is intentionally ignored
}

DATE_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
]


def _get_csv_value(row: dict, keys: list) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return ""


def _parse_amount(amount_str: str) -> Optional[float]:
    # strip currency prefix/suffix and normalise decimal separator
    cleaned = amount_str.strip()
    cleaned = re.sub(r"[^\d.,+-]", "", cleaned)   # remove anything not numeric
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(date_str: str) -> Optional[date]:
    date_str = date_str.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def parse_csv(content: str | bytes, filename: str) -> list[ParsedRow]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")

    source_file = filename.split("/")[-1]
    lines = content.splitlines()
    sample = "\n".join(lines[:10])

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(lines, dialect=dialect)
    parsed = []

    for row in reader:
        if not row:
            continue

        date_str    = _get_csv_value(row, CSV_FIELDS["date"]).strip()
        amount_str  = _get_csv_value(row, CSV_FIELDS["amount"]).strip()
        description = _get_csv_value(row, CSV_FIELDS["description"]).strip()
        category    = _get_csv_value(row, CSV_FIELDS["category"]).strip() or None
        subcategory = _get_csv_value(row, CSV_FIELDS["subcategory"]).strip() or None

        if not date_str or not amount_str:
            continue

        parsed_date   = _parse_date(date_str)
        parsed_amount = _parse_amount(amount_str)

        if parsed_date is None or parsed_amount is None:
            continue

        raw_line = "\t".join(filter(None, [date_str, description, category, subcategory, amount_str]))

        parsed.append(ParsedRow(
            date=parsed_date,
            amount=parsed_amount,
            description=description,
            raw_line=raw_line,
            source_file=source_file,
            category=category,
            subcategory=subcategory,
        ))

    return parsed


def ingest_file(db_url: str, content: str | bytes, filename: str) -> dict:
    if isinstance(content, bytes):
        content = content.decode("utf-8")

    conn = get_conn(db_url)
    is_csv = filename.lower().endswith(".csv")

    summary = {
        "status": None,
        "inserted": 0,
        "conflicts_new": 0,
        "conflicts_remembered": 0,
    }

    if is_csv:
        parsed_rows  = parse_csv(content, filename)
        conflict_rows = []
    else:
        parsed_rows, conflict_rows = parse_contents(content, filename)

    if not parsed_rows and not conflict_rows:
        summary["status"] = "empty"
        conn.close()
        return summary

    if is_csv:
        # CSV is source of truth — delete all existing rows for dates in the CSV
        # before reinserting so there are no duplicates or stale rows
        csv_dates = list({str(r.date) for r in parsed_rows})
        delete_expenses_by_dates(conn, csv_dates)

    else:
        # txt — apply date gate
        latest_sqlite = get_latest_expense_date(conn)
        txt_dates = [r.date for r in parsed_rows if r.date is not None]

        if latest_sqlite and txt_dates:
            latest_sqlite_date = date.fromisoformat(latest_sqlite)
            
            if not txt_dates:
                summary["status"] = "empty"
                conn.close()
                return summary

            if max(txt_dates) <= latest_sqlite_date:
                summary["status"] = "stale"
                conn.close()
                return summary

            valid_future_dates = [d for d in txt_dates if d > latest_sqlite_date]
            if not valid_future_dates:
                summary["status"] = "stale"
                conn.close()
                return summary

            cutoff = min(d for d in txt_dates if d > latest_sqlite_date)
            parsed_rows   = [r for r in parsed_rows   if r.date is not None and r.date >= cutoff]
            conflict_rows = [r for r in conflict_rows if r.context_date is not None and r.context_date >= cutoff]

    # Batch insert clean rows
    if parsed_rows:
        rows_to_insert = [
            {
                "date":        str(row.date),
                "amount":      row.amount,
                "description": row.description,
                "category":    row.category,
                "subcategory": row.subcategory,
                "raw_line":    row.raw_line,
                "source_file": row.source_file,
            }
            for row in parsed_rows
        ]
        insert_expenses_batch(conn, rows_to_insert)
        summary["inserted"] = len(rows_to_insert)

    # Batch insert unresolved conflicts
    if conflict_rows:
        unresolved_conflicts = []
        for conflict in conflict_rows:
            prior = get_resolution(conn, conflict.content_hash)
            if prior:
                summary["conflicts_remembered"] += 1
            else:
                unresolved_conflicts.append({
                    "raw_line":     conflict.raw_line,
                    "source_file":  conflict.source_file,
                    "issue":        conflict.issue,
                    "context_date": str(conflict.context_date) if conflict.context_date else None,
                    "content_hash": conflict.content_hash,
                })
        if unresolved_conflicts:
            insert_conflicts_batch(conn, unresolved_conflicts)
            summary["conflicts_new"] = len(unresolved_conflicts)

    summary["status"] = "ok"
    conn.commit()
    conn.close()
    return summary