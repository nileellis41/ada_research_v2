"""Stage 2: Macro Validation Dashboard (Dash/Plotly UI).

Pulls the curated FRED indicator catalog (~30 series across 6 categories),
shows latest values + 1-week changes + a quick regime read.

Requires FRED_API_KEY (free). Auto-loads on page open.
"""
from __future__ import annotations

from datetime import datetime

import dash
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import (
    btn,
    placeholder_panel,
    section_header,
    status_label,
)
from ada_research.ui.theme import COLORS, TABLE_STYLES
from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)

_REGIME_TAGS = ["curve", "liquidity", "risk", "growth", "inflation"]
_REGIME_LABELS = {
    "curve":     "Curve",
    "liquidity": "Liquidity",
    "risk":      "Risk",
    "growth":    "Growth",
    "inflation": "Inflation",
}

_REGIME_TONE = {
    "curve":      {"normal": "good", "flat": "warn", "inverted": "bad"},
    "liquidity":  {"easy": "good", "neutral": "warn", "tight": "bad"},
    "risk":       {"on": "good", "neutral": "warn", "off": "bad"},
    "growth":     {"expansion": "good", "slowing": "warn", "contraction": "bad"},
    "inflation":  {"cooling": "good", "tracking": "warn", "stable": "warn", "hot": "bad"},
}

_TONE_COLOR = {"good": COLORS["good"], "bad": COLORS["bad"],
               "warn": COLORS["warn"], "neutral": COLORS["text"]}


def _regime_color(tag: str, value: str) -> str:
    v = (value or "").lower()
    if v in ("n/a", "—", ""):
        return COLORS["text"]
    tone = _REGIME_TONE.get(tag, {}).get(v, "neutral")
    return _TONE_COLOR.get(tone, COLORS["text"])


def _indicator_table_cols():
    return [
        {"name": "Series",      "id": "series_id"},
        {"name": "Name",        "id": "name"},
        {"name": "Latest",      "id": "latest"},
        {"name": "1W Δ",        "id": "change_1w"},
        {"name": "As of",       "id": "as_of"},
        {"name": "Description", "id": "description"},
    ]


def _fmt_value(value, units: str) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if units == "%":
        return f"{v:.2f}%"
    if units == "% pts":
        return f"{v:+.2f} pts"
    if units in ("$/bbl", "$/MMBtu", "$/oz"):
        return f"${v:,.2f}"
    if units == "$M":
        return f"${v:,.0f}M"
    if units == "$B":
        return f"${v:,.0f}B"
    if units == "Index":
        return f"{v:,.2f}"
    if units == "Number":
        return f"{v:,.0f}"
    if units == "Thousands":
        return f"{v:,.0f}K"
    return f"{v:,.2f}"


def _fmt_change(change) -> str:
    if change is None:
        return "—"
    try:
        return f"{float(change):+.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_date(d) -> str:
    if d is None:
        return "—"
    try:
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(d)


def layout() -> html.Div:
    if not config.has_fred_key():
        return html.Div(
            placeholder_panel(
                "Stage 2 — Macro Validation",
                "FRED_API_KEY not set. Get a free key at fred.stlouisfed.org and "
                "add it to your .env file, then restart the server.",
            ),
            className="tab-content",
        )

    ts = TABLE_STYLES()

    # Build per-category sub-tabs (initially empty tables; filled on load)
    from ada_research.core.fred_client import CATEGORIES, INDICATORS, indicators_in

    sub_tabs = []
    for cat in CATEGORIES:
        inds = indicators_in(cat)
        placeholder_rows = [
            {
                "series_id":   ind.series_id,
                "name":        ind.name,
                "latest":      "—",
                "change_1w":   "—",
                "as_of":       "—",
                "description": ind.description or "",
            }
            for ind in inds
        ]
        sub_tabs.append(
            dcc.Tab(
                label=cat,
                value=cat,
                className="sub-tab",
                selected_className="sub-tab--selected",
                children=dash_table.DataTable(
                    id=f"s2-table-{cat.replace(' ', '_')}",
                    columns=_indicator_table_cols(),
                    data=placeholder_rows,
                    **ts,
                    style_cell_conditional=[
                        {"if": {"column_id": "description"}, "minWidth": "200px"},
                    ],
                ),
            )
        )

    from ada_research.core.fred_client import SECTORS

    _val_cols = [
        {"name": "Indicator",  "id": "name"},
        {"name": "Latest",     "id": "latest"},
        {"name": "1W Δ",       "id": "change_1w"},
        {"name": "As of",      "id": "as_of"},
        {"name": "Reading",    "id": "reading"},
    ]
    val_ts = TABLE_STYLES()
    val_ts["style_data_conditional"] = val_ts["style_data_conditional"] + [
        {"if": {"filter_query": '{reading} = "Bullish signal"', "column_id": "reading"},
         "color": COLORS["good"], "fontWeight": "600"},
        {"if": {"filter_query": '{reading} = "Bearish signal"', "column_id": "reading"},
         "color": COLORS["bad"], "fontWeight": "600"},
    ]

    return html.Div([
        dcc.Store(id="s2-store"),
        dcc.Interval(id="s2-init", interval=300, max_intervals=1),

        section_header(
            "Stage 2 — Macro Validation",
            "~30 macro indicators across 6 categories. Latest values from FRED, "
            "with 1-week change and a quick regime read at the top.",
        ),

        # ── Regime row ────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div(lbl, className="regime-label"),
                html.Div("—", id=f"s2-regime-{tag}", className="regime-value"),
            ], className="regime-item")
            for tag, lbl in _REGIME_LABELS.items()
        ], className="regime-row", style={"marginBottom": "12px"}),

        # ── Toolbar ───────────────────────────────────────────────────────
        html.Div([
            btn("Refresh", "s2-refresh-btn", primary=True),
            status_label("s2-status"),
        ], className="toolbar-row"),

        # ── Category sub-tabs ─────────────────────────────────────────────
        dcc.Tabs(
            id="s2-category-tabs",
            value=CATEGORIES[0] if CATEGORIES else None,
            children=sub_tabs,
            className="sub-tabs",
        ),

        # ── Sector Macro Validation ───────────────────────────────────────
        html.Hr(style={"borderColor": COLORS["border"], "margin": "24px 0 16px"}),

        section_header(
            "Sector Macro Validation",
            "Pick one of the 11 GICS sectors to validate its LLM signal against "
            "live FRED macro indicators. Run Stage 1 first to populate the LLM signal.",
        ),

        html.Div([
            dcc.Dropdown(
                id="s2-sector-picker",
                options=[{"label": s, "value": s} for s in SECTORS],
                placeholder="Select a sector…",
                clearable=True,
                className="ada-select",
                style={
                    "width": "260px",
                    "backgroundColor": COLORS["panel"],
                    "color": COLORS["text"],
                    "border": f"1px solid {COLORS['border']}",
                    "borderRadius": "4px",
                    "fontSize": "13px",
                },
            ),
            status_label("s2-val-status"),
        ], className="toolbar-row"),

        # Signal comparison banner (filled by callback)
        html.Div(id="s2-val-banner", style={"marginBottom": "12px"}),

        # Indicator table (filled by callback)
        dcc.Loading(
            type="circle", color=COLORS["accent"],
            children=html.Div(id="s2-val-table-wrap"),
        ),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:
    if not config.has_fred_key():
        return

    from ada_research.core.fred_client import CATEGORIES, indicators_in

    # Build the list of DataTable output IDs (one per category)
    table_outputs = [
        Output(f"s2-table-{cat.replace(' ', '_')}", "data")
        for cat in CATEGORIES
    ]
    regime_outputs = [
        Output(f"s2-regime-{tag}", "children") for tag in _REGIME_TAGS
    ] + [
        Output(f"s2-regime-{tag}", "style") for tag in _REGIME_TAGS
    ]

    @app.callback(
        [
            Output("s2-status", "children"),
            *table_outputs,
            *regime_outputs,
        ],
        Input("s2-init",        "n_intervals"),
        Input("s2-refresh-btn", "n_clicks"),
        prevent_initial_call=False,
    )
    def load_macro(_n_init, _n_refresh):
        from ada_research.core.fred_client import (
            CATEGORIES,
            FredClient,
            indicators_in,
            regime_classification,
        )

        try:
            client = FredClient()
            df = client.snapshot()
            regime = regime_classification(df)
        except Exception as exc:
            log.exception("FRED fetch failed")
            n_cats = len(CATEGORIES)
            empty = [[] for _ in range(n_cats)]
            no_regime_vals = ["—"] * len(_REGIME_TAGS)
            no_regime_styles = [{}] * len(_REGIME_TAGS)
            return [f"Error: {exc}", *empty, *no_regime_vals, *no_regime_styles]

        # Build table data per category
        tables = []
        for cat in CATEGORIES:
            inds = indicators_in(cat)
            cat_df = df[df["category"] == cat] if "category" in df.columns else df.iloc[0:0]
            rows_by_id = {r["series_id"]: r for _, r in cat_df.iterrows()}
            rows = []
            for ind in inds:
                r = rows_by_id.get(ind.series_id, {})
                rows.append({
                    "series_id":   ind.series_id,
                    "name":        ind.name,
                    "latest":      _fmt_value(r.get("value"), ind.units),
                    "change_1w":   _fmt_change(r.get("change_1w")),
                    "as_of":       _fmt_date(r.get("as_of")),
                    "description": ind.description or "",
                })
            tables.append(rows)

        # Regime labels + colors
        regime_vals   = [regime.get(tag, "—").upper() for tag in _REGIME_TAGS]
        regime_styles = [
            {"color": _regime_color(tag, regime.get(tag, ""))}
            for tag in _REGIME_TAGS
        ]

        ts = datetime.now().strftime("%H:%M:%S")
        return [f"Updated at {ts}.", *tables, *regime_vals, *regime_styles]

    # ------------------------------------------------------------------
    # Sector macro validation callback
    # ------------------------------------------------------------------

    @app.callback(
        Output("s2-val-banner",     "children"),
        Output("s2-val-table-wrap", "children"),
        Output("s2-val-status",     "children"),
        Input("s2-sector-picker",   "value"),
        State("ada-llm-store",      "data"),
        prevent_initial_call=True,
    )
    def validate_sector(sector, llm_store):
        if not sector:
            raise PreventUpdate

        from ada_research.core.fred_client import (
            INDICATORS,
            SECTOR_MACRO_MAP,
            FredClient,
            sector_macro_signal,
        )

        profile = SECTOR_MACRO_MAP.get(sector, {})
        series_ids = set(profile.get("series", []))
        relevant_inds = [i for i in INDICATORS if i.series_id in series_ids]

        try:
            client = FredClient()
            snap = client.snapshot(indicators=relevant_inds)
        except Exception as exc:
            log.warning("FRED validation fetch failed: %s", exc)
            snap = __import__("pandas").DataFrame()

        result = sector_macro_signal(sector, snap)
        macro_signal  = result["signal"]
        macro_score   = result["score"]
        ind_rows      = result["indicator_rows"]
        description   = result["description"]
        bull_when     = result["bull_when"]
        bear_when     = result["bear_when"]

        # ── LLM signal for this sector ──────────────────────────────────
        llm_signal   = "—"
        llm_response = ""
        llm_score    = None
        if llm_store and llm_store.get("llm_available"):
            analyses = llm_store.get("llm_analyses", {})
            llm_entry = analyses.get(sector)
            if llm_entry and llm_entry.get("available"):
                llm_signal   = llm_entry["signal"].replace("_", " ")
                llm_response = llm_entry.get("response", "")
                llm_score    = llm_entry.get("score")

        # ── Verdict logic ───────────────────────────────────────────────
        llm_direction = (
            "bullish" if llm_signal in ("STRONG BUY", "BUY")
            else "bearish" if llm_signal in ("SELL", "STRONG SELL")
            else "neutral"
        )
        macro_direction = macro_signal.lower()  # "bullish" | "neutral" | "bearish"

        if llm_direction == "neutral" or macro_direction == "neutral":
            verdict_text  = "Inconclusive"
            verdict_sub   = "One or both signals are neutral — no clear alignment."
            verdict_color = COLORS["text_dim"]
        elif llm_direction == macro_direction:
            verdict_text  = f"Aligned · {macro_direction.capitalize()}"
            verdict_sub   = "LLM sentiment and macro indicators point in the same direction."
            verdict_color = COLORS["good"] if macro_direction == "bullish" else COLORS["bad"]
        else:
            verdict_text  = "Divergence"
            verdict_sub   = (
                f"LLM is {llm_direction} but macro indicators are {macro_direction}. "
                "Consider additional research before acting."
            )
            verdict_color = COLORS["warn"]

        # ── Signal colors ───────────────────────────────────────────────
        def _sig_color(sig: str) -> str:
            s = sig.upper().replace(" ", "_")
            if s in ("STRONG_BUY", "BUY", "BULLISH"):
                return COLORS["good"]
            if s in ("STRONG_SELL", "SELL", "BEARISH"):
                return COLORS["bad"]
            return COLORS["warn"]

        def _score_bar(score_val) -> html.Div:
            if score_val is None:
                return html.Div()
            pct = int((score_val + 1) / 2 * 100)
            bar_color = COLORS["good"] if score_val > 0.2 else (
                COLORS["bad"] if score_val < -0.2 else COLORS["warn"]
            )
            return html.Div([
                html.Div(style={
                    "width": f"{pct}%", "height": "4px",
                    "backgroundColor": bar_color, "borderRadius": "2px",
                }),
            ], style={
                "width": "100%", "height": "4px",
                "backgroundColor": COLORS["border"], "borderRadius": "2px",
                "marginTop": "6px",
            })

        # ── Signal cards row ────────────────────────────────────────────
        macro_score_label = f"{macro_score:+.2f}" if macro_score is not None else "—"
        llm_score_label   = f"{llm_score:+.2f}" if llm_score is not None else "—"

        banner = html.Div([

            # LLM Signal card
            html.Div([
                html.Div("LLM Signal (Stage 1)", className="stat-label"),
                html.Div(
                    llm_signal,
                    className="stat-value",
                    style={"color": _sig_color(llm_signal), "fontSize": "18px"},
                ),
                html.Div(
                    f"Score: {llm_score_label}",
                    className="dim-text",
                    style={"marginTop": "2px"},
                ),
                _score_bar(llm_score),
                html.Div(
                    llm_response[:120] + "…" if len(llm_response) > 120 else llm_response,
                    style={"color": COLORS["text_dim"], "fontSize": "11px",
                           "marginTop": "6px", "lineHeight": "1.4"},
                ) if llm_response else html.Div(),
            ], className="stat-card", style={"flex": "2", "minWidth": "220px"}),

            # Macro Signal card
            html.Div([
                html.Div("Macro Signal (FRED)", className="stat-label"),
                html.Div(
                    macro_signal,
                    className="stat-value",
                    style={"color": _sig_color(macro_signal), "fontSize": "18px"},
                ),
                html.Div(
                    f"Score: {macro_score_label}",
                    className="dim-text",
                    style={"marginTop": "2px"},
                ),
                _score_bar(macro_score),
                html.Div(
                    f"↑ Bull: {bull_when[:80]}",
                    style={"color": COLORS["good"], "fontSize": "11px",
                           "marginTop": "6px", "lineHeight": "1.4"},
                ),
            ], className="stat-card", style={"flex": "2", "minWidth": "220px"}),

            # Verdict card
            html.Div([
                html.Div("Verdict", className="stat-label"),
                html.Div(
                    verdict_text,
                    className="stat-value",
                    style={"color": verdict_color, "fontSize": "17px"},
                ),
                html.Div(
                    verdict_sub,
                    style={"color": COLORS["text_dim"], "fontSize": "11px",
                           "marginTop": "6px", "lineHeight": "1.4"},
                ),
            ], className="stat-card", style={"flex": "3", "minWidth": "260px"}),

        ], className="stats-row")

        # ── Description + indicator table ───────────────────────────────
        _val_cols = [
            {"name": "Indicator", "id": "name"},
            {"name": "Latest",    "id": "latest"},
            {"name": "1W Δ",      "id": "change_1w"},
            {"name": "As of",     "id": "as_of"},
            {"name": "Reading",   "id": "reading"},
        ]
        val_ts = TABLE_STYLES()
        val_ts["style_data_conditional"] = val_ts["style_data_conditional"] + [
            {"if": {"filter_query": '{reading} = "Bullish signal"',
                    "column_id": "reading"},
             "color": COLORS["good"], "fontWeight": "600"},
            {"if": {"filter_query": '{reading} = "Bearish signal"',
                    "column_id": "reading"},
             "color": COLORS["bad"], "fontWeight": "600"},
        ]

        table_wrap = html.Div([
            html.Div(
                description,
                style={"color": COLORS["text_dim"], "fontSize": "12px",
                       "marginBottom": "10px", "lineHeight": "1.5"},
            ),
            html.Div(f"Key macro indicators for {sector}", className="subsection-title",
                     style={"marginBottom": "8px"}),
            dash_table.DataTable(
                id="s2-val-table",
                columns=_val_cols,
                data=ind_rows,
                **val_ts,
            ),
        ])

        ts_str = datetime.now().strftime("%H:%M:%S")
        return banner, table_wrap, f"Validated at {ts_str}."
