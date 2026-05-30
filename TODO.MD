[] update db calls to work in batches
"es, that's exactly the problem. The current code inserts one row at a time in a loop:
pythonfor row in parsed_rows:
    insert_expense(conn, {...})
That's one round trip to Supabase per row. If you have thousands of rows that's thousands of individual network calls to a remote database, hence minutes.
Fix is executemany which sends all rows in a single batch:
python# db/queries.py
def insert_expenses_batch(conn, rows: list[dict]):
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO expenses (date, amount, description, category, subcategory, raw_line, source_file)
           VALUES (%(date)s, %(amount)s, %(description)s, %(category)s, %(subcategory)s, %(raw_line)s, %(source_file)s)""",
        rows
    )
    cur.close()
Then in pipeline.py replace the insert loop with a single call:
python# build the list first
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

if rows_to_insert:
    insert_expenses_batch(conn, rows_to_insert)
    summary["inserted"] = len(rows_to_insert)
Same fix applies to insert_conflict if you ever have many conflicts at once — add an insert_conflicts_batch with the same pattern. The whole file becomes one network round trip instead of N."


[x] update conflict.py to use cursor instead of .execute directly
[]republish
[] push on git
[] fix add row feature
[x] fix line chart 