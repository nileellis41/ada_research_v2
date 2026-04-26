"""Application entry point — Dash/Plotly web UI.

Invoked by:
    - run.py (without installation)
    - the `ada-research` console script (after `pip install -e .`)

Opens a local Dash server at http://localhost:8050
"""
from __future__ import annotations

import dash

from ada_research.utils.logger import get_logger

log = get_logger(__name__)


def create_app() -> dash.Dash:
    app = dash.Dash(
        __name__,
        title="Ada Research",
        suppress_callback_exceptions=True,
        update_title=None,
    )

    from ada_research.ui.layout import create_layout
    app.layout = create_layout()

    from ada_research.tabs import (
        stage1_sentiment,
        stage2_macro,
        sprint1_market,
        sprint2_sectors,
        sprint3_analysts,
        sprint4_screener,
    )
    for mod in (
        stage1_sentiment,
        stage2_macro,
        sprint1_market,
        sprint2_sectors,
        sprint3_analysts,
        sprint4_screener,
    ):
        mod.register_callbacks(app)

    return app


def main() -> None:
    log.info("starting Ada Research (Dash)")
    app = create_app()

    # Pre-fetch all sector/industry data in the background so Sprint 3
    # is ready by the time the user navigates there.
    from ada_research.utils.config import config as _cfg
    if _cfg.has_fmp_key():
        from ada_research.core.sector_data import prefetch_async
        prefetch_async()

    print("\n  Ada Research  →  http://localhost:8050\n")
    app.run(debug=False, port=8050, host="127.0.0.1")


if __name__ == "__main__":
    main()
