"""Stage 1: PDF Sentiment Analysis (Dash/Plotly UI).

Layout
------
Left column  — PDF upload / text excerpt panel (always visible)
Right column — Inner tabs:
  • Overview      — stat cards + Sector Details table + sample sentences
  • LLM Responses — per-sector Claude analysis cards (requires ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import base64
import json
import tempfile
from datetime import datetime
from pathlib import Path

import dash
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from ada_research.ui.components import (
    btn,
    section_header,
    signal_badge,
    status_label,
)
from ada_research.ui.theme import COLORS, TABLE_STYLES, signal_tone, tone_color
from ada_research.utils.logger import get_logger

log = get_logger(__name__)

_COLS = [
    {"name": "Sector",      "id": "sector"},
    {"name": "LM Signal",   "id": "signal"},
    {"name": "LLM Signal",  "id": "llm_signal"},
    {"name": "Compound",    "id": "compound"},
    {"name": "Confidence",  "id": "confidence"},
    {"name": "Mentions",    "id": "mentions"},
    {"name": "Tokens",      "id": "tokens"},
]

_SUB_TAB = {
    "className": "sub-tab",
    "selected_className": "sub-tab--selected",
}


def layout() -> html.Div:
    ts = TABLE_STYLES()
    _signal_rules = []
    for col_id in ("signal", "llm_signal"):
        _signal_rules += [
            {"if": {"filter_query": f"{{{col_id}}} = 'STRONG BUY' || {{{col_id}}} = 'BUY'",
                    "column_id": col_id}, "color": COLORS["good"], "fontWeight": "600"},
            {"if": {"filter_query": f"{{{col_id}}} = 'SELL' || {{{col_id}}} = 'STRONG SELL'",
                    "column_id": col_id}, "color": COLORS["bad"], "fontWeight": "600"},
            {"if": {"filter_query": f"{{{col_id}}} = 'HOLD'",
                    "column_id": col_id}, "color": COLORS["warn"], "fontWeight": "600"},
            {"if": {"filter_query": f"{{{col_id}}} = '—'",
                    "column_id": col_id}, "color": COLORS["text_dim"]},
        ]
    ts["style_data_conditional"] = ts["style_data_conditional"] + _signal_rules

    return html.Div([
        dcc.Store(id="s1-store"),
        dcc.Download(id="s1-download"),

        section_header(
            "Stage 1 — PDF Sentiment Analysis",
            "Extracts sector commentary from a PDF and scores it with the "
            "Loughran-McDonald lexicon. Set ANTHROPIC_API_KEY for LLM analysis.",
        ),

        # ── Split layout ────────────────────────────────────────────────
        html.Div([

            # LEFT: PDF upload + text input
            html.Div([
                dcc.Upload(
                    id="s1-upload",
                    children=html.Div([
                        html.Div("📄", style={"fontSize": "28px", "marginBottom": "6px"}),
                        html.Div("Drop a PDF here"),
                        html.Div("— or click to browse —",
                                 style={"color": COLORS["accent"], "fontSize": "12px"}),
                    ]),
                    className="upload-zone",
                    multiple=False,
                    accept=".pdf",
                    style={"marginBottom": "12px"},
                ),

                html.Div("Or analyze text directly", className="subsection-title",
                         style={"marginBottom": "8px"}),

                html.Div([
                    html.Label("Sector tag (optional):",
                               style={"color": COLORS["text_dim"], "fontSize": "12px",
                                      "whiteSpace": "nowrap"}),
                    dcc.Input(
                        id="s1-sector", type="text",
                        placeholder="e.g. Technology",
                        className="ada-input",
                        style={"flex": "1"},
                        debounce=False,
                    ),
                ], style={"display": "flex", "alignItems": "center",
                          "gap": "8px", "marginBottom": "8px"}),

                dcc.Textarea(
                    id="s1-text",
                    placeholder=(
                        "Paste broker commentary, earnings excerpt, "
                        "or any financial text…"
                    ),
                    className="ada-textarea",
                    style={"height": "160px", "marginBottom": "8px"},
                ),

                btn("Analyze Text", "s1-analyze-btn", primary=True,
                    style={"width": "100%", "marginBottom": "12px"}),

                status_label("s1-status"),
            ], className="split-left"),

            # RIGHT: inner tabs — Overview and LLM Responses
            html.Div([
                dcc.Tabs(
                    id="s1-result-tabs",
                    value="s1-tab-overview",
                    className="sub-tabs",
                    children=[

                        # ── Overview tab ─────────────────────────────────
                        dcc.Tab(
                            label="Overview",
                            value="s1-tab-overview",
                            **_SUB_TAB,
                            children=[html.Div([

                                # Stat cards
                                html.Div([
                                    html.Div([
                                        html.Div("Overall Sentiment", className="stat-label"),
                                        html.Div("—", id="s1-stat-overall", className="stat-value"),
                                    ], className="stat-card"),
                                    html.Div([
                                        html.Div("Sectors Detected", className="stat-label"),
                                        html.Div("0", id="s1-stat-sectors", className="stat-value"),
                                    ], className="stat-card"),
                                    html.Div([
                                        html.Div("Pages Processed", className="stat-label"),
                                        html.Div("0", id="s1-stat-pages", className="stat-value"),
                                    ], className="stat-card"),
                                    html.Div([
                                        html.Div("Confidence", className="stat-label"),
                                        html.Div("—", id="s1-stat-confidence", className="stat-value"),
                                    ], className="stat-card"),
                                    html.Div([
                                        html.Div("Chunks", className="stat-label"),
                                        html.Div("—", id="s1-stat-chunks", className="stat-value"),
                                    ], className="stat-card"),
                                ], className="stats-row", style={"marginTop": "12px"}),

                                # Sector Details sub-section
                                html.Div([
                                    html.Div("Sector Details", className="subsection-title",
                                             style={"margin": "0"}),
                                    html.Div([
                                        btn("Export CSV",  "s1-export-csv"),
                                        btn("Export JSON", "s1-export-json"),
                                    ], style={"display": "flex", "gap": "8px",
                                              "marginLeft": "auto"}),
                                ], style={"display": "flex", "alignItems": "center",
                                          "marginBottom": "10px", "marginTop": "16px"}),

                                dcc.Loading(
                                    type="circle", color=COLORS["accent"],
                                    children=dash_table.DataTable(
                                        id="s1-table",
                                        columns=_COLS,
                                        data=[],
                                        row_selectable="single",
                                        selected_rows=[],
                                        page_size=20,
                                        **ts,
                                    ),
                                ),

                                html.Div([
                                    html.Div("Sample sentences for selected sector",
                                             className="dim-text",
                                             style={"marginBottom": "6px"}),
                                    dcc.Textarea(
                                        id="s1-samples",
                                        readOnly=True,
                                        className="ada-textarea",
                                        style={"height": "100px", "resize": "none",
                                               "marginTop": "8px"},
                                    ),
                                ], style={"marginTop": "12px"}),

                            ], style={"padding": "0 4px"})],
                        ),

                        # ── LLM Responses tab ─────────────────────────────
                        dcc.Tab(
                            label="LLM Responses",
                            value="s1-tab-llm",
                            **_SUB_TAB,
                            children=[html.Div([

                                html.Div(
                                    id="s1-llm-status",
                                    style={"marginTop": "12px", "marginBottom": "8px"},
                                ),

                                dcc.Loading(
                                    type="circle", color=COLORS["accent"],
                                    children=html.Div(
                                        id="s1-llm-cards",
                                        style={
                                            "display": "grid",
                                            "gridTemplateColumns":
                                                "repeat(auto-fill, minmax(340px, 1fr))",
                                            "gap": "10px",
                                        },
                                    ),
                                ),

                            ], style={"padding": "0 4px"})],
                        ),

                    ],
                ),
            ], className="split-right"),

        ], className="split-layout"),

    ], className="tab-content")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:

    @app.callback(
        Output("s1-stat-overall",    "children"),
        Output("s1-stat-overall",    "style"),
        Output("s1-stat-sectors",    "children"),
        Output("s1-stat-pages",      "children"),
        Output("s1-stat-confidence", "children"),
        Output("s1-stat-chunks",     "children"),
        Output("s1-table",           "data"),
        Output("s1-status",          "children"),
        Output("s1-store",           "data"),
        Output("ada-llm-store",      "data"),
        Input("s1-upload",       "contents"),
        Input("s1-analyze-btn",  "n_clicks"),
        State("s1-upload",  "filename"),
        State("s1-text",    "value"),
        State("s1-sector",  "value"),
        prevent_initial_call=True,
    )
    def process(contents, _n, filename, text, sector):
        from ada_research.core.pipeline import run_pipeline_on_pdf, run_pipeline_on_text

        _no = dash.no_update
        trigger = dash.ctx.triggered_id
        results = None

        if trigger == "s1-upload" and contents:
            try:
                _, content_string = contents.split(",", 1)
                pdf_bytes = base64.b64decode(content_string)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = Path(tmp.name)
                results = run_pipeline_on_pdf(tmp_path)
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            except Exception as exc:
                log.exception("PDF processing failed")
                return ("Error", {}, _no, _no, _no, _no, [], f"Error: {exc}", _no, _no)

        elif trigger == "s1-analyze-btn":
            if not text or not text.strip():
                return (_no,) * 9 + (_no,)
            try:
                results = run_pipeline_on_text(
                    text.strip(),
                    sector_name=sector.strip() if sector else None,
                )
            except Exception as exc:
                log.exception("Text analysis failed")
                return ("Error", {}, _no, _no, _no, _no, [], f"Error: {exc}", _no, _no)

        if results is None:
            raise PreventUpdate

        overall = results.overall
        tone = signal_tone(overall.signal)

        # Serialize LLM analyses
        llm_data: dict = {}
        for sname, llm in results.llm_analyses.items():
            llm_data[sname] = {
                "score":       llm.score,
                "signal":      llm.signal,
                "response":    llm.response,
                "key_themes":  llm.key_themes,
                "chunks_used": llm.chunks_used,
                "model":       llm.model,
                "available":   llm.available,
            }

        store_data = {
            "overall": {
                "signal":     overall.signal,
                "compound":   overall.compound,
                "confidence": overall.confidence,
            },
            "page_count":    results.document.page_count if results.document else None,
            "num_chunks":    len(results.chunks),
            "llm_available": results.llm_available,
            "llm_analyses":  llm_data,
            "rows": [
                {**row, "sample_sentences": sec.sample_sentences}
                for row, sec in zip(results.to_rows(), results.sectors)
            ],
        }

        # LLM signal per sector for the table (falls back to "—")
        table_data = [
            {
                "sector":     r["sector"],
                "signal":     r["signal"].replace("_", " "),
                "llm_signal": (
                    llm_data[r["sector"]]["signal"].replace("_", " ")
                    if r["sector"] in llm_data and llm_data[r["sector"]]["available"]
                    else "—"
                ),
                "compound":   f"{r['compound']:+.3f}",
                "confidence": f"{r['confidence'] * 100:.0f}%",
                "mentions":   str(r["sentence_count"]),
                "tokens":     str(r["tokens"]),
            }
            for r in store_data["rows"]
        ]

        chunk_label = str(len(results.chunks)) if results.chunks else "—"

        # Global store for cross-tab LLM signal access (Stage 2 reads this)
        global_llm = {
            "llm_available": results.llm_available,
            "llm_analyses":  llm_data,
        }

        return (
            overall.signal.replace("_", " "),
            {"color": tone_color(tone)},
            str(results.sector_count),
            str(results.document.page_count) if results.document else "—",
            f"{overall.confidence * 100:.0f}%",
            chunk_label,
            table_data,
            "Done.",
            store_data,
            global_llm,
        )

    @app.callback(
        Output("s1-samples", "value"),
        Input("s1-table", "selected_rows"),
        State("s1-store", "data"),
        prevent_initial_call=True,
    )
    def show_samples(selected_rows, store_data):
        if not selected_rows or not store_data:
            raise PreventUpdate
        idx = selected_rows[0]
        rows = store_data.get("rows", [])
        if idx >= len(rows):
            raise PreventUpdate
        row = rows[idx]
        lines = [f"{row['sector']} — {row['signal']} (compound {row['compound']:+.3f})\n"]
        for s in row.get("sample_sentences", []):
            lines.append(f"• {s}")
        return "\n".join(lines)

    @app.callback(
        Output("s1-llm-status", "children"),
        Output("s1-llm-cards",  "children"),
        Input("s1-store", "data"),
    )
    def render_llm_tab(store_data):
        if not store_data:
            return (
                html.Div("Upload a PDF to run analysis.", className="dim-text"),
                [],
            )

        if not store_data.get("llm_available"):
            return (
                html.Div([
                    html.Span("LLM analysis unavailable. ", className="dim-text"),
                    html.Span("Set ", className="dim-text"),
                    html.Code("ANTHROPIC_API_KEY",
                              style={"background": COLORS["panel_hi"],
                                     "padding": "1px 5px", "borderRadius": "3px",
                                     "fontSize": "12px"}),
                    html.Span(" in your .env to enable Claude-powered sector analysis.",
                              className="dim-text"),
                ], style={"marginTop": "12px"}),
                [],
            )

        llm_analyses = store_data.get("llm_analyses", {})
        if not llm_analyses:
            return html.Div("No LLM analyses found.", className="dim-text"), []

        # Determine model label from first available result
        model_label = next(
            (v["model"] for v in llm_analyses.values() if v.get("available")),
            "—",
        )
        status = html.Div(
            f"Model: {model_label} · {sum(1 for v in llm_analyses.values() if v.get('available'))} sectors analyzed",
            className="dim-text",
            style={"marginTop": "12px"},
        )

        cards = []
        for sector_name, llm in llm_analyses.items():
            if not llm.get("available"):
                continue

            signal_str = llm["signal"].replace("_", " ")
            score_val  = llm["score"]
            score_color = (
                COLORS["good"] if score_val > 0.2
                else COLORS["bad"] if score_val < -0.2
                else COLORS["warn"]
            )

            themes = [
                html.Span(
                    theme,
                    style={
                        "background":    COLORS["panel_hi"],
                        "border":        f"1px solid {COLORS['border']}",
                        "borderRadius":  "3px",
                        "padding":       "2px 7px",
                        "fontSize":      "11px",
                        "color":         COLORS["text_dim"],
                        "whiteSpace":    "nowrap",
                    },
                )
                for theme in llm.get("key_themes", [])
            ]

            card = html.Div([
                # Card header: sector name + signal badge + score
                html.Div([
                    html.Span(sector_name,
                              style={"fontWeight": "600", "fontSize": "15px",
                                     "color": COLORS["text"]}),
                    signal_badge(llm["signal"]),
                    html.Span(
                        f"{score_val:+.2f}",
                        style={"color": score_color, "fontSize": "13px",
                               "fontWeight": "500"},
                    ),
                ], style={"display": "flex", "alignItems": "center",
                          "gap": "8px", "marginBottom": "8px"}),

                # LLM narrative response
                html.P(
                    llm["response"],
                    style={"color": COLORS["text"], "margin": "0 0 8px 0",
                           "lineHeight": "1.5", "fontSize": "13px"},
                ),

                # Key themes
                html.Div(themes,
                         style={"display": "flex", "flexWrap": "wrap", "gap": "5px",
                                "marginBottom": "8px"}),

                # Footer
                html.Div(
                    f"Chunks used: {llm['chunks_used']}",
                    className="dim-text",
                    style={"fontSize": "11px"},
                ),
            ], className="ada-card")

            cards.append(card)

        return status, cards

    @app.callback(
        Output("s1-download", "data"),
        Input("s1-export-csv",  "n_clicks"),
        Input("s1-export-json", "n_clicks"),
        State("s1-store", "data"),
        prevent_initial_call=True,
    )
    def export(n_csv, n_json, store_data):
        if not store_data or not store_data.get("rows"):
            raise PreventUpdate
        trigger = dash.ctx.triggered_id
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rows = store_data["rows"]

        if trigger == "s1-export-csv":
            import pandas as pd
            df = pd.DataFrame([
                {k: v for k, v in r.items() if k != "sample_sentences"}
                for r in rows
            ])
            return dcc.send_data_frame(df.to_csv, f"stage1_{ts}.csv", index=False)

        if trigger == "s1-export-json":
            payload = {
                "overall":       store_data["overall"],
                "page_count":    store_data["page_count"],
                "num_chunks":    store_data.get("num_chunks"),
                "llm_available": store_data.get("llm_available", False),
                "llm_analyses":  store_data.get("llm_analyses", {}),
                "sectors":       rows,
            }
            return dcc.send_string(
                json.dumps(payload, indent=2, default=str),
                f"stage1_{ts}.json",
            )

        raise PreventUpdate
