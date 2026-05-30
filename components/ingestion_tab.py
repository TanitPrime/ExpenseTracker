# components/ingestion_tab.py
import os
import base64
from typing import cast
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from ingestion.pipeline import ingest_file
from db.init_db import reset_db
from db.queries import get_conn, get_conflict_count
import traceback

db_path_raw = os.getenv("DATABASE_URL")
if not db_path_raw:
    raise ValueError("DATABASE_URL not set in .env file")
DB_PATH: str = cast(str, db_path_raw)

def layout():
    return html.Div([
        html.H4("Ingestion"),
        html.P("Upload .txt or .csv expense files. Files are parsed in-memory and stored directly to Supabase."),
        dcc.Upload(
            id="upload-file",
            children=html.Div([
                html.Strong("Drag and drop"), html.Span(" or "), html.Strong("click to select")
            ]),
            style={
                "width": "100%",
                "height": "80px",
                "lineHeight": "80px",
                "borderWidth": "2px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center",
                "margin": "20px 0",
                "backgroundColor": "#f8f9fa",
                "cursor": "pointer"
            },
            multiple=False,
            accept=".txt,.csv"
        ),
        dbc.Button("Reset database", id="btn-reset-db", color="danger", className="mt-3"),
        html.Div(id="ingest-output", className="mt-4"),
    ])

@callback(
    Output("ingest-output", "children"),
    Input("upload-file", "contents"),
    State("upload-file", "filename"),
    State("admin-authorized", "data"),
    prevent_initial_call=True
)
def upload_and_ingest(contents, filename, admin_authorized):
    if not admin_authorized:
        return dbc.Alert("❌ Unauthorized. Please unlock admin access first.", color="danger", duration=4000)
    
    if contents is None or filename is None:
        return dash.no_update

    # Decode the base64 content
    try:
        content_type, content_string = contents.split(',')
        decoded_bytes = base64.b64decode(content_string)
        
        # Ingest from memory
        summary = ingest_file(DB_PATH, decoded_bytes, filename)
    except Exception as e:
        return dbc.Alert(f"❌ Error processing file: {traceback.format_exc()}", color="danger")

    # Build result display
    if summary["status"] == "stale":
        result_msg = f"⏭️ {filename} — stale, skipped (newer data already in database)"
        color = "info"
    elif summary["status"] == "empty":
        result_msg = f"⚠️ {filename} — empty or unreadable"
        color = "warning"
    elif summary["status"] == "ok":
        result_msg = (
            f"✅ {filename} — {summary['inserted']} inserted, "
            f"{summary['conflicts_new']} new conflicts, "
            f"{summary['conflicts_remembered']} already known"
        )
        color = "success"
    else:
        result_msg = f"❓ {filename} — unknown status"
        color = "warning"

    # Get conflict badge
    conn = get_conn(DB_PATH)
    conflict_count = get_conflict_count(conn)
    conn.close()

    badge = dbc.Alert(
        f"⚠️ {conflict_count} row(s) pending conflict resolution — see Conflicts tab.",
        color="warning"
    ) if conflict_count > 0 else dbc.Alert("✅ No pending conflicts.", color="success")

    return html.Div([
        dbc.Alert(result_msg, color=color),
        badge,
    ])

@callback(
    Output("ingest-output", "children", allow_duplicate=True),
    Input("btn-reset-db", "n_clicks"),
    State("admin-authorized", "data"),
    prevent_initial_call=True
)
def reset_database(n_clicks, admin_authorized):
    if not admin_authorized:
        return dbc.Alert("❌ Unauthorized. Please unlock admin access first.", color="danger", duration=4000)
    
    try:
        reset_db(DB_PATH)
        return dbc.Alert(
            "🧨 Database has been reset. All expenses and conflicts were cleared.",
            color="info"
        )
    except Exception as e:
        return dbc.Alert(f"❌ Error resetting database: {str(e)}", color="danger")

    conn = get_conn(DB_PATH)
    conflict_count = get_conflict_count(conn)
    conn.close()

    badge = dbc.Alert(
        f"✅ Database reset. No pending conflicts.",
        color="success"
    )
    summary_ui = html.P("🧨 Database has been reset. All expenses and conflicts were cleared.")
    return summary_ui, badge