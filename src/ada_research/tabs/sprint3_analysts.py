"""Sprint 3: Analyst Features (Dash/Plotly UI).

What Wall Street thinks about a single ticker — price targets, B/H/S
distribution, recent rating actions — plus a market-wide upgrades /
downgrades feed.

Mirrors the nine endpoints from `re/sprint3_analyst_features.ipynb`. All
calls go through `FmpClient.safe(...)` so endpoints that are gated to a
paid plan (notably `/price-target-news`) just degrade silently rather
than crash the tab.

Layout
------
Top — Toolbar
  • Ticker input + Fetch button

Per-ticker section (driven by Fetch)
  • Price target stat cards: consensus / median / high / low + implied % vs spot
  • Recommendation distribution: stat cards + horizontal bar chart
  • Recent rating actions table (per-symbol grades feed)
  • Forward analyst estimates table (revenue / EPS forward years)

Market section (auto-loads on tab open, independent of the ticker)
  • Latest grade actions across the whole market — "what moved overnight"

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
    text_input,
)
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Order matters — strong-buy on the left, strong-sell on the right.
_BHS_KEYS: list[tuple[str, str, str]] = [
    # (FMP key,        display label,  bar color)
    ("strongBuy",      "Strong Buy",   COLORS["good"]),
    ("buy",            "Buy",          "#2ecc71"),
    ("hold",           "Hold",         COLORS["warn"]),
    ("sell",           "Sell",         "#e74c3c"),
    ("strongSell",     "Strong Sell",  COLORS["bad"]),
]

# Forward-estimate columns we surface (best-effort — names vary across FMP versions).
_ESTIMATE_DISPLAY_COLS: list[tuple[str, str]] = [
    ("date",                       "Period"),
    ("estimatedRevenueAvg",        "Rev Avg"),
    ("estimatedRevenueLow",        "Rev Low"),
    ("estimatedRevenueHigh",       "Rev High"),
    ("estimatedEpsAvg",            "EPS Avg"),
    ("estimatedEpsLow",            "EPS Low"),
    ("estimatedEpsHigh",           "EPS High"),
    ("numberAnalystsEstimatedEps", "# Analysts"),
]


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _empty_fig(height: int = 240, msg: str = "No data") -> go.Figure:
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


def _bhs_chart(counts: dict[str, int], ticker: str) -> go.Figure:
    """Vertical bar chart of strong-buy → strong-sell distribution."""
    if not counts or sum(counts.values()) == 0:
        return _empty_fig(msg="No analyst ratings available")

    labels = [lbl  for k, lbl, _   in _BHS_KEYS if k in counts]
    values = [counts.get(k, 0) for k, _, _ in _BHS_KEYS if k in counts]
    colors = [c    for k, _,   c   in _BHS_KEYS if k in counts]

    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=values, textposition="outside",
        textfont={"color": COLORS["text"], "size": 12},
        hovertemplate="%{x}: %{y} analysts<extra></extra>",
    ))
    fig.update_layout(
        title={"text": f"{ticker} — Recommendation Distribution",
               "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        xaxis={"gridcolor": "transparent", "linecolor": COLORS["border"]},
        yaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"],
               "title": "# Analysts"},
        height=260,
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_money(v: Any, big: bool = False) -> str:
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if big:
        if abs(v) >= 1e12: return f"${v / 1e12:.2f}T"
        if abs(v) >= 1e9:  return f"${v / 1e9:.2f}B"
        if abs(v) >= 1e6:  return f"${v / 1e6:.1f}M"
    return f"${v:,.2f}"


def _fmt_pct(v: Any) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        return f"{float(v):+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _first_row(df: pd.DataFrame) -> dict[str, Any]:
    """First row of df as a plain dict, or {} if df is empty."""
    if df is None or df.empty:
        return {}
    return df.iloc[0].to_dict()


def _implied_pct(target: Any, current: Any) -> str:
    try:
        t = float(target); c = float(current)
        if c == 0:
            return ""
        return f" ({(t - c) / c * 100:+.1f}%)"
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 3 — Analysts",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart the server.",
            ),
            className="tab-content",
        )

    ts = TABLE_STYLES()

    # Per-ticker grades table — color the action column by sentiment.
    grades_ts = TABLE_STYLES()
    grades_base = grades_ts.pop("style_data_conditional", [])
    grades_ts["style_data_conditional"] = grades_base + [
        {"if": {"filter_query": '{action} contains "upgrad"', "column_id": "action"},
         "color": COLORS["good"], "fontWeight": "600"},
        {"if": {"filter_query": '{action} contains "downgrad"', "column_id": "action"},
         "color": COLORS["bad"], "fontWeight": "600"},
    ]

    return html.Div([
        # Triggers the market-wide grades news fetch on first render.
        dcc.Interval(id="sp3-init", interval=400, max_intervals=1),

        section_header(
            "Sprint 3 — Analysts",
            "What Wall Street thinks: price targets, recommendation distribution, "
            "recent rating actions, and forward estimates.",
        ),

        # ── Toolbar ──────────────────────────────────────────────────────
        html.Div([
            html.Label("Ticker:",
                       style={"color": COLORS["text_dim"], "fontSize": "12px",
                              "whiteSpace": "nowrap"}),
            text_input("sp3-ticker", value="AAPL", width="120px"),
            btn("Fetch", "sp3-fetch-btn", primary=True),
        ], className="toolbar-row"),

        # ── Price target stat cards ──────────────────────────────────────
        subsection_title("Price Targets"),
        html.Div([
            html.Div([
                html.Div("Current",   className="stat-label"),
                html.Div("—", id="sp3-stat-current",   className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Consensus", className="stat-label"),
                html.Div("—", id="sp3-stat-consensus", className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Median",    className="stat-label"),
                html.Div("—", id="sp3-stat-median",    className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("High",      className="stat-label"),
                html.Div("—", id="sp3-stat-high",      className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Low",       className="stat-label"),
                html.Div("—", id="sp3-stat-low",       className="stat-value"),
            ], className="stat-card"),
        ], className="stats-row"),

        # ── Recommendation distribution ──────────────────────────────────
        subsection_title("Recommendation Distribution"),
        html.Div([
            html.Div(
                dcc.Loading(
                    type="circle", color=COLORS["accent"],
                    children=dcc.Graph(
                        id="sp3-bhs-chart",
                        figure=_empty_fig(),
                        config={"displayModeBar": False},
                        style={"height": "260px"},
                    ),
                ),
                style={"flex": "2", "minWidth": "300px"},
            ),
            html.Div([
                html.Div([
                    html.Div("Total Analysts", className="stat-label"),
                    html.Div("—", id="sp3-stat-total", className="stat-value"),
                ], className="stat-card"),
                html.Div([
                    html.Div("Buy + Strong Buy", className="stat-label"),
                    html.Div("—", id="sp3-stat-buys", className="stat-value"),
                ], className="stat-card"),
                html.Div([
                    html.Div("Sell + Strong Sell", className="stat-label"),
                    html.Div("—", id="sp3-stat-sells", className="stat-value"),
                ], className="stat-card"),
            ], style={"flex": "1", "minWidth": "240px",
                      "display": "flex", "flexDirection": "column", "gap": "8px"}),
        ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap",
                  "marginBottom": "16px"}),

        # ── Recent rating actions (per ticker) ───────────────────────────
        subsection_title("Recent Rating Actions"),
        dcc.Loading(
            type="circle", color=COLORS["accent"],
            children=dash_table.DataTable(
                id="sp3-grades-table",
                columns=[
                    {"name": "Date",    "id": "date"},
                    {"name": "Firm",    "id": "firm"},
                    {"name": "Action",  "id": "action"},
                    {"name": "From",    "id": "previous"},
                    {"name": "To",      "id": "new_grade"},
                ],
                data=[],
                page_size=10,
                sort_action="native",
                **grades_ts,
            ),
        ),

        # ── Forward estimates (per ticker) ───────────────────────────────
        html.Details([
            html.Summary("Forward Analyst Estimates",
                         style={"cursor": "pointer", "color": COLORS["text_dim"],
                                "fontSize": "12px", "marginTop": "12px",
                                "marginBottom": "6px", "userSelect": "none"}),
            dash_table.DataTable(
                id="sp3-estimates-table",
                columns=[{"name": "—", "id": "placeholder"}],  # rebuilt by callback
                data=[],
                page_size=8,
                **ts,
            ),
        ], style={"marginBottom": "20px"}),

        status_label("sp3-status"),

        # ── Market-wide grades feed (independent of ticker) ──────────────
        section_header(
            "Market-Wide Grade Actions",
            "Latest upgrades / downgrades across all symbols — refreshes when you "
            "open the tab.",
        ),
        dcc.Loading(
            type="circle", color=COLORS["accent"],
            children=dash_table.DataTable(
                id="sp3-market-grades",
                columns=[
                    {"name": "Date",    "id": "date"},
                    {"name": "Symbol",  "id": "symbol"},
                    {"name": "Firm",    "id": "firm"},
                    {"name": "Action",  "id": "action"},
                    {"name": "From",    "id": "previous"},
                    {"name": "To",      "id": "new_grade"},
                ],
                data=[],
                page_size=20,
                sort_action="native",
                **grades_ts,
            ),
        ),
        status_label("sp3-market-status"),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    # ── Per-ticker fetch ─────────────────────────────────────────────────
    @app.callback(
        Output("sp3-stat-current",    "children"),
        Output("sp3-stat-consensus",  "children"),
        Output("sp3-stat-median",     "children"),
        Output("sp3-stat-high",       "children"),
        Output("sp3-stat-low",        "children"),
        Output("sp3-stat-total",      "children"),
        Output("sp3-stat-buys",       "children"),
        Output("sp3-stat-sells",      "children"),
        Output("sp3-bhs-chart",       "figure"),
        Output("sp3-grades-table",    "data"),
        Output("sp3-estimates-table", "columns"),
        Output("sp3-estimates-table", "data"),
        Output("sp3-status",          "children"),
        Input("sp3-fetch-btn", "n_clicks"),
        State("sp3-ticker",    "value"),
        prevent_initial_call=True,
    )
    def fetch(n_clicks, ticker_val):
        from ada_research.core.fmp_client import FmpClient

        if not ticker_val or not ticker_val.strip():
            raise PreventUpdate

        ticker = ticker_val.strip().upper()
        try:
            client = FmpClient()
        except Exception as exc:
            log.exception("FMP client init failed")
            return _err_tuple(f"Error: {exc}")

        # Fetch in one batch — every call goes through `safe()` so a single
        # premium-gated endpoint can't take down the whole tab.
        try:
            quote_obj   = client.quote(ticker) or {}
            consensus   = client.price_target_consensus(ticker)
            grades_sum  = client.grades_summary(ticker)
            grades_df   = client.grades(ticker)
            estimates   = client.analyst_estimates(ticker, period="annual", limit=10)
        except Exception as exc:
            log.exception("FMP analyst fetch failed for %s", ticker)
            return _err_tuple(f"Error: {exc}")

        # ── Price targets ────────────────────────────────────────────────
        current = quote_obj.get("price")
        cons    = _first_row(consensus)

        current_str   = _fmt_money(current)
        consensus_str = _fmt_money(cons.get("targetConsensus")) + _implied_pct(cons.get("targetConsensus"), current)
        median_str    = _fmt_money(cons.get("targetMedian"))    + _implied_pct(cons.get("targetMedian"),    current)
        high_str      = _fmt_money(cons.get("targetHigh"))      + _implied_pct(cons.get("targetHigh"),      current)
        low_str       = _fmt_money(cons.get("targetLow"))       + _implied_pct(cons.get("targetLow"),       current)

        # ── BHS distribution ─────────────────────────────────────────────
        gs = _first_row(grades_sum)
        # Coerce missing/None to 0 so the chart still renders zeros.
        counts = {k: int(gs.get(k) or 0) for k, _, _ in _BHS_KEYS}
        total  = sum(counts.values())
        buys   = counts.get("strongBuy",  0) + counts.get("buy",  0)
        sells  = counts.get("strongSell", 0) + counts.get("sell", 0)

        bhs_fig = _bhs_chart(counts, ticker) if total > 0 else _empty_fig(
            msg="No analyst ratings available"
        )

        total_str = str(total) if total else "—"
        buys_str  = str(buys)  if total else "—"
        sells_str = str(sells) if total else "—"

        # ── Grade actions (per ticker) ──────────────────────────────────
        grades_rows = _format_grades(grades_df, include_symbol=False)

        # ── Forward estimates ────────────────────────────────────────────
        est_cols, est_rows = _format_estimates(estimates)

        status = (f"{ticker} loaded — {total} analysts, {len(grades_rows)} recent actions."
                  if total or grades_rows else
                  f"{ticker} loaded — limited analyst coverage available.")

        return (
            current_str, consensus_str, median_str, high_str, low_str,
            total_str, buys_str, sells_str,
            bhs_fig,
            grades_rows,
            est_cols, est_rows,
            status,
        )

    # ── Market-wide grade actions feed ───────────────────────────────────
    @app.callback(
        Output("sp3-market-grades", "data"),
        Output("sp3-market-status", "children"),
        Input("sp3-init", "n_intervals"),
        prevent_initial_call=False,
    )
    def fetch_market(_n):
        from ada_research.core.fmp_client import FmpClient

        try:
            client = FmpClient()
            df = client.grades_latest_news(limit=30)
        except Exception as exc:
            log.exception("FMP latest grades fetch failed")
            return [], f"Error loading market grades: {exc}"

        rows = _format_grades(df, include_symbol=True)
        return rows, f"{len(rows)} latest market actions." if rows else "No market actions returned."


# ---------------------------------------------------------------------------
# Row formatters (kept out of the callback for testability)
# ---------------------------------------------------------------------------

def _format_grades(df: pd.DataFrame, include_symbol: bool) -> list[dict]:
    """Format per-ticker or market-wide grades feed rows.

    Handles FMP's column-naming variation: `gradingCompany` vs `firm`,
    `publishedDate` vs `date`, `previousGrade` vs `priorGrade`, etc.
    """
    if df is None or df.empty:
        return []

    def _pick(row: pd.Series, *names: str) -> Any:
        for n in names:
            if n in row and pd.notna(row[n]):
                return row[n]
        return None

    rows: list[dict] = []
    for _, r in df.head(30).iterrows():
        date_val = _pick(r, "date", "publishedDate")
        if isinstance(date_val, str) and "T" in date_val:
            date_val = date_val.split("T")[0]

        row = {
            "date":       str(date_val) if date_val is not None else "—",
            "firm":       str(_pick(r, "gradingCompany", "firm")          or "—"),
            "action":     str(_pick(r, "action")                          or "—"),
            "previous":   str(_pick(r, "previousGrade", "priorGrade")     or "—"),
            "new_grade":  str(_pick(r, "newGrade", "currentGrade")        or "—"),
        }
        if include_symbol:
            row["symbol"] = str(_pick(r, "symbol") or "—")
        rows.append(row)
    return rows


def _format_estimates(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Build (columns, data) for the forward-estimates table.

    Returns whichever subset of `_ESTIMATE_DISPLAY_COLS` actually exists in
    the response, so the table degrades gracefully on free tier or when FMP
    renames a field.
    """
    if df is None or df.empty:
        return [{"name": "—", "id": "placeholder"}], []

    available = [(src, label) for src, label in _ESTIMATE_DISPLAY_COLS if src in df.columns]
    if not available:
        return [{"name": "—", "id": "placeholder"}], []

    cols = [{"name": label, "id": src} for src, label in available]
    rows: list[dict] = []
    for _, r in df.head(8).iterrows():
        row = {}
        for src, _ in available:
            v = r.get(src)
            if src == "date" and v is not None:
                v = str(v).split("T")[0] if "T" in str(v) else str(v)
            elif src.startswith("estimatedRevenue") and v is not None:
                v = _fmt_money(v, big=True)
            elif src.startswith("estimatedEps") and v is not None:
                try:
                    v = f"${float(v):.2f}"
                except (TypeError, ValueError):
                    v = "—"
            elif v is None or (isinstance(v, float) and v != v):
                v = "—"
            else:
                v = str(v)
            row[src] = v
        rows.append(row)
    return cols, rows


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def _err_tuple(msg: str) -> tuple:
    """Return a 13-element tuple matching the per-ticker callback signature."""
    return (
        "—", "—", "—", "—", "—",     # price target stats
        "—", "—", "—",                # bhs stats
        _empty_fig(msg="—"),
        [],                            # grades table
        [{"name": "—", "id": "placeholder"}], [],  # estimates cols + data
        msg,
    )
