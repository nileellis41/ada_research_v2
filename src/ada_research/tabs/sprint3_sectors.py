"""Sprint 3: Stock vs Sector (Dash/Plotly UI).

Compare a single stock's behaviour to the sector it belongs to. The user
types a ticker, the tab auto-detects the parent sector via the FMP profile
endpoint, then renders side-by-side performance, valuation, and volatility
metrics.

Data flow
---------
  /profile?symbol=                 → resolve ticker → sector
  /quote?symbol=                   → current price + P/E + change today
  /historical-price-eod/full       → daily closes for the stock
  /sector-performance-snapshot     → sector's avg change today
  /historical-sector-performance   → daily avg change for the sector
  /sector-pe-snapshot              → sector P/E today
  /historical-sector-pe            → sector P/E history (period change)

Layout
------
Top  — Toolbar
  • Ticker input
  • Sector dropdown (auto-populated after Fetch; user can override)
  • Lookback selector
  • Fetch button

Stat row (3 columns, 3 rows of cards)
  Performance:    Today       — stock vs sector vs spread
  Valuation:      Current P/E — stock vs sector vs premium/discount %
  Risk:           Period vol  — stock vs sector vs ratio

Charts
  • Cumulative return: stock vs sector, both rebased to 100
  • Relative strength: stock_cum − sector_cum (positive = outperforming)
  • P/E history: sector trend with the stock's current P/E as a marker line

Bottom
  • Side-by-side summary table

Requires FMP_API_KEY.

Note on the FMP client
----------------------
This tab needs `FmpClient.profile(symbol)` for sector auto-detect. If your
client doesn't have it yet, add this method (under the Sprint 1 section):

    def profile(self, symbol: str) -> dict | None:
        data = self.safe("/profile", symbol=symbol)
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None

The tab degrades gracefully if `profile()` is missing — it just falls back
to manual sector selection.
"""
from __future__ import annotations

import math
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


# FMP's canonical sector list (matches /sector-performance-snapshot)
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

_PERIOD_OPTIONS = [
    {"label": "30 days",  "value": 30},
    {"label": "60 days",  "value": 60},
    {"label": "90 days",  "value": 90},
    {"label": "180 days", "value": 180},
    {"label": "365 days", "value": 365},
]


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _empty_fig(height: int = 300, msg: str = "Pick a ticker and Fetch.") -> go.Figure:
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


def _dual_line(stock_x, stock_y, sector_x, sector_y,
               ticker: str, sector: str, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=stock_x, y=stock_y,
        mode="lines", name=ticker,
        line={"color": COLORS["accent"], "width": 2.2},
        hovertemplate=f"{ticker}: %{{y:.2f}}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=sector_x, y=sector_y,
        mode="lines", name=sector,
        line={"color": COLORS["warn"], "width": 2, "dash": "dot"},
        hovertemplate=f"{sector}: %{{y:.2f}}<extra></extra>",
    ))
    fig.add_hline(y=100, line_color=COLORS["border"], line_width=1)
    fig.update_layout(
        title={"text": title, "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 50, "r": 20, "t": 36, "b": 36},
        xaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"]},
        yaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"],
               "title": "Indexed (start = 100)"},
        legend={"bgcolor": COLORS["panel"], "bordercolor": COLORS["border"],
                "orientation": "h",
                "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        hovermode="x unified",
        height=320,
    )
    return fig


def _relative_strength_fig(dates, rs_values, ticker: str, sector: str) -> go.Figure:
    """Stock cumulative − sector cumulative. Filled to zero for clarity."""
    fig = go.Figure(go.Scatter(
        x=dates, y=rs_values,
        mode="lines",
        line={"color": COLORS["accent"], "width": 2},
        fill="tozeroy",
        fillcolor="rgba(91, 155, 213, 0.15)",
        hovertemplate="%{x|%Y-%m-%d}: %{y:+.2f}<extra></extra>",
        name="Spread",
    ))
    fig.add_hline(y=0, line_color=COLORS["border"], line_width=1)
    fig.update_layout(
        title={"text": f"Relative Strength — {ticker} vs {sector}",
               "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 50, "r": 20, "t": 36, "b": 36},
        xaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"]},
        yaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"],
               "title": "Cumulative spread (pp)"},
        height=260,
        hovermode="x unified",
    )
    return fig


def _pe_compare_fig(dates, sector_pe, stock_pe: float | None,
                    ticker: str, sector: str) -> go.Figure:
    """Sector P/E line with the stock's current P/E as a horizontal marker."""
    fig = go.Figure()
    if dates is not None and sector_pe is not None and len(dates):
        fig.add_trace(go.Scatter(
            x=dates, y=sector_pe,
            mode="lines", name=f"{sector} P/E",
            line={"color": COLORS["warn"], "width": 2},
            hovertemplate=f"{sector}: %{{y:.2f}}x<extra></extra>",
        ))
    if stock_pe is not None and stock_pe == stock_pe:  # not NaN
        fig.add_hline(
            y=stock_pe,
            line_color=COLORS["accent"],
            line_width=2,
            line_dash="dash",
            annotation={"text": f"{ticker} P/E: {stock_pe:.1f}x",
                        "font": {"color": COLORS["accent"], "size": 11}},
            annotation_position="top right",
        )
    if not fig.data:
        return _empty_fig(height=260, msg="No valuation data")

    fig.update_layout(
        title={"text": f"Valuation — {ticker} vs {sector}",
               "font": {"size": 13, "color": COLORS["text"]}},
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif", "size": 12},
        margin={"l": 50, "r": 20, "t": 36, "b": 36},
        xaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"]},
        yaxis={"gridcolor": COLORS["border"], "linecolor": COLORS["border"],
               "title": "P/E (x)"},
        height=260,
        hovermode="x unified",
        showlegend=True,
        legend={"bgcolor": COLORS["panel"], "bordercolor": COLORS["border"]},
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


def _fmt_num(v: Any, decimals: int = 2, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        return f"{float(v):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _tone(v: Any) -> dict:
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
# Layout
# ---------------------------------------------------------------------------

def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 3 — Stock vs Sector",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart the server.",
            ),
            className="tab-content",
        )

    sector_opts = [{"label": s, "value": s} for s in _SECTORS]

    ts = TABLE_STYLES()

    return html.Div([
        section_header(
            "Sprint 3 — Stock vs Sector",
            "Type a ticker; we'll resolve its sector automatically and compare "
            "performance, valuation, and volatility.",
        ),

        # ── Toolbar ──────────────────────────────────────────────────────
        html.Div([
            html.Label("Ticker:", style={"color": COLORS["text_dim"],
                                          "fontSize": "12px", "whiteSpace": "nowrap"}),
            text_input("sp3-ticker", value="AAPL", width="120px"),
            html.Label("Sector:", style={"color": COLORS["text_dim"],
                                          "fontSize": "12px", "whiteSpace": "nowrap"}),
            dcc.Dropdown(
                id="sp3-sector",
                options=sector_opts,
                value=None,
                placeholder="Auto-detect after Fetch",
                clearable=True,
                style={"minWidth": "200px",
                       "backgroundColor": COLORS["panel"],
                       "color": COLORS["text"],
                       "border": f"1px solid {COLORS['border']}",
                       "borderRadius": "4px",
                       "fontSize": "13px"},
            ),
            html.Label("Lookback:", style={"color": COLORS["text_dim"],
                                            "fontSize": "12px", "whiteSpace": "nowrap"}),
            dcc.Dropdown(
                id="sp3-period",
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
            btn("Fetch", "sp3-fetch-btn", primary=True),
        ], className="toolbar-row"),

        # ── Performance row ──────────────────────────────────────────────
        subsection_title("Performance — Today"),
        html.Div([
            html.Div([
                html.Div("Stock today",  className="stat-label"),
                html.Div("—", id="sp3-perf-stock",  className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Sector today", className="stat-label"),
                html.Div("—", id="sp3-perf-sector", className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Spread (pp)",  className="stat-label"),
                html.Div("—", id="sp3-perf-spread", className="stat-value"),
            ], className="stat-card"),
        ], className="stats-row"),

        # ── Valuation row ────────────────────────────────────────────────
        subsection_title("Valuation — P/E"),
        html.Div([
            html.Div([
                html.Div("Stock P/E",     className="stat-label"),
                html.Div("—", id="sp3-pe-stock",  className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Sector P/E",    className="stat-label"),
                html.Div("—", id="sp3-pe-sector", className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Premium/Discount", className="stat-label"),
                html.Div("—", id="sp3-pe-prem",  className="stat-value"),
            ], className="stat-card"),
        ], className="stats-row"),

        # ── Risk row ─────────────────────────────────────────────────────
        subsection_title("Risk — Period Volatility"),
        html.Div([
            html.Div([
                html.Div("Stock vol (ann.)", className="stat-label"),
                html.Div("—", id="sp3-vol-stock", className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Sector vol (ann.)", className="stat-label"),
                html.Div("—", id="sp3-vol-sector", className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Vol ratio", className="stat-label"),
                html.Div("—", id="sp3-vol-ratio",  className="stat-value"),
            ], className="stat-card"),
        ], className="stats-row"),

        # ── Cumulative + relative strength ───────────────────────────────
        dcc.Loading(type="circle", color=COLORS["accent"],
                    children=dcc.Graph(
                        id="sp3-cum-chart",
                        figure=_empty_fig(height=320),
                        config={"displayModeBar": False},
                    )),
        dcc.Loading(type="circle", color=COLORS["accent"],
                    children=dcc.Graph(
                        id="sp3-rs-chart",
                        figure=_empty_fig(height=260),
                        config={"displayModeBar": False},
                    )),

        # ── Valuation chart ──────────────────────────────────────────────
        dcc.Loading(type="circle", color=COLORS["accent"],
                    children=dcc.Graph(
                        id="sp3-pe-chart",
                        figure=_empty_fig(height=260),
                        config={"displayModeBar": False},
                    )),

        # ── Summary table ────────────────────────────────────────────────
        html.Details([
            html.Summary("Side-by-side summary",
                         style={"cursor": "pointer", "color": COLORS["text_dim"],
                                "fontSize": "12px", "marginTop": "12px",
                                "marginBottom": "6px", "userSelect": "none"}),
            dash_table.DataTable(
                id="sp3-summary-table",
                columns=[
                    {"name": "Metric", "id": "metric"},
                    {"name": "Stock",  "id": "stock"},
                    {"name": "Sector", "id": "sector"},
                    {"name": "Diff",   "id": "diff"},
                ],
                data=[],
                **ts,
            ),
        ], style={"marginBottom": "20px"}),

        status_label("sp3-status"),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    @app.callback(
        Output("sp3-sector",        "value"),     # auto-fill sector
        Output("sp3-perf-stock",    "children"),
        Output("sp3-perf-stock",    "style"),
        Output("sp3-perf-sector",   "children"),
        Output("sp3-perf-sector",   "style"),
        Output("sp3-perf-spread",   "children"),
        Output("sp3-perf-spread",   "style"),
        Output("sp3-pe-stock",      "children"),
        Output("sp3-pe-sector",     "children"),
        Output("sp3-pe-prem",       "children"),
        Output("sp3-pe-prem",       "style"),
        Output("sp3-vol-stock",     "children"),
        Output("sp3-vol-sector",    "children"),
        Output("sp3-vol-ratio",     "children"),
        Output("sp3-cum-chart",     "figure"),
        Output("sp3-rs-chart",      "figure"),
        Output("sp3-pe-chart",      "figure"),
        Output("sp3-summary-table", "data"),
        Output("sp3-status",        "children"),
        Input("sp3-fetch-btn", "n_clicks"),
        State("sp3-ticker",    "value"),
        State("sp3-sector",    "value"),
        State("sp3-period",    "value"),
        prevent_initial_call=True,
    )
    def fetch(n_clicks, ticker_val, sector_val, period):
        from ada_research.core.fmp_client import FmpClient

        if not ticker_val or not ticker_val.strip():
            raise PreventUpdate

        ticker = ticker_val.strip().upper()
        days   = int(period or 90)

        try:
            c = FmpClient()
        except Exception as exc:
            log.exception("FMP client init failed")
            return _err_tuple(sector_val, f"Error: {exc}")

        # ── Resolve sector ──────────────────────────────────────────────
        # Priority: explicit user override > /profile lookup > unchanged.
        resolved_sector = sector_val
        if not resolved_sector:
            resolved_sector = _resolve_sector(c, ticker)
            if not resolved_sector:
                return _err_tuple(
                    sector_val,
                    f"Couldn't resolve sector for {ticker}. "
                    "Pick a sector manually and re-fetch.",
                )

        # ── Pull data in one batch ──────────────────────────────────────
        try:
            quote_obj  = c.quote(ticker) or {}
            stock_hist = c.historical_prices(ticker, periods=days + 5)
            sec_snap   = c.sector_snapshot()
            sec_hist   = c.historical_sector(resolved_sector, days=days)
            sec_pe_now = c.sector_pe()
            sec_pe_hi  = c.historical_sector_pe(resolved_sector, days=days)
        except Exception as exc:
            log.exception("FMP stock-vs-sector fetch failed")
            return _err_tuple(resolved_sector, f"Error: {exc}")

        # ── Today's performance ─────────────────────────────────────────
        stock_today  = quote_obj.get("changesPercentage")
        sector_today = _sector_today(sec_snap, resolved_sector)
        spread_today = (
            float(stock_today) - float(sector_today)
            if stock_today is not None and sector_today is not None
            else None
        )

        # ── Cumulative-return series (rebased to 100) ───────────────────
        stock_cum_dates, stock_cum_vals, stock_vol = _stock_cumulative(stock_hist, days)
        sector_cum_dates, sector_cum_vals, sector_vol = _sector_cumulative(sec_hist)

        # Cumulative chart
        cum_fig = _empty_fig(height=320, msg="No history for this period")
        if stock_cum_dates and sector_cum_dates:
            cum_fig = _dual_line(
                stock_cum_dates,  stock_cum_vals,
                sector_cum_dates, sector_cum_vals,
                ticker, resolved_sector,
                f"Cumulative Return — {ticker} vs {resolved_sector} ({days}d)",
            )

        # Relative strength: aligned by date
        rs_fig = _empty_fig(height=260, msg="No overlap")
        rs_dates, rs_vals = _align_relative(stock_cum_dates, stock_cum_vals,
                                             sector_cum_dates, sector_cum_vals)
        if rs_dates:
            rs_fig = _relative_strength_fig(rs_dates, rs_vals, ticker, resolved_sector)

        # ── Valuation ───────────────────────────────────────────────────
        stock_pe = quote_obj.get("pe") or quote_obj.get("priceEarningsRatio")
        sector_pe_curr = _sector_pe_now(sec_pe_now, resolved_sector)
        premium_pct: float | None = None
        if (stock_pe is not None and sector_pe_curr is not None
                and sector_pe_curr != 0):
            try:
                premium_pct = (float(stock_pe) - float(sector_pe_curr)) / float(sector_pe_curr) * 100
            except (TypeError, ValueError):
                premium_pct = None

        pe_fig = _build_pe_fig(sec_pe_hi, stock_pe, ticker, resolved_sector)

        # ── Volatility ──────────────────────────────────────────────────
        vol_ratio: float | None = None
        if (stock_vol is not None and sector_vol is not None
                and sector_vol > 0):
            vol_ratio = stock_vol / sector_vol

        # ── Format outputs ──────────────────────────────────────────────
        perf_stock_str  = _fmt_pct(stock_today)
        perf_sector_str = _fmt_pct(sector_today)
        spread_str      = _fmt_num(spread_today, decimals=2, suffix=" pp") if spread_today is not None else "—"
        pe_stock_str    = _fmt_num(stock_pe,       decimals=2, suffix="x")
        pe_sector_str   = _fmt_num(sector_pe_curr, decimals=2, suffix="x")
        pe_prem_str     = _fmt_pct(premium_pct)
        vol_stock_str   = _fmt_pct(stock_vol  * 100, signed=False) if stock_vol  is not None else "—"
        vol_sector_str  = _fmt_pct(sector_vol * 100, signed=False) if sector_vol is not None else "—"
        vol_ratio_str   = _fmt_num(vol_ratio, decimals=2, suffix="x") if vol_ratio is not None else "—"

        # ── Summary table ───────────────────────────────────────────────
        summary = _summary_table(
            ticker, resolved_sector,
            stock_today, sector_today, spread_today,
            stock_pe, sector_pe_curr, premium_pct,
            stock_vol, sector_vol, vol_ratio,
            stock_cum_vals, sector_cum_vals,
        )

        status = (
            f"{ticker} ({resolved_sector}) — "
            f"{len(stock_cum_vals) if stock_cum_vals else 0} stock days, "
            f"{len(sector_cum_vals) if sector_cum_vals else 0} sector days."
        )

        return (
            resolved_sector,
            perf_stock_str,  _tone(stock_today),
            perf_sector_str, _tone(sector_today),
            spread_str,      _tone(spread_today),
            pe_stock_str, pe_sector_str,
            pe_prem_str,  _tone(-premium_pct if premium_pct is not None else None),
            # ^ premium tone: positive premium = "expensive" → tinted red, discount → green
            vol_stock_str, vol_sector_str, vol_ratio_str,
            cum_fig, rs_fig, pe_fig,
            summary,
            status,
        )


# ---------------------------------------------------------------------------
# Sector resolution
# ---------------------------------------------------------------------------

def _resolve_sector(client, ticker: str) -> str | None:
    """Resolve sector via FmpClient.profile() if available, else None.

    Falls back gracefully if the client doesn't have profile() yet — see
    the module docstring for the one-method patch.
    """
    profile_fn = getattr(client, "profile", None)
    if not callable(profile_fn):
        # No profile method on client — try /profile via raw safe call.
        try:
            data = client.safe("/profile", symbol=ticker)
        except Exception:
            return None
        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            return data.get("sector") or None
        return None

    try:
        prof = profile_fn(ticker)
    except Exception as exc:
        log.warning("profile lookup failed for %s: %s", ticker, exc)
        return None
    if isinstance(prof, dict):
        return prof.get("sector") or None
    return None


# ---------------------------------------------------------------------------
# Series builders
# ---------------------------------------------------------------------------

def _stock_cumulative(hist: pd.DataFrame, days: int
                      ) -> tuple[list, list, float | None]:
    """Stock daily closes → rebased cumulative + annualized vol."""
    if hist is None or hist.empty or "close" not in hist.columns:
        return [], [], None
    df = hist.copy()
    df["date"]  = pd.to_datetime(df["date"])
    df["close"] = _coerce_num(df["close"])
    df = df.dropna(subset=["close"]).sort_values("date").tail(days)
    if df.empty or len(df) < 2:
        return [], [], None
    base = df["close"].iloc[0]
    if base == 0 or base != base:
        return [], [], None
    cum = (df["close"] / base * 100.0).tolist()
    dates = df["date"].tolist()

    daily_ret = df["close"].pct_change().dropna()
    vol = float(daily_ret.std() * math.sqrt(252)) if len(daily_ret) >= 2 else None
    if vol is not None and not math.isfinite(vol):
        vol = None
    return dates, cum, vol


def _sector_cumulative(hist: pd.DataFrame) -> tuple[list, list, float | None]:
    """Sector daily averageChange (%) → rebased cumulative + annualized vol."""
    if hist is None or hist.empty or "averageChange" not in hist.columns:
        return [], [], None
    df = hist.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["averageChange"] = _coerce_num(df["averageChange"])
    df = df.dropna(subset=["averageChange"]).sort_values("date")
    if df.empty:
        return [], [], None

    rets = df["averageChange"] / 100.0
    cum = (1.0 + rets).cumprod() * 100.0
    dates = df["date"].tolist()

    vol = float(rets.std() * math.sqrt(252)) if len(rets) >= 2 else None
    if vol is not None and not math.isfinite(vol):
        vol = None
    return dates, cum.tolist(), vol


def _align_relative(s_dates, s_vals, x_dates, x_vals
                    ) -> tuple[list, list]:
    """Inner-join stock and sector cumulatives by date; return spread series."""
    if not s_dates or not x_dates:
        return [], []
    s = pd.Series(s_vals, index=pd.to_datetime(s_dates))
    x = pd.Series(x_vals, index=pd.to_datetime(x_dates))
    aligned = pd.concat([s, x], axis=1, join="inner").dropna()
    if aligned.empty:
        return [], []
    spread = (aligned.iloc[:, 0] - aligned.iloc[:, 1])
    return aligned.index.tolist(), spread.tolist()


def _sector_today(snap: pd.DataFrame, sector: str) -> Any:
    if snap is None or snap.empty or "sector" not in snap.columns:
        return None
    m = snap[snap["sector"].astype(str).str.lower() == sector.lower()]
    if m.empty or "averageChange" not in m.columns:
        return None
    val = m.iloc[0]["averageChange"]
    try:
        f = float(val)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _sector_pe_now(snap: pd.DataFrame, sector: str) -> float | None:
    if snap is None or snap.empty or "sector" not in snap.columns or "pe" not in snap.columns:
        return None
    m = snap[snap["sector"].astype(str).str.lower() == sector.lower()]
    if m.empty:
        return None
    try:
        f = float(m.iloc[0]["pe"])
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _build_pe_fig(hist_pe: pd.DataFrame, stock_pe: Any,
                  ticker: str, sector: str) -> go.Figure:
    if hist_pe is None or hist_pe.empty or "pe" not in hist_pe.columns:
        return _pe_compare_fig([], [], _safe_float(stock_pe), ticker, sector)
    df = hist_pe.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["pe"]   = _coerce_num(df["pe"])
    df = df.dropna(subset=["pe"]).sort_values("date")
    return _pe_compare_fig(df["date"].tolist(), df["pe"].tolist(),
                           _safe_float(stock_pe), ticker, sector)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _summary_table(ticker, sector,
                   stock_today, sector_today, spread_today,
                   stock_pe, sector_pe_curr, premium_pct,
                   stock_vol, sector_vol, vol_ratio,
                   stock_cum_vals, sector_cum_vals) -> list[dict]:
    """Side-by-side metric table."""

    def _diff_pct(a, b):
        try:
            return f"{float(a) - float(b):+.2f} pp"
        except (TypeError, ValueError):
            return "—"

    # Period total return = last cum value - 100
    stock_total  = (stock_cum_vals[-1]  - 100.0) if stock_cum_vals  else None
    sector_total = (sector_cum_vals[-1] - 100.0) if sector_cum_vals else None
    period_diff = (
        f"{stock_total - sector_total:+.2f} pp"
        if stock_total is not None and sector_total is not None else "—"
    )

    return [
        {"metric": "Today % change",
         "stock":  _fmt_pct(stock_today),
         "sector": _fmt_pct(sector_today),
         "diff":   _diff_pct(stock_today, sector_today)},
        {"metric": "Period total return",
         "stock":  _fmt_pct(stock_total),
         "sector": _fmt_pct(sector_total),
         "diff":   period_diff},
        {"metric": "Annualized volatility",
         "stock":  _fmt_pct(stock_vol  * 100, signed=False) if stock_vol  is not None else "—",
         "sector": _fmt_pct(sector_vol * 100, signed=False) if sector_vol is not None else "—",
         "diff":   _fmt_num(vol_ratio, decimals=2, suffix="x") if vol_ratio is not None else "—"},
        {"metric": "P/E (current)",
         "stock":  _fmt_num(stock_pe,       decimals=2, suffix="x"),
         "sector": _fmt_num(sector_pe_curr, decimals=2, suffix="x"),
         "diff":   _fmt_pct(premium_pct)},
    ]


# ---------------------------------------------------------------------------
# Error fallback
# ---------------------------------------------------------------------------

def _err_tuple(sector_val: str | None, msg: str) -> tuple:
    """Match the 19-element callback signature on error paths."""
    empty = _empty_fig()
    rs    = _empty_fig(height=260)
    return (
        sector_val,
        "—", {}, "—", {}, "—", {},          # perf
        "—", "—", "—", {},                   # valuation
        "—", "—", "—",                        # risk
        empty, rs, _empty_fig(height=260),    # charts
        [],                                    # summary
        msg,
    )
