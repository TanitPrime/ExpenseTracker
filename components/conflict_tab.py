# components/conflict_tab.py
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from typing import cast
import os
from ingestion.conflict import get_conflict_queue, get_context_rows, resolve_conflict
from db.queries import get_all_expenses
from db.init_db import get_conn

db_path_raw = os.getenv("DATABASE_URL")
if not db_path_raw:
    raise ValueError("DATABASE_URL not set in .env file")
DB_PATH: str = cast(str, db_path_raw)

def layout():
    return html.Div([
        dcc.Store(id="conflict-queue"),       # full list of pending conflicts
        dcc.Store(id="conflict-index", data=0),  # which conflict we're on
        dcc.Store(id="grid-original"),        # snapshot of grid when opened

        html.Div(id="conflict-header", className="mb-3"),
        html.Div(id="conflict-grid-container"),

        dbc.Row([
            dbc.Col(dbc.Button("Add row", id="btn-add-row", color="secondary"), width="auto"),
            dbc.Col(dbc.Button("Delete selected", id="btn-delete-selected", color="danger"), width="auto"),
        ], className="mb-3 gap-2"),

        dbc.Row([
            dbc.Col(dbc.Button("Confirm", id="btn-confirm", color="success"), width="auto"),
            dbc.Col(dbc.Button("Skip",    id="btn-skip",    color="secondary"), width="auto"),
            dbc.Col(dbc.Button("Refresh", id="btn-refresh", color="warning"), width="auto"),
        ], className="mt-3 gap-2"),

        html.Div(id="conflict-feedback", className="mt-2"),
    ])


def _build_grid(context_rows: list):
    column_defs = [
        {"field": "id",          "headerName": "ID",          "editable": False, "width": 70},
        {"field": "date",        "headerName": "Date",        "editable": True},
        {"field": "amount",      "headerName": "Amount",      "editable": True},
        {"field": "description", "headerName": "Description", "editable": True, "flex": 1},
    ]

    # avoid typed getRowStyle to keep linter happy
    row_style_conditions = None

    return dag.AgGrid(
        id="conflict-grid",
        rowData=context_rows,
        columnDefs=column_defs,
        defaultColDef={"resizable": True, "sortable": False},
        dashGridOptions={
            "rowSelection": "multiple",
            "animateRows": True,
            "suppressRowClickSelection": False,
        },
        getRowStyle=row_style_conditions,
        style={"height": "450px"},
    )


# --- load queue on tab open or refresh ---
@callback(
    Output("conflict-queue",  "data"),
    Output("conflict-index",  "data"),
    Input("btn-refresh",      "n_clicks"),
    Input("conflict-tab-trigger", "data"),   # fired when tab becomes active
    prevent_initial_call=False
)
def load_queue(refresh_clicks, tab_trigger):
    queue = get_conflict_queue(DB_PATH)
    return queue, 0


# --- render current conflict ---
@callback(
    Output("conflict-header",         "children"),
    Output("conflict-grid-container", "children"),
    Output("grid-original",           "data"),
    Input("conflict-queue",  "data"),
    Input("conflict-index",  "data"),
)
def render_conflict(queue, index):
    if not queue:
        return dbc.Alert("✅ No pending conflicts.", color="success"), html.Div(), []

    total    = len(queue)
    conflict = queue[index]
    conflict_date = conflict.get("context_date") or conflict.get("created_at", "")[:10]

    context_rows = get_context_rows(DB_PATH, conflict)
    initial_rows = context_rows

    header = dbc.Alert(
        [
            html.Strong(f"Conflict {index + 1} of {total}  "),
            html.Span(f"{conflict['issue']}  "),
            html.Code(conflict['raw_line']),
        ],
        color="warning"
    )

    grid = _build_grid(initial_rows)
    return header, grid, initial_rows


# --- confirm ---
@callback(
    Output("conflict-queue",    "data",  allow_duplicate=True),
    Output("conflict-index",    "data",  allow_duplicate=True),
    Output("conflict-feedback", "children"),
    Output("all-expenses", "data", allow_duplicate=True),
    Input("btn-confirm",        "n_clicks"),
    State("conflict-queue",     "data"),
    State("conflict-index",     "data"),
    State("conflict-grid",      "rowData"),
    State("grid-original",      "data"),
    State("admin-authorized",   "data"),
    prevent_initial_call=True
)
def confirm_resolution(n_clicks, queue, index, grid_current, grid_original, admin_authorized):
    if not admin_authorized:
        return queue, index, dbc.Alert("Unauthorized. Please unlock admin access first.", color="danger", duration=4000), dash.no_update
    if not queue:
        return queue, index, dash.no_update, dash.no_update

    conflict = queue[index]
    resolve_conflict(DB_PATH, conflict["content_hash"], grid_original, grid_current)

    # reprocess queue — remove resolved conflict
    new_queue = get_conflict_queue(DB_PATH)
    new_index = min(index, len(new_queue) - 1) if new_queue else 0

    feedback = dbc.Alert("✅ Conflict resolved.", color="success", duration=3000)
    # refresh all-expenses store
    conn = get_conn(DB_PATH)
    all_rows = [dict(r) for r in get_all_expenses(conn)]
    conn.close()

    return new_queue, new_index, feedback, all_rows


# --- add new blank row ---
@callback(
    Output("conflict-grid-container", "children", allow_duplicate=True),
    Input("btn-add-row", "n_clicks"),
    State("conflict-grid", "rowData"),
    State("conflict-queue", "data"),
    State("conflict-index", "data"),
    prevent_initial_call=True
)
def add_row(n_clicks, current_rows, queue, index):
    if current_rows is None or not queue:
        return dash.no_update

    conflict = queue[index]
    conflict_date = conflict.get("context_date") or conflict.get("created_at", "")[:10]
    new_rows = current_rows + [{"id": None, "date": conflict_date, "amount": "", "description": "", "is_conflict": False}]
    return _build_grid(new_rows)


# --- delete selected rows ---
@callback(
    Output("conflict-grid-container", "children", allow_duplicate=True),
    Input("btn-delete-selected", "n_clicks"),
    State("conflict-grid", "rowData"),
    State("conflict-grid", "selectedRows"),
    State("conflict-queue", "data"),
    State("conflict-index", "data"),
    prevent_initial_call=True
)
def delete_selected_rows(n_clicks, current_rows, selected_rows, queue, index):
    if current_rows is None or not selected_rows or not queue:
        return dash.no_update

    selected_set = {(
        row.get("id"),
        str(row.get("date")),
        str(row.get("amount")),
        str(row.get("description"))
    ) for row in selected_rows}

    remaining = [row for row in current_rows if (
        row.get("id"),
        str(row.get("date")),
        str(row.get("amount")),
        str(row.get("description"))
    ) not in selected_set]

    conflict = queue[index]
    conflict_date = conflict.get("context_date") or conflict.get("created_at", "")[:10]
    return _build_grid(remaining)


# --- skip ---
@callback(
    Output("conflict-index", "data", allow_duplicate=True),
    Input("btn-skip",        "n_clicks"),
    State("conflict-queue",  "data"),
    State("conflict-index",  "data"),
    prevent_initial_call=True
)
def skip_conflict(n_clicks, queue, index):
    if not queue:
        return 0
    return (index + 1) % len(queue)