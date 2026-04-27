"""Sprint 1: Industry Performance (Dash/Plotly UI).

Industry-first market performance tab. Uses FMP market-performance endpoints
split across two user-triggered fetches to minimise API calls:

  Fetch A — "Refresh" button (also auto-fires on page load)
    /historical-industry-performance   (daily series for chosen industry)
    /historical-industry-pe            (P/E time series for chosen industry)
    Today's change is read from the most-recent row of the history.

  Fetch B — "Load Market Snapshot" button (manual, on demand)
    /industry-performance-snapshot     (today's avg change, all industries)
    /industry-pe-snapshot              (today's P/E, all industries)

Layout
------
Top  — Toolbar
  • Industry dropdown
  • Lookback dropdown (30 / 60 / 90 / 180 / 365 days)
  • Refresh button          → updates stat cards + twin charts (Fetch A)
  • Load Market Snapshot    → updates scatter + leaders/laggards (Fetch B)

Mid  — Stat cards
  • Today % change            (most-recent history row)
  • Period avg daily change   (mean of history)
  • Period total return       (compounded)
  • Current industry P/E      (most-recent P/E history row)
  • Period P/E change         (first vs last P/E)

Mid  — Charts (side by side)
  • Daily % change for the chosen industry over the lookback
  • P/E for the chosen industry over the lookback

Bottom — Market Snapshot (populated on demand)
  • Industry P/E & Return Snapshot  (scatter, all industries)
  • Today's Industry Leaders & Laggards (bar charts, all industries)
  • Full sortable industry table

Requires FMP_API_KEY.
"""
from __future__ import annotations

from typing import Any

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import (
    btn,
    placeholder_panel,
    section_header,
    status_label,
    subsection_title,
)
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERIOD_OPTIONS = [
    {"label": "30 days",  "value": 30},
    {"label": "60 days",  "value": 60},
    {"label": "90 days",  "value": 90},
    {"label": "180 days", "value": 180},
    {"label": "365 days", "value": 365},
]

_FALLBACK_INDUSTRIES = [
    "Semiconductors", "Software - Application", "Software - Infrastructure",
    "Banks - Diversified", "Banks - Regional", "Insurance - Diversified",
    "Oil & Gas E&P", "Oil & Gas Integrated", "Oil & Gas Midstream",
    "Drug Manufacturers - General", "Biotechnology", "Medical Devices",
    "Aerospace & Defense", "Auto Manufacturers", "Internet Retail",
    "REIT - Residential", "Utilities - Regulated Electric",
]


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _empty_fig(height: int = 300, msg: str = "No data") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text_dim"]},
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=height,
        annotations=[{
            "text": msg, "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5, "showarrow": False,
            "font": {"color": COLORS["text_dim"], "size": 13},
        }],
    )
    return fig


def _line_fig(df: pd.DataFrame, val_col: str, title: str,
              color: str, fmt: str = "pct") -> go.Figure:
    """Single-line time series. fmt=='pct' draws a zero baseline."""
    if df is None or df.empty or val_col not in df.columns:
        return _empty_fig(msg="No data for this period")

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    fig = go.Figure(go.Scatter(
        x=df["date"], y=df[val_col],
        mode="lines", line={"color": color, "width": 2},
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>",
        name=title,
    ))
    if fmt == "pct":
        fig.add_hline(y=0, line_color=COLORS["border"], line_width=1)
    fig.update_layout(
        title={"text": title, "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 50, "r": 20, "t": 36, "b": 36},
        xaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"]},
        yaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"]},
        height=300,
        hovermode="x unified",
    )
    return fig


def _hbar(names: list, values: list, title: str) -> go.Figure:
    """Horizontal bar chart, green/red by sign."""
    if not names:
        return _empty_fig(msg="No data")
    colors = [COLORS["good"] if v >= 0 else COLORS["bad"] for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in values],
        textposition="outside",
        textfont={"color": COLORS["text"], "size": 11},
        hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title={"text": title, "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 200, "r": 60, "t": 36, "b": 20},
        xaxis={"gridcolor": COLORS["border"], "zeroline": True,
               "zerolinecolor": COLORS["border"]},
        yaxis={"gridcolor": "rgba(0,0,0,0)"},
        height=max(280, len(names) * 28 + 60),
    )
    return fig


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_pct(v: Any, signed: bool = True) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _fmt_num(v: Any, decimals: int = 1) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _tone_for_change(v: Any) -> dict:
    """Return inline style dict colored by sign of change."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return {"color": COLORS["text"]}
    if f > 0: return {"color": COLORS["good"]}
    if f < 0: return {"color": COLORS["bad"]}
    return {"color": COLORS["text"]}


def _coerce_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


# ---------------------------------------------------------------------------
# Initial industry list (lazy — populated on first page render)
# ---------------------------------------------------------------------------

def _industries_for_dropdown() -> list[dict]:
    """Try to load the live industry list, falling back to a hardcoded set."""
    try:
        from ada_research.core.fmp_client import FmpClient
        df = FmpClient().industry_snapshot()
        if not df.empty and "industry" in df.columns:
            names = sorted(df["industry"].dropna().unique().tolist())
            return [{"label": n, "value": n} for n in names]
    except Exception as exc:
        log.warning("industry dropdown fallback: %s", exc)
    return [{"label": n, "value": n} for n in _FALLBACK_INDUSTRIES]


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 1 — Industry Performance",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart the server.",
            ),
            className="tab-content",
        )

    industry_options = _industries_for_dropdown()
    default_industry = next(
        (o["value"] for o in industry_options if o["value"] == "Semiconductors"),
        industry_options[0]["value"] if industry_options else None,
    )

    ts = TABLE_STYLES()
    base_sdc = ts.pop("style_data_conditional", [])
    ts["style_data_conditional"] = base_sdc + [
        {"if": {"filter_query": '{averageChange} contains "+"', "column_id": "averageChange"},
         "color": COLORS["good"], "fontWeight": "600"},
        {"if": {"filter_query": '{averageChange} contains "-"', "column_id": "averageChange"},
         "color": COLORS["bad"], "fontWeight": "600"},
    ]

    _snapshot_prompt = (
        "Click 'Load Market Snapshot' in the toolbar to populate this section."
    )

    return html.Div([
        # Auto-fire fetch on first render (industry data only)
        dcc.Interval(id="sp1-init", interval=400, max_intervals=1),

        section_header(
            "Sprint 1 — Industry Performance",
            "Select an industry and use Refresh to load its trend. "
            "Use 'Load Market Snapshot' to compare all ~150 industries.",
        ),

        # ── Toolbar ──────────────────────────────────────────────────────
        html.Div([
            html.Label("Industry:", style={"color": COLORS["text_dim"],
                                            "fontSize": "12px", "whiteSpace": "nowrap"}),
            dcc.Dropdown(
                id="sp1-industry",
                options=industry_options,
                value=default_industry,
                clearable=False,
                style={"minWidth": "260px",
                       "backgroundColor": COLORS["panel"],
                       "color": COLORS["text"],
                       "border": f"1px solid {COLORS['border']}",
                       "borderRadius": "4px",
                       "fontSize": "13px"},
            ),
            html.Label("Lookback:", style={"color": COLORS["text_dim"],
                                            "fontSize": "12px", "whiteSpace": "nowrap"}),
            dcc.Dropdown(
                id="sp1-period",
                options=_PERIOD_OPTIONS,
                value=90,
                clearable=False,
                style={"minWidth": "120px",
                       "backgroundColor": COLORS["panel"],
                       "color": COLORS["text"],
                       "border": f"1px solid {COLORS['border']}",
                       "borderRadius": "4px",
                       "fontSize": "13px"},
            ),
            btn("Refresh", "sp1-refresh-btn", primary=True),
            btn("Load Market Snapshot", "sp1-snapshot-btn", primary=False),
        ], className="toolbar-row"),

        # ── Stat cards ───────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Today",          className="stat-label"),
                html.Div("—", id="sp1-stat-today",   className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Avg Daily (period)", className="stat-label"),
                html.Div("—", id="sp1-stat-avg",     className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Period Total",   className="stat-label"),
                html.Div("—", id="sp1-stat-total",   className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Industry P/E",   className="stat-label"),
                html.Div("—", id="sp1-stat-pe",      className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("P/E Δ (period)", className="stat-label"),
                html.Div("—", id="sp1-stat-pe-chg",  className="stat-value"),
            ], className="stat-card"),
        ], className="stats-row"),

        # ── Twin charts: performance + P/E ───────────────────────────────
        html.Div([
            html.Div(
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dcc.Graph(
                                id="sp1-perf-chart",
                                figure=_empty_fig(),
                                config={"displayModeBar": False},
                            )),
                style={"flex": "1", "minWidth": "320px"},
            ),
            html.Div(
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dcc.Graph(
                                id="sp1-pe-chart",
                                figure=_empty_fig(),
                                config={"displayModeBar": False},
                            )),
                style={"flex": "1", "minWidth": "320px"},
            ),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginBottom": "16px"}),

        status_label("sp1-status"),

        # ── Industry P/E & Return Snapshot (on demand) ───────────────────
        subsection_title("Industry P/E & Return Snapshot"),
        dcc.Loading(type="circle", color=COLORS["accent"],
                    children=dcc.Graph(
                        id="sp1-pe-return-scatter",
                        figure=_empty_fig(height=400, msg=_snapshot_prompt),
                        config={"displayModeBar": False},
                    )),
        html.Div(style={"marginBottom": "16px"}),

        # ── Leaders / laggards (on demand) ───────────────────────────────
        subsection_title("Today's Industry Leaders & Laggards"),
        html.Div([
            html.Div(
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dcc.Graph(
                                id="sp1-leaders-chart",
                                figure=_empty_fig(height=320, msg=_snapshot_prompt),
                                config={"displayModeBar": False},
                            )),
                style={"flex": "1", "minWidth": "320px"},
            ),
            html.Div(
                dcc.Loading(type="circle", color=COLORS["accent"],
                            children=dcc.Graph(
                                id="sp1-laggards-chart",
                                figure=_empty_fig(height=320, msg=_snapshot_prompt),
                                config={"displayModeBar": False},
                            )),
                style={"flex": "1", "minWidth": "320px"},
            ),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginBottom": "16px"}),

        # ── Full industry table for today ────────────────────────────────
        html.Details([
            html.Summary("All Industries (today)",
                         style={"cursor": "pointer", "color": COLORS["text_dim"],
                                "fontSize": "12px", "marginBottom": "6px",
                                "userSelect": "none"}),
            dash_table.DataTable(
                id="sp1-all-table",
                columns=[
                    {"name": "Industry",  "id": "industry"},
                    {"name": "% Change",  "id": "averageChange"},
                ],
                data=[],
                page_size=20,
                sort_action="native",
                **ts,
            ),
        ]),

        status_label("sp1-snapshot-status"),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    # ── Callback A: specific industry data (Fetch A) ─────────────────────
    # 2 API calls: historical_industry + historical_industry_pe
    # Triggered by: page load interval, Refresh button
    @app.callback(
        Output("sp1-stat-today",   "children"),
        Output("sp1-stat-today",   "style"),
        Output("sp1-stat-avg",     "children"),
        Output("sp1-stat-avg",     "style"),
        Output("sp1-stat-total",   "children"),
        Output("sp1-stat-total",   "style"),
        Output("sp1-stat-pe",      "children"),
        Output("sp1-stat-pe-chg",  "children"),
        Output("sp1-stat-pe-chg",  "style"),
        Output("sp1-perf-chart",   "figure"),
        Output("sp1-pe-chart",     "figure"),
        Output("sp1-status",       "children"),
        Input("sp1-init",          "n_intervals"),
        Input("sp1-refresh-btn",   "n_clicks"),
        State("sp1-industry",      "value"),
        State("sp1-period",        "value"),
        prevent_initial_call=False,
    )
    def fetch_industry(_n_init, _n_click, industry, period):
        from ada_research.core.fmp_client import FmpClient

        if not industry:
            raise PreventUpdate

        days = int(period or 90)
        try:
            c = FmpClient()
            hist_perf = c.historical_industry(industry, days=days)
            hist_pe   = c.historical_industry_pe(industry, days=days)
        except Exception as exc:
            log.exception("FMP industry fetch failed")
            return _err_industry(f"Error: {exc}")

        # ── Today's value: most-recent row of the history ────────────────
        today_val = None
        perf_fig = _empty_fig(msg="No history for this industry")
        avg_str, avg_sty, tot_str, tot_sty = "—", {}, "—", {}

        if not hist_perf.empty and "averageChange" in hist_perf.columns:
            hp = hist_perf.copy()
            hp["averageChange"] = _coerce_num(hp["averageChange"])
            hp["date"] = pd.to_datetime(hp["date"])
            hp = hp.sort_values("date").dropna(subset=["averageChange"])
            if not hp.empty:
                today_val = hp["averageChange"].iloc[-1]
                avg_val   = hp["averageChange"].mean()
                tot_val   = ((1 + hp["averageChange"] / 100.0).prod() - 1) * 100.0
                avg_str, avg_sty = _fmt_pct(avg_val), _tone_for_change(avg_val)
                tot_str, tot_sty = _fmt_pct(tot_val), _tone_for_change(tot_val)
                perf_fig = _line_fig(hp, "averageChange",
                                     f"{industry} — Daily % Change ({days}d)",
                                     COLORS["accent"], fmt="pct")

        today_str = _fmt_pct(today_val)
        today_sty = _tone_for_change(today_val)

        # ── Industry P/E ─────────────────────────────────────────────────
        pe_str = "—"
        pe_chg_str, pe_chg_sty = "—", {}
        pe_fig = _empty_fig(msg="No P/E history")

        if not hist_pe.empty and "pe" in hist_pe.columns:
            ph = hist_pe.copy()
            ph["pe"] = _coerce_num(ph["pe"])
            ph["date"] = pd.to_datetime(ph["date"])
            ph = ph.sort_values("date").dropna(subset=["pe"])
            if not ph.empty:
                pe_curr = ph["pe"].iloc[-1]
                pe_str  = (_fmt_num(pe_curr, decimals=2) + "x"
                           if pe_curr == pe_curr else "—")
                if len(ph) >= 2:
                    first_pe = ph["pe"].iloc[0]
                    if first_pe and first_pe == first_pe and first_pe != 0:
                        chg_val    = (pe_curr - first_pe) / first_pe * 100.0
                        pe_chg_str = _fmt_pct(chg_val)
                        pe_chg_sty = _tone_for_change(chg_val)
                pe_fig = _line_fig(ph, "pe",
                                   f"{industry} — P/E ({days}d)",
                                   COLORS["warn"], fmt="num")

        status = (f"{industry}: {today_str} today · {days}d lookback · "
                  "click 'Load Market Snapshot' to see all industries.")

        return (
            today_str, today_sty,
            avg_str,   avg_sty,
            tot_str,   tot_sty,
            pe_str,
            pe_chg_str, pe_chg_sty,
            perf_fig, pe_fig,
            status,
        )

    # ── Callback B: market-wide snapshot (Fetch B) ────────────────────────
    # 2 API calls: industry_snapshot + industry_pe
    # Triggered by: "Load Market Snapshot" button only
    @app.callback(
        Output("sp1-pe-return-scatter", "figure"),
        Output("sp1-leaders-chart",     "figure"),
        Output("sp1-laggards-chart",    "figure"),
        Output("sp1-all-table",         "data"),
        Output("sp1-snapshot-status",   "children"),
        Input("sp1-snapshot-btn",       "n_clicks"),
        prevent_initial_call=True,
    )
    def fetch_market_snapshot(n_clicks):
        from ada_research.core.fmp_client import FmpClient

        if not n_clicks:
            raise PreventUpdate

        try:
            c = FmpClient()
            ind_snap = c.industry_snapshot()
            ind_pe   = c.industry_pe()
        except Exception as exc:
            log.exception("FMP snapshot fetch failed")
            empty = _empty_fig()
            return empty, empty, empty, [], f"Error: {exc}"

        pe_return_fig              = _build_pe_return_scatter(ind_snap, ind_pe)
        leaders_fig, laggards_fig, all_rows = _build_leaderboards(ind_snap)

        n_total = len(all_rows)
        status  = f"Market snapshot loaded · {n_total} industries."

        return pe_return_fig, leaders_fig, laggards_fig, all_rows, status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_pe_return_scatter(snap: pd.DataFrame, pe_df: pd.DataFrame) -> go.Figure:
    """Scatter: x=today % change, y=P/E, one bubble per industry."""
    if snap is None or snap.empty or pe_df is None or pe_df.empty:
        return _empty_fig(height=400, msg="No snapshot data")

    df = snap[["industry", "averageChange"]].copy()
    df["averageChange"] = _coerce_num(df["averageChange"])

    pe = pe_df[["industry", "pe"]].copy() if "pe" in pe_df.columns else pd.DataFrame()
    if pe.empty:
        return _empty_fig(height=400, msg="No P/E snapshot data")
    pe["pe"] = _coerce_num(pe["pe"])

    merged = df.merge(pe, on="industry", how="inner").dropna()
    if merged.empty:
        return _empty_fig(height=400, msg="No matched industry data")

    colors = [COLORS["good"] if v >= 0 else COLORS["bad"] for v in merged["averageChange"]]

    fig = go.Figure(go.Scatter(
        x=merged["averageChange"],
        y=merged["pe"],
        mode="markers+text",
        text=merged["industry"],
        textposition="top center",
        textfont={"size": 8, "color": COLORS["text_dim"]},
        marker={"color": colors, "size": 9, "opacity": 0.85,
                "line": {"width": 0.5, "color": COLORS["border"]}},
        hovertemplate="<b>%{text}</b><br>Return: %{x:+.2f}%<br>P/E: %{y:.1f}x<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=COLORS["border"], line_width=1, line_dash="dash")
    fig.update_layout(
        title={"text": "All Industries — P/E vs Today's Return",
               "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 60, "r": 20, "t": 40, "b": 50},
        xaxis={"title": "Today's % Change", "gridcolor": COLORS["border"],
               "zeroline": True, "zerolinecolor": COLORS["border"],
               "linecolor": COLORS["border"]},
        yaxis={"title": "P/E Ratio", "gridcolor": COLORS["border"],
               "linecolor": COLORS["border"]},
        height=400,
        hovermode="closest",
        showlegend=False,
    )
    return fig


def _build_leaderboards(snap: pd.DataFrame) -> tuple[go.Figure, go.Figure, list[dict]]:
    """Top-10/bottom-10 horizontal bars + sorted full table."""
    if snap is None or snap.empty or "industry" not in snap.columns:
        empty = _empty_fig(height=320, msg="No snapshot data")
        return empty, empty, []

    df = snap.copy()
    df["averageChange"] = _coerce_num(df["averageChange"])
    df = df.dropna(subset=["averageChange"]).sort_values("averageChange", ascending=False)

    if df.empty:
        empty = _empty_fig(height=320, msg="No snapshot data")
        return empty, empty, []

    top10 = df.head(10).iloc[::-1]
    bot10 = df.tail(10)

    leaders = _hbar(
        top10["industry"].tolist(),
        top10["averageChange"].tolist(),
        "Top 10 Today",
    )
    laggards = _hbar(
        bot10["industry"].tolist(),
        bot10["averageChange"].tolist(),
        "Bottom 10 Today",
    )

    all_rows = [
        {"industry": str(r["industry"]),
         "averageChange": _fmt_pct(r["averageChange"])}
        for _, r in df.iterrows()
    ]
    return leaders, laggards, all_rows


def _err_industry(msg: str) -> tuple:
    """Match the 12-element Callback A signature on error paths."""
    empty = _empty_fig()
    return (
        "—", {}, "—", {}, "—", {},   # today / avg / total
        "—",                           # pe
        "—", {},                       # pe change
        empty, empty,                  # perf + pe charts
        msg,
    )
