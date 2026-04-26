"""Color palette for the Dash UI.

All UI colors live here. To switch themes, edit COLORS — nothing else needs changing.
"""
from __future__ import annotations

COLORS = {
    "bg":        "#0f1419",
    "panel":     "#1a1f2e",
    "panel_hi":  "#242937",
    "border":    "#2d3548",
    "text":      "#e6e9ef",
    "text_dim":  "#9aa3b8",
    "accent":    "#5b9bd5",
    "accent_hi": "#7eb7e8",
    "good":      "#4caf50",
    "good_dim":  "#2d6a30",
    "bad":       "#e57373",
    "bad_dim":   "#7a3030",
    "warn":      "#ffb74d",
    "warn_dim":  "#7a5520",
}

_TONE_MAP = {
    "good":    COLORS["good"],
    "bad":     COLORS["bad"],
    "warn":    COLORS["warn"],
    "neutral": COLORS["text"],
}


def tone_color(tone: str) -> str:
    return _TONE_MAP.get(tone, COLORS["text"])


def signal_tone(signal: str) -> str:
    s = signal.upper()
    if s in ("STRONG_BUY", "BUY"):
        return "good"
    if s in ("STRONG_SELL", "SELL"):
        return "bad"
    return "warn"


def TABLE_STYLES() -> dict:
    """Return common DataTable style kwargs."""
    return dict(
        style_table={"overflowX": "auto", "minWidth": "100%"},
        style_header={
            "backgroundColor": COLORS["bg"],
            "color": COLORS["text_dim"],
            "fontWeight": "500",
            "border": f"1px solid {COLORS['border']}",
            "padding": "6px 8px",
            "whiteSpace": "nowrap",
        },
        style_cell={
            "backgroundColor": COLORS["panel"],
            "color": COLORS["text"],
            "border": f"1px solid {COLORS['border']}",
            "padding": "6px 8px",
            "fontFamily": "-apple-system, 'Segoe UI', 'Inter', sans-serif",
            "fontSize": "13px",
            "textAlign": "left",
            "whiteSpace": "normal",
            "overflow": "hidden",
            "textOverflow": "ellipsis",
        },
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": COLORS["panel_hi"]},
        ],
        style_as_list_view=False,
    )
