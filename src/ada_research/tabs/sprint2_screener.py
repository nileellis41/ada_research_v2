"""Sprint 2: Stock Screener (Dash/Plotly UI).

Preset-driven screens. Pick a preset, set a limit, hit Run.

Requires FMP_API_KEY.
"""
from __future__ import annotations

import dash
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import btn, placeholder_panel, section_header, status_label
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 2 — Stock Screener",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart the server.",
            ),
            className="tab-content",
        )

    from ada_research.core.fmp_client import SCREEN_PRESETS

    preset_options = [
        {"label": f"{name} — {desc}", "value": name}
        for name, (_, desc) in SCREEN_PRESETS.items()
    ]

    ts = TABLE_STYLES()

    return html.Div([
        section_header("Sprint 2 — Stock Screener"),

        # ── Toolbar ──────────────────────────────────────────────────────
        html.Div([
            html.Label("Preset:", style={"color": COLORS["text_dim"],
                                          "fontSize": "12px", "whiteSpace": "nowrap"}),
            dcc.Dropdown(
                id="sp2-preset",
                options=preset_options,
                value=preset_options[0]["value"] if preset_options else None,
                clearable=False,
                style={
                    "minWidth": "300px",
                    "backgroundColor": COLORS["panel"],
                    "color": COLORS["text"],
                    "border": f"1px solid {COLORS['border']}",
                    "borderRadius": "4px",
                    "fontSize": "13px",
                },
            ),
            html.Label("Limit:", style={"color": COLORS["text_dim"],
                                         "fontSize": "12px", "whiteSpace": "nowrap"}),
            dcc.Input(
                id="sp2-limit",
                type="number",
                value=30,
                min=5,
                max=200,
                step=5,
                className="ada-input",
                style={"width": "70px"},
            ),
            btn("Run Screen", "sp2-run-btn", primary=True),
        ], className="toolbar-row"),

        # ── Results table ─────────────────────────────────────────────────
        dcc.Loading(
            type="circle", color=COLORS["accent"],
            children=dash_table.DataTable(
                id="sp2-table",
                columns=[
                    {"name": "Symbol",     "id": "symbol"},
                    {"name": "Name",       "id": "name"},
                    {"name": "Sector",     "id": "sector"},
                    {"name": "Market Cap", "id": "market_cap"},
                    {"name": "Price",      "id": "price"},
                    {"name": "Beta",       "id": "beta"},
                ],
                data=[],
                page_size=30,
                sort_action="native",
                **ts,
            ),
        ),

        status_label("sp2-status"),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    @app.callback(
        Output("sp2-table",  "data"),
        Output("sp2-status", "children"),
        Input("sp2-run-btn", "n_clicks"),
        State("sp2-preset",  "value"),
        State("sp2-limit",   "value"),
        prevent_initial_call=True,
    )
    def run_screen(n_clicks, preset_name, limit):
        import pandas as pd
        from ada_research.core.fmp_client import FmpClient, SCREEN_PRESETS

        if not preset_name:
            raise PreventUpdate

        limit = int(limit or 30)
        fn, _ = SCREEN_PRESETS[preset_name]

        try:
            client = FmpClient()
            df = fn(client, limit=limit)
        except Exception as exc:
            log.exception("Screener failed")
            return [], f"Error: {exc}"

        if df.empty:
            return [], "No matches."

        rows = []
        for _, r in df.reset_index(drop=True).iterrows():
            mcap = r.get("marketCap")
            beta = r.get("beta")
            price = r.get("price")
            rows.append({
                "symbol":     str(r.get("symbol", "")),
                "name":       str(r.get("companyName", "")),
                "sector":     str(r.get("sector", "")),
                "market_cap": _fmt_marketcap(mcap),
                "price":      f"${float(price):,.2f}" if price else "—",
                "beta":       f"{float(beta):.2f}" if beta is not None and pd.notna(beta) else "—",
            })

        return rows, f"{len(rows)} matches."


# ── Dropdown dark styling via dcc_dropdown_style ──────────────────────────
# Plotly Dash doesn't support full dropdown CSS via inline styles;
# additional overrides are in assets/style.css.


def _fmt_marketcap(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
        if v != v:
            return "—"
    except (TypeError, ValueError):
        return "—"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"
