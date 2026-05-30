from collections import Counter
import statistics
from datetime import date, datetime, timedelta
from typing import cast
from dash import html, dcc, Input, Output, callback
import dash_bootstrap_components as dbc
from plotly import graph_objects as go
from wordcloud import WordCloud
import io
import base64
import os
from db.queries import get_conn, get_distinct_years, get_distinct_months, get_expense_stats_rows

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
        html.H4("Dashboard"),
        dbc.Row([
            dbc.Col(
                html.Div([
                    dbc.Label("Year", html_for="dashboard-year"),
                    dcc.Dropdown(
                        id="dashboard-year",
                        options=[{"label": y, "value": y} for y in years],
                        placeholder="All years",
                        clearable=True,
                    ),
                ], className="mb-3"),
                md=4,
            ),
            dbc.Col(
                html.Div([
                    dbc.Label("Month", html_for="dashboard-month"),
                    dcc.Dropdown(
                        id="dashboard-month",
                        options=MONTH_OPTIONS,
                        placeholder="All months",
                        clearable=True,
                    ),
                ], className="mb-3"),
                md=4,
            ),
        ], className="mb-4"),

        dbc.Row(id="dashboard-chart-row", className="mt-4"),
        dbc.Row(id="dashboard-stats-cards"),
        dbc.Row(id="dashboard-wordcloud-row", className="mt-4"),
    ])


def _stat_card(title: str, value, color: str = "light"):
    if isinstance(value, list):
        content = html.Div([html.P(item, className="mb-1") for item in value])
    else:
        content = html.H4(value, className="card-text")

    return dbc.Col(
        dbc.Card([
            dbc.CardBody([
                html.H6(title, className="card-title text-muted"),
                content,
            ])
        ], color=color, inverse=(color != "light")),
        md=4,
    )


def _format_amount(value):
    return f"{value:,.2f}" if value is not None else "—"


def _format_expense_row(row):
    amount = _format_amount(row["amount"])
    description = row.get("description", "")
    date = row.get("date", "")
    return f"{date} • {amount} • {description}"


def _safe_mode(values):
    if not values:
        return "—"
    counts = Counter(values)
    most_common = counts.most_common()
    if not most_common:
        return "—"
    mode_value, count = most_common[0]
    return f"{mode_value} ({count})"


def _to_label_list(values):
    return ", ".join(str(v) for v in values) if values else "—"


@callback(
    Output("dashboard-stats-cards", "children"),
    Input("dashboard-year", "value"),
    Input("dashboard-month", "value"),
)
def render_dashboard_stats(selected_year, selected_month):
    conn = get_conn(DB_PATH)
    rows = [dict(row) for row in get_expense_stats_rows(conn, year=selected_year, month=selected_month)]
    conn.close()

    amounts = [row["amount"] for row in rows]
    descriptions = [row["description"] for row in rows]

    if not amounts:
        return [
            dbc.Col(dbc.Alert("No expense records found for the selected filter.", color="warning"), md=12)
        ]

    total = sum(amounts)
    count = len(amounts)
    average = statistics.mean(amounts)
    minimum = min(amounts)
    maximum = max(amounts)
    std_dev = statistics.pstdev(amounts) if count > 0 else 0.0
    amount_mode = _safe_mode(amounts)
    
    # Get top 3 most common descriptions
    description_counts = Counter(descriptions)
    top_descriptions = [f"{desc} ({count})" for desc, count in description_counts.most_common(3)]
    
    bottom_3_rows = sorted(rows, key=lambda r: r["amount"])[:3]
    top_3_rows = sorted(rows, key=lambda r: r["amount"], reverse=True)[:3]

    quantitative_cards = [
        _stat_card("Sum", _format_amount(total)),
        _stat_card("Count", str(count)),
        _stat_card("Average", _format_amount(average)),
        _stat_card("Min", _format_amount(minimum)),
        _stat_card("Max", _format_amount(maximum)),
        _stat_card("Std Dev", _format_amount(std_dev)),
        _stat_card("Amount Mode", amount_mode),
    ]

    expense_cards = [
        _stat_card(
            "Top 3 Most Common Expenses",
            top_descriptions,
            color="info",
        ),
        _stat_card(
            "Bottom 3 by Amount",
            [_format_expense_row(row) for row in bottom_3_rows],
            color="secondary",
        ),
        _stat_card(
            "Top 3 by Amount",
            [_format_expense_row(row) for row in top_3_rows],
            color="secondary",
        ),
    ]

    result = [
        dbc.Row([
            dbc.Col(html.H5("Quantitative Stats", className="text-muted"), md=12)
        ], className="mb-3 mt-3"),
        dbc.Row(quantitative_cards),
        dbc.Row([
            dbc.Col(html.H5("Expense Analysis", className="text-muted"), md=12)
        ], className="mb-3 mt-4"),
        dbc.Row(expense_cards),
    ]

    return result

def _to_date_str(d) -> str:
    return d.isoformat() if isinstance(d, (date, datetime)) else str(d)

def _build_expense_trend_chart(rows, include_empty_days):
    """Build a line chart of cumulative expenses over time with daily amounts in hover."""
    if not rows:
        return dcc.Graph(
            figure=go.Figure().add_annotation(text="No data available")
        )

    # Sort rows by date
    sorted_rows = sorted(rows, key=lambda r: _to_date_str(r["date"]))
    
    if include_empty_days:
        # Generate all days in the range and fill in missing days with 0
        dates = [_to_date_str(r["date"]) for r in sorted_rows]
        min_date = datetime.fromisoformat(min(dates))
        max_date = datetime.fromisoformat(max(dates))
        
        # Create a dict of date -> amount for quick lookup
        amount_by_date = {}
        for row in sorted_rows:
            date_str = _to_date_str(row["date"])
            amount_by_date[date_str] = amount_by_date.get(date_str, 0) + row["amount"]
        
        # Generate all dates in range
        current_date = min_date
        all_dates = []
        all_amounts = []
        all_daily_amounts = []
        cumulative = 0
        
        while current_date <= max_date:
            date_str = current_date.strftime("%Y-%m-%d")
            all_dates.append(date_str)
            daily_amount = amount_by_date.get(date_str, 0)
            cumulative += daily_amount
            all_amounts.append(cumulative)
            all_daily_amounts.append(daily_amount)
            current_date += timedelta(days=1)
    else:
        # Only plot days with expenses
        all_dates = [r["date"] for r in sorted_rows]
        cumulative = 0
        all_amounts = []
        all_daily_amounts = []
        
        for row in sorted_rows:
            daily_amount = row["amount"]
            cumulative += daily_amount
            all_amounts.append(cumulative)
            all_daily_amounts.append(daily_amount)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=all_dates,
        y=all_amounts,
        mode='lines+markers',
        name='Cumulative Expenses',
        line=dict(color='#1f77b4', width=2),
        marker=dict(size=6),
        customdata=all_daily_amounts,
        hovertemplate='<b>%{x}</b><br>Daily Total: %{customdata:.2f}TND<br>Cumulative: %{y:.2f}TND<extra></extra>',
    ))
    
    fig.update_layout(
        title="Expense Trend Over Time",
        xaxis_title="Date",
        yaxis_title="Cumulative Amount",
        hovermode='x unified',
        template='plotly_white',
        height=400,
    )
    
    return dcc.Graph(figure=fig)


def _build_wordcloud_image(descriptions):
    """Generate a wordcloud from expense descriptions."""
    if not descriptions or not any(descriptions):
        return html.Div("No descriptions available for wordcloud")
    
    # Join all descriptions and generate wordcloud
    text = " ".join(descriptions)
    wordcloud = WordCloud(width=300, height=200, background_color='white').generate(text)
    
    # Convert to base64
    buf = io.BytesIO()
    wordcloud.to_image().save(buf, format='png')
    buf.seek(0)
    image_b64 = base64.b64encode(buf.read()).decode()
    
    return html.Div([
        html.Img(src=f"data:image/png;base64,{image_b64}", style={"width": "100%", "height": "auto"})
    ])


@callback(
    Output("dashboard-chart-row", "children"),
    Input("dashboard-year", "value"),
    Input("dashboard-month", "value"),
)
def render_chart(selected_year, selected_month):
    conn = get_conn(DB_PATH)
    rows = [dict(row) for row in get_expense_stats_rows(conn, year=selected_year, month=selected_month)]
    conn.close()

    if not rows:
        return [dbc.Col(dbc.Alert("No expense records found.", color="warning"), md=12)]

    chart = _build_expense_trend_chart(rows, include_empty_days=True)
    
    return [
        dbc.Row([
            dbc.Col(html.H5("Expense Trend", className="text-muted"), md=12)
        ], className="mb-3"),
        dbc.Row([
            dbc.Col(chart, md=12)
        ]),
    ]


@callback(
    Output("dashboard-wordcloud-row", "children"),
    Input("dashboard-year", "value"),
    Input("dashboard-month", "value"),
)
def render_wordcloud(selected_year, selected_month):
    conn = get_conn(DB_PATH)
    rows = [dict(row) for row in get_expense_stats_rows(conn, year=selected_year, month=selected_month)]
    conn.close()

    if not rows:
        return [dbc.Col(dbc.Alert("No expense records found.", color="warning"), md=12)]

    descriptions = [row["description"] for row in rows]
    wordcloud_div = _build_wordcloud_image(descriptions)
    
    return [
        dbc.Row([
            dbc.Col(html.H5("Expense Description Cloud", className="text-muted"), md=12)
        ], className="mb-3"),
        dbc.Row([
            dbc.Col(wordcloud_div, md=6)
        ], justify="center"),
    ]