"""Sprint 1: Market Performance Engine (Dash/Plotly UI).

Quote + 1-year price history + volatility / moving-average chart.
Adds a Plotly candlestick chart — richer than the original PyQt table-only view.

Requires FMP_API_KEY.
"""
from __future__ import annotations

import math

import dash
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import (
    btn,
    placeholder_panel,
    section_header,
    status_label,
    text_input,
)
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


def _dark_figure() -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["panel"],
        font={"color": COLORS["text"], "family": "Segoe UI, Inter, sans-serif"},
        margin={"l": 40, "r": 20, "t": 30, "b": 40},
        xaxis={
            "gridcolor": COLORS["border"],
            "linecolor": COLORS["border"],
            "tickcolor": COLORS["border"],
        },
        yaxis={
            "gridcolor": COLORS["border"],
            "linecolor": COLORS["border"],
            "tickcolor": COLORS["border"],
        },
    )
    return fig


def layout() -> html.Div:
    if not config.has_fmp_key():
        return html.Div(
            placeholder_panel(
                "Sprint 1 — Market Performance",
                "FMP_API_KEY not set. Get a free key at "
                "site.financialmodelingprep.com and add it to .env, "
                "then restart the server.",
            ),
            className="tab-content",
        )

    ts = TABLE_STYLES()

    return html.Div([
        section_header("Sprint 1 — Market Performance"),

        # ── Toolbar ──────────────────────────────────────────────────────
        html.Div([
            html.Label("Ticker:", style={"color": COLORS["text_dim"],
                                         "fontSize": "12px", "whiteSpace": "nowrap"}),
            text_input("sp1-ticker", value="AAPL", width="120px"),
            btn("Fetch", "sp1-fetch-btn", primary=True),
        ], className="toolbar-row"),

        # ── Stat cards ───────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Price",              className="stat-label"),
                html.Div("—", id="sp1-stat-price",  className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Market Cap",         className="stat-label"),
                html.Div("—", id="sp1-stat-mcap",   className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Ann. Volatility",    className="stat-label"),
                html.Div("—", id="sp1-stat-vol",    className="stat-value"),
            ], className="stat-card"),
            html.Div([
                html.Div("Trend vs MAs",       className="stat-label"),
                html.Div("—", id="sp1-stat-trend",  className="stat-value"),
            ], className="stat-card"),
        ], className="stats-row"),

        # ── Price chart ──────────────────────────────────────────────────
        dcc.Loading(
            type="circle", color=COLORS["accent"],
            children=dcc.Graph(
                id="sp1-chart",
                figure=_dark_figure(),
                config={"displayModeBar": False},
                style={"height": "340px", "marginBottom": "12px"},
            ),
        ),

        # ── History table (last 50 sessions) ─────────────────────────────
        dash_table.DataTable(
            id="sp1-table",
            columns=[
                {"name": "Date",   "id": "date"},
                {"name": "Open",   "id": "open"},
                {"name": "High",   "id": "high"},
                {"name": "Low",    "id": "low"},
                {"name": "Close",  "id": "close"},
                {"name": "Volume", "id": "volume"},
            ],
            data=[],
            page_size=15,
            **ts,
        ),

        status_label("sp1-status"),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fmp_key():
        return

    @app.callback(
        Output("sp1-stat-price",  "children"),
        Output("sp1-stat-mcap",   "children"),
        Output("sp1-stat-vol",    "children"),
        Output("sp1-stat-trend",  "children"),
        Output("sp1-stat-trend",  "style"),
        Output("sp1-chart",       "figure"),
        Output("sp1-table",       "data"),
        Output("sp1-status",      "children"),
        Input("sp1-fetch-btn",  "n_clicks"),
        State("sp1-ticker",     "value"),
        prevent_initial_call=True,
    )
    def fetch(n_clicks, ticker_val):
        from ada_research.core.fmp_client import FmpClient

        if not ticker_val or not ticker_val.strip():
            raise PreventUpdate

        ticker = ticker_val.strip().upper()
        try:
            client = FmpClient()
            quote   = client.quote(ticker)
            history = client.historical_prices(ticker, periods=252)
        except Exception as exc:
            log.exception("FMP fetch failed")
            return ("—", "—", "—", "Error", {}, _dark_figure(), [], f"Error: {exc}")

        # ── Stat cards ────────────────────────────────────────────────────
        price_str = "—"
        mcap_str  = "—"
        if quote:
            price = quote.get("price")
            mcap  = quote.get("marketCap")
            price_str = f"${price:,.2f}" if price else "—"
            mcap_str  = _fmt_marketcap(mcap)

        vol_str   = "—"
        trend_str = "—"
        trend_style = {"color": COLORS["text"]}

        if not history.empty:
            h = history.copy()
            h["return"] = h["close"].pct_change()
            vol = h["return"].std() * math.sqrt(252)
            vol_str = f"{vol * 100:.1f}%" if math.isfinite(vol) else "—"

            ma50  = h["close"].rolling(50).mean().iloc[-1]
            ma200 = h["close"].rolling(200).mean().iloc[-1]
            close = h["close"].iloc[-1]

            parts = []
            if close > ma50:
                parts.append("> 50D")
            if close > ma200:
                parts.append("> 200D")
            if not parts:
                parts.append("Below MAs")
                trend_style = {"color": COLORS["bad"]}
            elif len(parts) == 2:
                trend_style = {"color": COLORS["good"]}
            else:
                trend_style = {"color": COLORS["warn"]}
            trend_str = " / ".join(parts)

        # ── Candlestick chart ─────────────────────────────────────────────
        fig = _dark_figure()
        if not history.empty:
            h_plot = history.sort_values("date")
            dates  = h_plot["date"].astype(str).tolist()

            fig.add_trace(go.Candlestick(
                x=dates,
                open=h_plot["open"],
                high=h_plot["high"],
                low=h_plot["low"],
                close=h_plot["close"],
                name=ticker,
                increasing_line_color=COLORS["good"],
                decreasing_line_color=COLORS["bad"],
            ))

            # MA overlays
            if len(h_plot) >= 50:
                ma50_series = h_plot["close"].rolling(50).mean()
                fig.add_trace(go.Scatter(
                    x=dates, y=ma50_series,
                    mode="lines",
                    name="50D MA",
                    line={"color": COLORS["accent"], "width": 1},
                ))
            if len(h_plot) >= 200:
                ma200_series = h_plot["close"].rolling(200).mean()
                fig.add_trace(go.Scatter(
                    x=dates, y=ma200_series,
                    mode="lines",
                    name="200D MA",
                    line={"color": COLORS["warn"], "width": 1, "dash": "dot"},
                ))

            fig.update_layout(
                title={"text": f"{ticker} — 1 Year", "font": {"size": 14}},
                xaxis_rangeslider_visible=False,
                legend={"bgcolor": COLORS["panel"],
                        "bordercolor": COLORS["border"], "borderwidth": 1},
            )

        # ── History table (last 50 rows, newest first) ────────────────────
        table_data = []
        if not history.empty:
            tail = history.sort_values("date", ascending=False).head(50)
            for _, row in tail.iterrows():
                table_data.append({
                    "date":   row["date"].strftime("%Y-%m-%d"),
                    "open":   f"{row['open']:.2f}"   if row.get("open")   is not None else "—",
                    "high":   f"{row['high']:.2f}"   if row.get("high")   is not None else "—",
                    "low":    f"{row['low']:.2f}"    if row.get("low")    is not None else "—",
                    "close":  f"{row['close']:.2f}"  if row.get("close")  is not None else "—",
                    "volume": f"{row['volume']:,.0f}" if row.get("volume") is not None else "—",
                })

        return (
            price_str, mcap_str, vol_str,
            trend_str, trend_style,
            fig, table_data, f"{ticker} loaded.",
        )


def _fmt_marketcap(v) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"
