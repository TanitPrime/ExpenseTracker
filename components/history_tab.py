# components/history_tab.py
import os
from typing import cast
import dash
from dash import html, dcc, Input, Output, callback
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
from db.queries import get_conn, get_distinct_years, get_distinct_months

db_path_raw = os.getenv("DATABASE_URL")
if not db_path_raw:
    raise ValueError("DATABASE_URL not set in .env file")
DB_PATH: str = cast(str, db_path_raw)

MONTH_OPTIONS = [
    {"label": "January",   "value": "01"},
    {"label": "February",  "value": "02"},
    {"label": "March",     "value": "03"},
    {"label": "April",     "value": "04"},
    {"label": "May",       "value": "05"},
    {"label": "June",      "value": "06"},
    {"label": "July",      "value": "07"},
    {"label": "August",    "value": "08"},
    {"label": "September", "value": "09"},
    {"label": "October",   "value": "10"},
    {"label": "November",  "value": "11"},
    {"label": "December",  "value": "12"},
]

def layout():
    conn = get_conn(DB_PATH)
    years = get_distinct_years(conn)
    conn.close()

    return html.Div([
        html.H4("Expense History"),
        dbc.Row([
            dbc.Col(
                html.Div([
                    dbc.Label("Year", html_for="history-year"),
                    dcc.Dropdown(
                        id="history-year",
                        options=[{"label": y, "value": y} for y in years],
                        placeholder="All years",
                        clearable=True,
                    ),
                ], className="mb-3"),
                md=4,
            ),
            dbc.Col(
                html.Div([
                    dbc.Label("Month", html_for="history-month"),
                    dcc.Dropdown(
                        id="history-month",
                        options=MONTH_OPTIONS,
                        placeholder="All months",
                        clearable=True,
                    ),
                ], className="mb-3"),
                md=4,
            ),
        ], className="mb-4"),
        html.Div(id="history-grid-container"),
    ])

def _build_history_grid(expenses: list):
    column_defs = [
        {"field": "date",                "headerName": "Date",                "sortable": True, "filter": True},
        {"field": "amount",              "headerName": "Amount",              "sortable": True, "filter": True, "valueFormatter": {"function": "d3.format('.2f')(params.value)"}},
        {"field": "description",         "headerName": "Description",         "sortable": True, "filter": True, "flex": 1},
        {"field": "category",            "headerName": "Category",            "sortable": True, "filter": True},
        {"field": "subcategory",         "headerName": "Subcategory",         "sortable": True, "filter": True},
    ]

    get_row_style = {
        "styleConditions": [
            {
                "condition": "params.data.day_alternate === true",
                "style": {"backgroundColor": "#d9e7da"}
            }
        ]
    }

    return dag.AgGrid(
        id="history-grid",
        rowData=expenses,
        columnDefs=column_defs,
        defaultColDef={"resizable": True},
        dashGridOptions={
            "animateRows": True,
            "pagination": True,
            "paginationPageSize": 50,
        },
        getRowStyle=get_row_style,
        style={"height": "600px"},
    )

@callback(
    Output("history-grid-container", "children"),
    Input("history-tab-trigger", "data"),
    Input("history-year", "value"),
    Input("history-month", "value"),
)
def load_history(trigger, selected_year, selected_month):
    conn = get_conn(DB_PATH)
    
    # Build query with optional year/month filters
    query = "SELECT * FROM expenses"
    filters = []
    params = []
    
    if selected_year:
        filters.append("strftime('%Y', date) = ?")
        params.append(selected_year)
    if selected_month:
        filters.append("strftime('%m', date) = ?")
        params.append(selected_month)
    
    if filters:
        query += " WHERE " + " AND ".join(filters)
    
    query += " ORDER BY date DESC, id DESC"
    
    cursor = conn.cursor()
    cursor.execute(query, params)
    expenses = cursor.fetchall()
    conn.close()
    expenses_list = [dict(row) for row in expenses]

    # Add alternating by day
    current_date = None
    alternate = False
    for row in expenses_list:
        if row["date"] != current_date:
            current_date = row["date"]
            alternate = not alternate
        row["day_alternate"] = alternate

    return _build_history_grid(expenses_list)