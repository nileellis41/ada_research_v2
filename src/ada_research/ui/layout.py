"""Main Dash layout: header + six-tab workbench."""
from __future__ import annotations

from dash import dcc, html

from ada_research.ui.theme import COLORS


def create_layout() -> html.Div:
    from ada_research.tabs import (
        stage1_sentiment,
        stage2_macro,
        sprint1_market,
        sprint3_sectors,
        sprint4_analysts,
        sprint2_screener,
    )

    _TAB_STYLE = {
        "className": "custom-tab",
        "selected_className": "custom-tab--selected",
    }

    return html.Div([
        # Global store: Stage 1 LLM analyses available across all tabs
        dcc.Store(id="ada-llm-store", storage_type="session"),

        # ── App header ────────────────────────────────────────────────────
        html.Div([
            html.Span(
                "Ada Research",
                style={"fontSize": "18px", "fontWeight": "600",
                       "color": COLORS["text"], "letterSpacing": "-0.3px"},
            ),
            html.Span(
                "Top-down financial research workbench",
                style={"fontSize": "12px", "color": COLORS["text_dim"]},
            ),
        ], className="app-header"),

        # ── Main tabs ─────────────────────────────────────────────────────
        dcc.Tabs(
            id="main-tabs",
            value="tab-s1",
            className="custom-tabs",
            children=[
                dcc.Tab(
                    label="Stage 1 · Sentiment",
                    value="tab-s1",
                    children=[stage1_sentiment.layout()],
                    **_TAB_STYLE,
                ),
                dcc.Tab(
                    label="Stage 2 · Macro",
                    value="tab-s2",
                    children=[stage2_macro.layout()],
                    **_TAB_STYLE,
                ),
                dcc.Tab(
                    label="Sprint 1 · Market",
                    value="tab-sp1",
                    children=[sprint1_market.layout()],
                    **_TAB_STYLE,
                ),
                dcc.Tab(
                    label="Sprint 2 · Screener",
                    value="tab-sp2",
                    children=[sprint2_screener.layout()],
                    **_TAB_STYLE,
                ),
                dcc.Tab(
                    label="Sprint 3 · Stock vs Sector",
                    value="tab-sp3",
                    children=[sprint3_sectors.layout()],
                    **_TAB_STYLE,
                ),
                dcc.Tab(
                    label="Sprint 4 · Analysts Analysis",
                    value="tab-sp4",
                    children=[sprint4_analysts.layout()],
                    **_TAB_STYLE,
                ),
          ],
        ),
    ], style={"backgroundColor": COLORS["bg"], "minHeight": "100vh"})
