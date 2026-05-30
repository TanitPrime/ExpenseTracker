# components/autofill_tab.py
from dash import html
import dash_bootstrap_components as dbc

def layout():
    return html.Div([
        html.H4("Autofill"),
        dbc.Alert(
            "Category autofill — phase 2. "
            "Will surface unconfirmed rows and apply fuzzy matching in batches.",
            color="info"
        )
    ])