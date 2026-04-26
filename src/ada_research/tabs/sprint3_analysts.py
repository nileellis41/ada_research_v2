"""Sprint 3: Sector & Industry Analysis (Dash/Plotly UI).

Layout
------
Top — Overview (auto-loads on page open, Refresh button)
  • Sector Performance bar chart  (left)
  • Sector P/E bar chart          (right)
  • Gainers / Losers / Most Active tables (3-column row)

Bottom — Sector Deep Dive (user-driven)
  • Pick a primary sector + up to 3 comparison sectors + lookback period
  • Multi-sector historical performance line chart
  • Historical P/E line chart for the primary sector
  • Industry performance today: bar chart + sortable table

Requires FMP_API_KEY.
"""
from __future__ import annotations

import dash
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import btn, placeholder_panel, section_header, status_label
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)

# FMP sector names as returned by the /sector-performance-snapshot endpoint
_SECTORS = [
    "Basic Materials",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Energy",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Real Estate",
    "Technology",
    "Utilities",
]

# Colour palette for comparison lines (primary always uses accent)
_COMPARE_COLORS = [
    "#e57373", "#ffb74d", "#4caf50", "#ce93d8",
    "#80cbc4", "#f06292", "#aed581", "#ff8a65",
    "#90a4ae", "#fff176",
]

_PERIOD_OPTIONS = [
    {"label": "30 days",  "value": 30},
    {"label": "60 days",  "value": 60},
    {"label": "90 days",  "value": 90},
    {"label": "180 days", "value": 180},
]

_SUB_TAB = {"className": "sub-tab", "selected_className": "sub-tab--selected"}


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _dark(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 170, "r": 50, "t": 36, "b": 20},
        xaxis={"gridcolor": COLORS["border"], "zerolinecolor": COLORS["border"]},
        yaxis={"gridcolor": "transparent"},
        height=height,
    )
    return fig


def _dark_line(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 60, "r": 20, "t": 40, "b": 40},
        xaxis={"gridcolor": COLORS["border"], "zerolinecolor": COLORS["border"],
               "linecolor": COLORS["border"]},
        yaxis={"gridcolor": COLORS["border"], "zerolinecolor": COLORS["border"],
               "linecolor": COLORS["border"]},
        legend={"bgcolor": COLORS["panel"], "bordercolor": COLORS["border"],
                "font": {"color": COLORS["text"]}, "orientation": "h",
                "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        hovermode="x unified",
        height=height,
    )
    return fig


def _empty_fig(height: int = 320) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text_dim"]},
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        height=height,
        annotations=[{"text": "No data", "xref": "paper", "yref": "paper",
                      "x": 0.5, "y": 0.5, "showarrow": False,
                      "font": {"color": COLORS["text_dim"], "size": 14}}],
    )
    return fig


def _bar_chart(names: list, values: list, title: str,
               color_by_sign: bool = True, fmt_pct: bool = True) -> go.Figure:
    if not names:
        return _empty_fig()
    colors = (
        [COLORS["good"] if v >= 0 else COLORS["bad"] for v in values]
        if color_by_sign
        else [COLORS["accent"]] * len(values)
    )
    text = [f"{v:+.2f}%" if fmt_pct else f"{v:.1f}x" for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker_color=colors,
        text=text, textposition="outside",
        textfont={"color": COLORS["text"], "size": 11},
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title={"text": title, "font": {"size": 13, "color": COLORS["text"]}},
    )
    height = max(280, len(names) * 30 + 80)
    return _dark(fig, height=height)


# ---------------------------------------------------------------------------
# Table style helpers
# ---------------------------------------------------------------------------

def _mover_ts(change_color: str | None = None):
    ts = TABLE_STYLES()
    base = ts.pop("style_data_conditional", [])
    extra = []
    if change_color:
        extra = [{"if": {"column_id": "pct_change"}, "color": change_color,
                  "fontWeight": "600"}]
    else:
        extra = [
            {"if": {"filter_query": "{pct_change} contains '+'", "column_id": "pct_change"},
             "color": COLORS["good"], "fontWeight": "600"},
            {"if": {"filter_query": "{pct_change} contains '-'", "column_id": "pct_change"},
             "color": COLORS["bad"], "fontWeight": "600"},
        ]
    ts["style_data_conditional"] = base + extra
    return ts


_MOVER_COLS = [
    {"name": "Symbol",   "id": "symbol"},
    {"name": "Name",     "id": "name"},
    {"name": "Price",    "id": "price"},
    {"name": "% Chg",    "id": "pct_change"},
]

_INDUSTRY_COLS = [
    {"name": "Industry",    "id": "industry"},
    {"name": "Avg % Chg",   "id": "averageChange"},
]


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 3 — Sector Analysis",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart.",
            ),
            className="tab-content",
        )

    sector_opts  = [{"label": s, "value": s} for s in _SECTORS]
    period_opts  = _PERIOD_OPTIONS

    ind_ts = TABLE_STYLES()
    base_sdc = ind_ts.pop("style_data_conditional", [])
    ind_ts["style_data_conditional"] = base_sdc + [
        {"if": {"filter_query": "{averageChange} contains '+'", "column_id": "averageChange"},
         "color": COLORS["good"], "fontWeight": "600"},
        {"if": {"filter_query": "{averageChange} contains '-'", "column_id": "averageChange"},
         "color": COLORS["bad"], "fontWeight": "600"},
    ]

    return html.Div([
        dcc.Store(id="sp3-overview-store"),
        dcc.Interval(id="sp3-init", interval=400, max_intervals=1),

        section_header(
            "Sprint 3 — Sector Analysis",
            "Overview: today's sector performance, valuations, and market movers. "
            "Deep Dive: compare historical sector trends side by side.",
        ),

        # ── Overview toolbar ─────────────────────────────────────────────
        html.Div([
            btn("Refresh", "sp3-refresh-btn", primary=True),
            status_label("sp3-ov-status"),
        ], className="toolbar-row"),

        # ── Overview: performance + PE charts ────────────────────────────
        html.Div([
            html.Div(
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dcc.Graph(
                                id="sp3-perf-chart",
                                figure=_empty_fig(300),
                                config={"displayModeBar": False},
                            )),
                style={"flex": "2", "minWidth": "320px"},
            ),
            html.Div(
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dcc.Graph(
                                id="sp3-pe-chart",
                                figure=_empty_fig(300),
                                config={"displayModeBar": False},
                            )),
                style={"flex": "1", "minWidth": "240px"},
            ),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginBottom": "16px"}),

        # ── Sector performance table (collapsible sub-section) ────────────
        html.Details([
            html.Summary("Sector Performance Table",
                         style={"cursor": "pointer", "color": COLORS["text_dim"],
                                "fontSize": "12px", "marginBottom": "6px",
                                "userSelect": "none"}),
            dash_table.DataTable(
                id="sp3-sector-table",
                columns=[
                    {"name": "Sector",    "id": "sector"},
                    {"name": "Avg % Chg", "id": "averageChange"},
                    {"name": "P/E",       "id": "pe"},
                ],
                data=[],
                page_size=12,
                sort_action="native",
                **ind_ts,
            ),
        ], style={"marginBottom": "16px"}),

        # ── Movers row ────────────────────────────────────────────────────
        html.Div("Market Movers", className="subsection-title",
                 style={"marginBottom": "8px"}),
        html.Div([
            html.Div([
                html.Div("Biggest Gainers", className="dim-text",
                         style={"marginBottom": "4px"}),
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dash_table.DataTable(
                                id="sp3-gainers",
                                columns=_MOVER_COLS, data=[],
                                page_size=10,
                                **_mover_ts(COLORS["good"]),
                            )),
            ], style={"flex": "1", "minWidth": "240px"}),

            html.Div([
                html.Div("Biggest Losers", className="dim-text",
                         style={"marginBottom": "4px"}),
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dash_table.DataTable(
                                id="sp3-losers",
                                columns=_MOVER_COLS, data=[],
                                page_size=10,
                                **_mover_ts(COLORS["bad"]),
                            )),
            ], style={"flex": "1", "minWidth": "240px"}),

            html.Div([
                html.Div("Most Active", className="dim-text",
                         style={"marginBottom": "4px"}),
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dash_table.DataTable(
                                id="sp3-actives",
                                columns=_MOVER_COLS, data=[],
                                page_size=10,
                                **_mover_ts(),
                            )),
            ], style={"flex": "1", "minWidth": "240px"}),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginBottom": "24px"}),

        # ─────────────────────────────────────────────────────────────────
        # Sector Deep Dive
        # ─────────────────────────────────────────────────────────────────
        html.Hr(style={"borderColor": COLORS["border"], "margin": "8px 0 16px"}),

        section_header(
            "Sector Deep Dive",
            "Pick a primary sector and up to 3 peers to compare historical "
            "performance. Industries for the primary sector are shown below.",
        ),

        # Toolbar
        html.Div([
            html.Div([
                html.Label("Primary sector", className="dim-text",
                           style={"display": "block", "marginBottom": "4px",
                                  "fontSize": "11px"}),
                dcc.Dropdown(
                    id="sp3-primary-sector",
                    options=sector_opts,
                    placeholder="Pick a sector…",
                    clearable=False,
                    style={"width": "220px", "fontSize": "13px"},
                ),
            ]),
            html.Div([
                html.Label("Compare with (up to 3)", className="dim-text",
                           style={"display": "block", "marginBottom": "4px",
                                  "fontSize": "11px"}),
                dcc.Dropdown(
                    id="sp3-compare-sectors",
                    options=sector_opts,
                    multi=True,
                    placeholder="Add comparison sectors…",
                    style={"width": "340px", "fontSize": "13px"},
                ),
            ]),
            html.Div([
                html.Label("Period", className="dim-text",
                           style={"display": "block", "marginBottom": "4px",
                                  "fontSize": "11px"}),
                dcc.Dropdown(
                    id="sp3-period",
                    options=period_opts,
                    value=90,
                    clearable=False,
                    style={"width": "120px", "fontSize": "13px"},
                ),
            ]),
            html.Div(
                btn("Load", "sp3-dive-btn", primary=True),
                style={"alignSelf": "flex-end", "paddingBottom": "1px"},
            ),
            status_label("sp3-dive-status"),
        ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap",
                  "alignItems": "flex-end", "marginBottom": "16px"}),

        # Deep Dive results
        dcc.Loading(
            type="circle", color=COLORS["accent"],
            children=html.Div(id="sp3-dive-content",
                              children=html.Div(
                                  "Select a primary sector and click Load.",
                                  className="dim-text",
                                  style={"padding": "24px 0"},
                              )),
        ),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    # ── Overview: auto-load + refresh ────────────────────────────────────

    @app.callback(
        Output("sp3-perf-chart",    "figure"),
        Output("sp3-pe-chart",      "figure"),
        Output("sp3-sector-table",  "data"),
        Output("sp3-gainers",       "data"),
        Output("sp3-losers",        "data"),
        Output("sp3-actives",       "data"),
        Output("sp3-ov-status",     "children"),
        Input("sp3-init",           "n_intervals"),
        Input("sp3-refresh-btn",    "n_clicks"),
        prevent_initial_call=False,
    )
    def load_overview(_init, _refresh):
        import pandas as pd
        from ada_research.core.sector_data import get_bundle

        try:
            force  = dash.ctx.triggered_id == "sp3-refresh-btn"
            bundle = get_bundle(force=force)
            df_sector = bundle.sector_snapshot
            df_pe     = bundle.sector_pe
            df_gain   = bundle.gainers
            df_lose   = bundle.losers
            df_act    = bundle.actives
        except Exception as exc:
            log.exception("Sprint 3 overview fetch failed")
            e = _empty_fig()
            return e, e, [], [], [], [], f"Error: {exc}"

        # Performance bar chart
        if not df_sector.empty and "averageChange" in df_sector.columns:
            df_s = df_sector.copy()
            df_s["averageChange"] = pd.to_numeric(df_s["averageChange"], errors="coerce")
            df_s = df_s.dropna(subset=["averageChange"]).sort_values("averageChange")
            perf_fig = _bar_chart(
                df_s["sector"].tolist(),
                df_s["averageChange"].tolist(),
                "Sector Performance — Today",
            )
        else:
            perf_fig = _empty_fig()

        # PE bar chart
        if not df_pe.empty and "pe" in df_pe.columns:
            df_p = df_pe.copy()
            df_p["pe"] = pd.to_numeric(df_p["pe"], errors="coerce")
            df_p = df_p[(df_p["pe"] > 0) & (df_p["pe"] < 500)].dropna(subset=["pe"])
            df_p = df_p.sort_values("pe")
            pe_fig = _bar_chart(
                df_p["sector"].tolist(),
                df_p["pe"].tolist(),
                "Sector P/E — Today",
                color_by_sign=False,
                fmt_pct=False,
            )
        else:
            pe_fig = _empty_fig()

        # Merged sector table (perf + PE joined on sector name)
        sector_rows = []
        if not df_sector.empty:
            df_s2 = df_sector.copy()
            df_s2["averageChange"] = pd.to_numeric(df_s2["averageChange"], errors="coerce")
            if not df_pe.empty:
                df_pe2 = df_pe.copy()
                df_pe2["pe"] = pd.to_numeric(df_pe2["pe"], errors="coerce")
                merged = df_s2.merge(df_pe2[["sector", "pe"]], on="sector", how="left")
            else:
                merged = df_s2.copy()
                merged["pe"] = None
            merged = merged.sort_values("averageChange", ascending=False)
            for _, r in merged.iterrows():
                chg = r.get("averageChange")
                pe  = r.get("pe")
                sector_rows.append({
                    "sector":        str(r.get("sector", "")),
                    "averageChange": f"{chg:+.2f}%" if pd.notna(chg) else "—",
                    "pe":            f"{pe:.1f}x" if pe is not None and pd.notna(pe) else "—",
                })

        def mover_rows(df: pd.DataFrame) -> list[dict]:
            if df.empty:
                return []
            out = []
            for _, r in df.head(15).iterrows():
                chg = r.get("changesPercentage")
                out.append({
                    "symbol":     str(r.get("symbol", "")),
                    "name":       str(r.get("name", ""))[:32],
                    "price":      f"${float(r['price']):,.2f}" if r.get("price") else "—",
                    "pct_change": f"{chg:+.2f}%" if chg is not None and pd.notna(chg) else "—",
                })
            return out

        age = f" (cached {int(bundle.age_seconds)}s ago)" if bundle.age_seconds > 5 else ""
        return (
            perf_fig, pe_fig, sector_rows,
            mover_rows(df_gain), mover_rows(df_lose), mover_rows(df_act),
            f"Updated.{age}",
        )

    # ── Sector Deep Dive ─────────────────────────────────────────────────

    @app.callback(
        Output("sp3-dive-content", "children"),
        Output("sp3-dive-status",  "children"),
        Input("sp3-dive-btn",      "n_clicks"),
        State("sp3-primary-sector",  "value"),
        State("sp3-compare-sectors", "value"),
        State("sp3-period",          "value"),
        prevent_initial_call=True,
    )
    def load_dive(_n, primary, compare_sectors, period):
        import pandas as pd
        from ada_research.core.sector_data import get_bundle

        if not primary:
            raise PreventUpdate

        days    = int(period or 90)
        compare = list(compare_sectors or [])[:3]
        compare = [s for s in compare if s != primary]

        try:
            bundle = get_bundle()

            # Historical performance — bundle has 90 days; tail() to the requested window
            hist_data: dict[str, pd.DataFrame] = {}
            for s in [primary] + compare:
                df = bundle.hist_sector_perf.get(s, pd.DataFrame())
                hist_data[s] = df.tail(days).copy() if not df.empty else df

            # Historical PE — bundle has 180 days; slice to requested window
            pe_raw = bundle.hist_sector_pe.get(primary, pd.DataFrame())
            hist_pe = pe_raw.tail(days).copy() if not pe_raw.empty else pe_raw

            # Today's industry snapshot (pre-fetched)
            df_ind = bundle.industry_snapshot.copy() if not bundle.industry_snapshot.empty else pd.DataFrame()

        except Exception as exc:
            log.exception("Sprint 3 deep dive failed")
            return (
                html.Div(f"Error: {exc}", className="dim-text"),
                f"Error: {exc}",
            )

        # ── Multi-sector performance chart ──────────────────────────────
        perf_fig = go.Figure()
        all_sectors_ordered = [primary] + compare
        palette = [COLORS["accent"]] + _COMPARE_COLORS[:len(compare)]

        for idx, sec in enumerate(all_sectors_ordered):
            df_h = hist_data.get(sec, pd.DataFrame())
            if df_h.empty:
                continue
            is_primary = (sec == primary)
            perf_fig.add_trace(go.Scatter(
                x=df_h["date"],
                y=df_h["averageChange"],
                mode="lines",
                name=sec,
                line={
                    "color": palette[idx],
                    "width": 2.5 if is_primary else 1.5,
                    "dash":  "solid" if is_primary else "dot",
                },
                hovertemplate=f"<b>{sec}</b><br>%{{x|%b %d}}: %{{y:+.2f}}%<extra></extra>",
            ))

        if perf_fig.data:
            perf_fig.add_hline(y=0, line_dash="dash", line_color=COLORS["border"],
                               line_width=1)
            _dark_line(perf_fig, height=360)
            perf_fig.update_layout(
                title={"text": f"Historical Daily % Change — {days}-day window",
                       "font": {"size": 13, "color": COLORS["text"]}},
                yaxis_title="Avg Daily % Change",
            )
        else:
            perf_fig = _empty_fig(360)

        # ── Historical PE chart (primary only) ──────────────────────────
        pe_fig = go.Figure()
        if not hist_pe.empty:
            pe_fig.add_trace(go.Scatter(
                x=hist_pe["date"],
                y=hist_pe["pe"],
                mode="lines",
                name=f"{primary} P/E",
                line={"color": COLORS["accent"], "width": 2},
                fill="tozeroy",
                fillcolor=f"rgba(91,155,213,0.12)",
                hovertemplate="P/E: %{y:.1f}<extra></extra>",
            ))
            _dark_line(pe_fig, height=280)
            pe_fig.update_layout(
                title={"text": f"{primary} — Historical P/E Ratio ({days} days)",
                       "font": {"size": 13, "color": COLORS["text"]}},
                yaxis_title="P/E",
                margin={"l": 60, "r": 20, "t": 40, "b": 40},
            )
        else:
            pe_fig = _empty_fig(280)

        # ── Industry performance today ──────────────────────────────────
        ind_fig = _empty_fig(300)
        ind_rows: list[dict] = []
        ind_ts   = TABLE_STYLES()
        base_sdc = ind_ts.pop("style_data_conditional", [])
        ind_ts["style_data_conditional"] = base_sdc + [
            {"if": {"filter_query": "{averageChange} contains '+'",
                    "column_id": "averageChange"},
             "color": COLORS["good"], "fontWeight": "600"},
            {"if": {"filter_query": "{averageChange} contains '-'",
                    "column_id": "averageChange"},
             "color": COLORS["bad"], "fontWeight": "600"},
        ]

        if not df_ind.empty and "averageChange" in df_ind.columns:
            df_ind = df_ind.copy()
            df_ind["averageChange"] = pd.to_numeric(df_ind["averageChange"], errors="coerce")
            df_ind = df_ind.dropna(subset=["averageChange"])
            df_ind_sorted = df_ind.sort_values("averageChange", ascending=False)

            # Top 10 + bottom 10 for the bar chart
            top10    = df_ind_sorted.head(10)
            bot10    = df_ind_sorted.tail(10).iloc[::-1]
            vis_rows = pd.concat([top10, bot10]).drop_duplicates()
            vis_rows = vis_rows.sort_values("averageChange")
            ind_fig  = _bar_chart(
                vis_rows["industry"].tolist(),
                vis_rows["averageChange"].tolist(),
                "Top & Bottom 10 Industries Today",
            )

            # Full table
            for _, r in df_ind_sorted.iterrows():
                chg = r.get("averageChange")
                ind_rows.append({
                    "industry":     str(r.get("industry", "")),
                    "averageChange": f"{chg:+.2f}%" if pd.notna(chg) else "—",
                })

        # ── Assemble dive content ───────────────────────────────────────
        content = html.Div([

            # Performance comparison chart
            html.Div("Historical Performance Comparison", className="subsection-title"),
            dcc.Graph(figure=perf_fig, config={"displayModeBar": True},
                      style={"marginBottom": "16px"}),

            # Historical PE chart
            html.Div(f"{primary} — Historical P/E", className="subsection-title"),
            dcc.Graph(figure=pe_fig, config={"displayModeBar": False},
                      style={"marginBottom": "16px"}),

            # Industry bar chart + table
            html.Div("Industry Performance Today", className="subsection-title"),
            dcc.Graph(figure=ind_fig, config={"displayModeBar": False},
                      style={"marginBottom": "12px"}),

            html.Details([
                html.Summary("Full industry table",
                             style={"cursor": "pointer", "color": COLORS["text_dim"],
                                    "fontSize": "12px", "marginBottom": "6px",
                                    "userSelect": "none"}),
                dash_table.DataTable(
                    columns=_INDUSTRY_COLS,
                    data=ind_rows,
                    page_size=20,
                    sort_action="native",
                    **ind_ts,
                ),
            ]),

        ])

        return content, f"{primary} loaded ({days}-day window)."
