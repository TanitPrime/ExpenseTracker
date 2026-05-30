# components/history_tab.py
import dash
from dash import html, dcc, Input, Output, callback
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import pandas as pd
from typing import cast
from datetime import datetime

"""History now consumes the `all-expenses` store (localStorage) instead of
querying the DB on every view. Filtering and sorting are done with Pandas."""

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
    return html.Div([
        html.H4("Expense History"),
        dcc.Store(id="history-years-data"),  # Store year mapping
        dbc.Row([
            dbc.Col(
                html.Div([
                    dbc.Label("Year", html_for="history-year-slider"),
                    dcc.Slider(
                        id="history-year-slider",
                        min=0,
                        max=3,
                        step=1,
                        marks={},
                        value=0,
                        tooltip={"placement": "bottom"}
                    ),
                ], className="mb-3"),
                md=8,
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

    return dag.AgGrid(
        id="history-grid",
        rowData=expenses,
        columnDefs=column_defs,
        defaultColDef={"resizable": True},
        dashGridOptions={
            "animateRows": True,
            "pagination": True,
            "paginationPageSize": 50,
            "rowStyle": {"function": "if (params.data.day_alternate) { return { backgroundColor: '#f5f5f5' }; } return {};"}
        },
        style={"height": "600px"},
    )

@callback(
    Output("history-grid-container", "children"),
    Input("all-expenses", "data"),
    Input("history-tab-trigger", "data"),
    Input("history-year-slider", "value"),
    Input("history-month", "value"),
    Input("history-years-data", "data"),
)
def load_history(all_expenses, trigger, selected_position, selected_month, years_list):
    if not all_expenses:
        return dbc.Alert("No expense records available.", color="warning")
    df = pd.DataFrame(all_expenses)
    if df.empty:
        return dbc.Alert("No expense records available.", color="warning")

    df["date"] = pd.to_datetime(df["date"])  # type: ignore[arg-type]

    # selected_position: 0="All", 1-N map to years_list indices
    if selected_position and selected_position > 0 and years_list:
        year_index = selected_position - 1
        if year_index < len(years_list):
            df = df[df["date"].dt.year == int(years_list[year_index])]
    if selected_month:
        df = df[df["date"].dt.month == int(selected_month)]

    df = df.sort_values(by=["date", "id"], ascending=[False, False])
    expenses_list = cast(list, df.to_dict("records"))
    for r in expenses_list:
        r["date"] = r["date"].date() if hasattr(r["date"], "date") else r["date"]

    # Add alternating by day
    current_date = None
    alternate = False
    for row in expenses_list:
        if row["date"] != current_date:
            current_date = row["date"]
            alternate = not alternate
        row["day_alternate"] = alternate

    return _build_history_grid(expenses_list)


@callback(
    Output("history-year-slider", "min"),
    Output("history-year-slider", "max"),
    Output("history-year-slider", "marks"),
    Output("history-year-slider", "value"),
    Output("history-years-data", "data"),
    Input("all-expenses", "data"),
)
def populate_history_years(all_expenses):
    if not all_expenses:
        return 0, 1, {0: "All"}, 0, []
    df = pd.DataFrame(all_expenses)
    if df.empty:
        return 0, 1, {0: "All"}, 0, []
    df["date"] = pd.to_datetime(df["date"])  # type: ignore[arg-type]
    years = sorted(df["date"].dt.year.unique().tolist())
    if not years:
        return 0, 1, {0: "All"}, 0, []
    # Build marks: position 0 is "All", positions 1-N are the years
    marks = {0: "All"}
    for i, year in enumerate(years):
        marks[i + 1] = str(year)
    max_pos = len(years)  # 0 (All) + N years = positions 0 to N
    return 0, max_pos, marks, 0, years