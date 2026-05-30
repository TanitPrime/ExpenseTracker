# app.py
import os
from dotenv import load_dotenv

load_dotenv()

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
from typing import cast
from db.init_db import init_db
from components import ingestion_tab, conflict_tab, autofill_tab, dashboard, history_tab

DATABASE_URL_raw = os.getenv("DATABASE_URL")
if not DATABASE_URL_raw:
    raise ValueError("DATABASE_URL not set in .env file")
DATABASE_URL: str = cast(str, DATABASE_URL_raw)
init_db(DATABASE_URL)
os.makedirs("raw", exist_ok=True)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)

app.layout = dbc.Container([
    dcc.Store(id="admin-authorized", data=False),
    dcc.Store(id="conflict-tab-trigger"),
    dcc.Store(id="history-tab-trigger"),
    dbc.Tabs(id="tabs", active_tab="tab-history", children=[
        dbc.Tab(label="History",   tab_id="tab-history"),
        dbc.Tab(label="Dashboard", tab_id="tab-dashboard"),
        dbc.Tab(label="Ingestion", tab_id="tab-ingestion"),
        dbc.Tab(label="Conflicts", tab_id="tab-conflicts"),
        dbc.Tab(label="Autofill",  tab_id="tab-autofill"),
    ]),
    html.Div(id="tab-content", className="mt-4")
], fluid=True)

from components import dashboard, ingestion_tab, conflict_tab, autofill_tab, history_tab  # noqa

def _admin_gate_layout(tab_label: str):
    return html.Div([
        html.H4(f"{tab_label} — Admin access required"),
        dbc.Alert(
            "This section is restricted. Enter the admin password to continue.",
            color="warning"
        ),
        dbc.Row([
            dbc.Col(
                dcc.Input(
                    id="admin-password-input",
                    type="password",
                    placeholder="Admin password",
                    style={"width": "100%"}
                ),
                width=6
            ),
            dbc.Col(
                dbc.Button("Unlock", id="btn-admin-unlock", color="primary"),
                width="auto"
            ),
        ], className="g-2"),
        html.Div(id="admin-login-feedback", className="mt-3"),
    ])

@app.callback(
    Output("admin-authorized", "data"),
    Output("admin-login-feedback", "children"),
    Input("btn-admin-unlock", "n_clicks"),
    State("admin-password-input", "value"),
    prevent_initial_call=True
)
def unlock_admin(n_clicks, password):
    if password and ADMIN_TOKEN and password == ADMIN_TOKEN:
        return True, dbc.Alert("✅ Access granted.", color="success", duration=4000)
    return False, dbc.Alert("❌ Invalid password.", color="danger", duration=4000)

@app.callback(
    Output("tab-content",           "children"),
    Output("conflict-tab-trigger",  "data"),
    Output("history-tab-trigger",   "data"),
    Input("tabs",                   "active_tab"),
    Input("admin-authorized",       "data")
)
def render_tab(active_tab, admin_authorized):
    conflict_trigger = active_tab == "tab-conflicts"
    history_trigger = active_tab == "tab-history"

    restricted_tabs = {
        "tab-ingestion": "Ingestion",
        "tab-conflicts": "Conflicts",
        "tab-autofill":  "Autofill",
    }

    if active_tab in restricted_tabs and not admin_authorized:
        return _admin_gate_layout(restricted_tabs[active_tab]), False, False

    if active_tab == "tab-dashboard":
        return dashboard.layout(), conflict_trigger, history_trigger
    if active_tab == "tab-history":
        return history_tab.layout(), conflict_trigger, history_trigger
    if active_tab == "tab-ingestion":
        return ingestion_tab.layout(), conflict_trigger, history_trigger
    if active_tab == "tab-conflicts":
        return conflict_tab.layout(), conflict_trigger, history_trigger
    if active_tab == "tab-autofill":
        return autofill_tab.layout(), conflict_trigger, history_trigger
    return html.Div("Unknown tab"), conflict_trigger, history_trigger

if __name__ == "__main__":
    app.run(debug=True)