"""Reusable Dash component builders.

Pure functions — no side effects, no imports from tab modules.
Each returns a Dash component tree.
"""
from __future__ import annotations

from dash import dcc, html

from ada_research.ui.theme import COLORS, tone_color


# ---------------------------------------------------------------------------
# Stat card
# ---------------------------------------------------------------------------

def stat_card(
    label: str,
    value: str = "—",
    sublabel: str | None = None,
    tone: str = "neutral",
    value_id: str | None = None,
    card_id: str | None = None,
) -> html.Div:
    value_el = html.Div(
        value,
        id=value_id,
        className="stat-value",
        style={"color": tone_color(tone)},
    ) if value_id else html.Div(
        value,
        className="stat-value",
        style={"color": tone_color(tone)},
    )
    children = [
        html.Div(label, className="stat-label"),
        value_el,
    ]
    if sublabel:
        children.append(html.Div(sublabel, className="stat-sublabel"))

    kwargs = {"className": "stat-card"}
    if card_id:
        kwargs["id"] = card_id
    return html.Div(children, **kwargs)


def updatable_stat_card(label: str, card_id: str) -> html.Div:
    """Stat card whose entire content is replaced by a callback via card_id."""
    return html.Div([
        html.Div(label, className="stat-label"),
        html.Div("—", className="stat-value"),
    ], id=card_id, className="stat-card")


# ---------------------------------------------------------------------------
# Signal badge
# ---------------------------------------------------------------------------

def signal_badge(signal: str) -> html.Span:
    sig = signal.upper().replace(" ", "_")
    return html.Span(sig.replace("_", " "), className=f"signal-badge sig-{sig}")


# ---------------------------------------------------------------------------
# Section headers
# ---------------------------------------------------------------------------

def section_header(title: str, subtitle: str | None = None) -> html.Div:
    children: list = [html.H2(title, className="section-title")]
    if subtitle:
        children.append(html.P(subtitle, className="section-subtitle"))
    return html.Div(children)


def subsection_title(text: str) -> html.Div:
    return html.Div(text, className="subsection-title")


# ---------------------------------------------------------------------------
# Placeholder (missing API key)
# ---------------------------------------------------------------------------

def placeholder_panel(title: str, message: str) -> html.Div:
    return html.Div([
        html.H3(title),
        html.P(message),
    ], className="placeholder-panel")


# ---------------------------------------------------------------------------
# Styled button
# ---------------------------------------------------------------------------

def btn(label: str, btn_id: str, primary: bool = False, **kwargs) -> html.Button:
    cls = "ada-btn ada-btn-primary" if primary else "ada-btn"
    return html.Button(label, id=btn_id, className=cls, **kwargs)


# ---------------------------------------------------------------------------
# Styled text input
# ---------------------------------------------------------------------------

def text_input(input_id: str, placeholder: str = "", value: str = "", width: str = "140px") -> dcc.Input:
    return dcc.Input(
        id=input_id,
        type="text",
        placeholder=placeholder,
        value=value,
        className="ada-input",
        style={"width": width},
        debounce=False,
    )


# ---------------------------------------------------------------------------
# Status label
# ---------------------------------------------------------------------------

def status_label(label_id: str) -> html.Div:
    return html.Div("", id=label_id, className="dim-text", style={"marginTop": "8px"})
