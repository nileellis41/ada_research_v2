"""Sprint 2: Sectors, Industries & Movers (Dash/Plotly UI).

Sub-tabs: Sector Snapshot, Industry Snapshot, Sector PE, Industry PE, Movers.
Adds horizontal bar charts for sector and industry performance.

Requires FMP_API_KEY. Auto-loads on page open.
"""
from __future__ import annotations

import dash
import plotly.graph_objects as go
from dash import Input, Output, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import btn, placeholder_panel, section_header, status_label
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


def _bar_chart(names: list, values: list, title: str, color_by_sign: bool = True) -> go.Figure:
    colors = []
    if color_by_sign:
        colors = [COLORS["good"] if v >= 0 else COLORS["bad"] for v in values]
    else:
        colors = [COLORS["accent"]] * len(values)

    fig = go.Figure(go.Bar(
        x=values,
        y=names,
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" if color_by_sign else f"{v:.2f}" for v in values],
        textposition="outside",
        textfont={"color": COLORS["text"], "size": 11},
    ))
    fig.update_layout(
        title={"text": title, "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 160, "r": 60, "t": 36, "b": 20},
        xaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"],
               "zeroline": True, "zerolinecolor": COLORS["border"]},
        yaxis={"gridcolor": "transparent"},
        height=max(280, len(names) * 28 + 60),
    )
    return fig


def _ts():
    return TABLE_STYLES()


def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 2 — Sectors & Movers",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart the server.",
            ),
            className="tab-content",
        )

    ts = _ts()
    base_sdc = ts.pop("style_data_conditional", [])  # extract so we can extend per-table
    mover_cols = [
        {"name": "Symbol",   "id": "symbol"},
        {"name": "Name",     "id": "name"},
        {"name": "Price",    "id": "price"},
        {"name": "% Change", "id": "change"},
    ]

    return html.Div([
        dcc.Interval(id="sp2-init", interval=400, max_intervals=1),

        section_header("Sprint 2 — Sectors & Movers"),

        html.Div([
            btn("Refresh All", "sp2-refresh-btn", primary=True),
            status_label("sp2-status"),
        ], className="toolbar-row"),

        dcc.Tabs(
            id="sp2-tabs",
            value="sector-perf",
            className="sub-tabs",
            children=[

                # ── Sector Performance ────────────────────────────────────
                dcc.Tab(
                    label="Sector Performance", value="sector-perf",
                    className="sub-tab", selected_className="sub-tab--selected",
                    children=[
                        dcc.Loading(type="circle", color=COLORS["accent"],
                                    children=dcc.Graph(id="sp2-sector-chart", config={"displayModeBar": False})),
                        dash_table.DataTable(id="sp2-sector-table", columns=[
                            {"name": "Sector", "id": "sector"},
                            {"name": "Avg Change", "id": "averageChange"},
                        ], data=[], **ts,
                        style_data_conditional=[
                            *base_sdc,
                            {"if": {"filter_query": "{averageChange} > 0", "column_id": "averageChange"}, "color": COLORS["good"]},
                            {"if": {"filter_query": "{averageChange} < 0", "column_id": "averageChange"}, "color": COLORS["bad"]},
                        ]),
                    ],
                ),

                # ── Industry Performance ──────────────────────────────────
                dcc.Tab(
                    label="Industry Performance", value="industry-perf",
                    className="sub-tab", selected_className="sub-tab--selected",
                    children=[
                        dcc.Loading(type="circle", color=COLORS["accent"],
                                    children=dcc.Graph(id="sp2-industry-chart", config={"displayModeBar": False})),
                        dash_table.DataTable(id="sp2-industry-table", columns=[
                            {"name": "Industry", "id": "industry"},
                            {"name": "Avg Change", "id": "averageChange"},
                        ], data=[], page_size=20, **ts,
                        style_data_conditional=[
                            *base_sdc,
                            {"if": {"filter_query": "{averageChange} > 0", "column_id": "averageChange"}, "color": COLORS["good"]},
                            {"if": {"filter_query": "{averageChange} < 0", "column_id": "averageChange"}, "color": COLORS["bad"]},
                        ]),
                    ],
                ),

                # ── Sector P/E ────────────────────────────────────────────
                dcc.Tab(
                    label="Sector P/E", value="sector-pe",
                    className="sub-tab", selected_className="sub-tab--selected",
                    children=dash_table.DataTable(
                        id="sp2-sector-pe-table",
                        columns=[{"name": "Sector", "id": "sector"}, {"name": "P/E", "id": "pe"}],
                        data=[], **ts, style_data_conditional=base_sdc,
                    ),
                ),

                # ── Industry P/E ──────────────────────────────────────────
                dcc.Tab(
                    label="Industry P/E", value="industry-pe",
                    className="sub-tab", selected_className="sub-tab--selected",
                    children=dash_table.DataTable(
                        id="sp2-industry-pe-table",
                        columns=[{"name": "Industry", "id": "industry"}, {"name": "P/E", "id": "pe"}],
                        data=[], page_size=20, **ts, style_data_conditional=base_sdc,
                    ),
                ),

                # ── Movers ────────────────────────────────────────────────
                dcc.Tab(
                    label="Movers", value="movers",
                    className="sub-tab", selected_className="sub-tab--selected",
                    children=html.Div([
                        html.Div([
                            html.Div([
                                html.Div("Gainers", className="subsection-title"),
                                dash_table.DataTable(id="sp2-gainers", columns=mover_cols, data=[], **ts,
                                    style_data_conditional=[
                                        *base_sdc,
                                        {"if": {"column_id": "change"}, "color": COLORS["good"]},
                                    ]),
                            ], style={"flex": "1"}),
                            html.Div([
                                html.Div("Losers", className="subsection-title"),
                                dash_table.DataTable(id="sp2-losers", columns=mover_cols, data=[], **ts,
                                    style_data_conditional=[
                                        *base_sdc,
                                        {"if": {"column_id": "change"}, "color": COLORS["bad"]},
                                    ]),
                            ], style={"flex": "1"}),
                            html.Div([
                                html.Div("Most Active", className="subsection-title"),
                                dash_table.DataTable(id="sp2-actives", columns=mover_cols, data=[], **ts,
                                    style_data_conditional=base_sdc),
                            ], style={"flex": "1"}),
                        ], style={"display": "flex", "gap": "16px"}),
                    ], style={"padding": "8px"}),
                ),
            ],
        ),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    @app.callback(
        Output("sp2-status",           "children"),
        Output("sp2-sector-table",     "data"),
        Output("sp2-sector-chart",     "figure"),
        Output("sp2-industry-table",   "data"),
        Output("sp2-industry-chart",   "figure"),
        Output("sp2-sector-pe-table",  "data"),
        Output("sp2-industry-pe-table","data"),
        Output("sp2-gainers",          "data"),
        Output("sp2-losers",           "data"),
        Output("sp2-actives",          "data"),
        Input("sp2-init",         "n_intervals"),
        Input("sp2-refresh-btn",  "n_clicks"),
        prevent_initial_call=False,
    )
    def refresh(_n_init, _n_click):
        import pandas as pd
        from ada_research.core.fmp_client import FmpClient

        empty_fig = go.Figure()
        _apply_dark(empty_fig)

        try:
            c = FmpClient()
            data = {
                "sector":      c.sector_snapshot(),
                "industry":    c.industry_snapshot(),
                "sector_pe":   c.sector_pe(),
                "industry_pe": c.industry_pe(),
                "gainers":     c.gainers(),
                "losers":      c.losers(),
                "actives":     c.most_actives(),
            }
        except Exception as exc:
            log.exception("FMP sectors fetch failed")
            return (f"Error: {exc}", [], empty_fig, [], empty_fig,
                    [], [], [], [], [])

        def perf_rows(df: pd.DataFrame, name_col: str, val_col: str, fmt_pct: bool = True):
            if df.empty or name_col not in df.columns:
                return []
            df = df.copy()
            df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
            df = df.sort_values(val_col, ascending=False)
            rows = []
            for _, r in df.iterrows():
                v = r.get(val_col)
                rows.append({
                    name_col: str(r.get(name_col, "")),
                    val_col:  (f"{v:+.2f}%" if fmt_pct else f"{v:.2f}") if pd.notna(v) else "—",
                })
            return rows

        def perf_chart(df: pd.DataFrame, name_col: str, val_col: str, title: str) -> go.Figure:
            if df.empty or name_col not in df.columns:
                f = go.Figure(); _apply_dark(f); return f
            df = df.copy()
            df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
            df = df.dropna(subset=[val_col]).sort_values(val_col)
            return _bar_chart(df[name_col].tolist(), df[val_col].tolist(), title)

        def mover_rows(df: pd.DataFrame):
            if df.empty:
                return []
            out = []
            for _, r in df.head(20).iterrows():
                chg = r.get("changesPercentage")
                out.append({
                    "symbol": str(r.get("symbol", "")),
                    "name":   str(r.get("name", "")),
                    "price":  f"${r['price']:,.2f}" if r.get("price") else "—",
                    "change": f"{chg:+.2f}%" if chg is not None and pd.notna(chg) else "—",
                })
            return out

        sector_rows   = perf_rows(data["sector"],   "sector",   "averageChange")
        sector_chart  = perf_chart(data["sector"],  "sector",   "averageChange", "Sector Performance")
        industry_rows = perf_rows(data["industry"], "industry", "averageChange")
        industry_chart= perf_chart(data["industry"],"industry", "averageChange", "Industry Performance")
        sec_pe_rows   = perf_rows(data["sector_pe"],  "sector",   "pe", fmt_pct=False)
        ind_pe_rows   = perf_rows(data["industry_pe"],"industry", "pe", fmt_pct=False)

        return (
            "Updated.",
            sector_rows,   sector_chart,
            industry_rows, industry_chart,
            sec_pe_rows,   ind_pe_rows,
            mover_rows(data["gainers"]),
            mover_rows(data["losers"]),
            mover_rows(data["actives"]),
        )


def _apply_dark(fig: go.Figure) -> None:
    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"]},
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
    )
