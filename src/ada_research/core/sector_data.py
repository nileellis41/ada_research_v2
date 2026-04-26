"""Sector data bundle — collects all Sprint 2/3 FMP data in one pass.

On app startup, `prefetch_async()` is called to collect everything in a
background thread. Subsequent callback calls hit the in-memory cache
(sub-millisecond). The cache is refreshed on explicit user request via
`get_bundle(force=True)`.

Data collected
--------------
- Sector performance snapshot (today)
- Industry performance snapshot (today, ~128 industries)
- Sector P/E snapshot (today)
- Industry P/E snapshot (today)
- Historical sector performance — all 11 sectors, 90 days
- Historical sector P/E        — all 11 sectors, 180 days
- Biggest gainers  (top 20)
- Biggest losers   (top 20)
- Most active      (top 20)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

from ada_research.utils.logger import get_logger

log = get_logger(__name__)

# Same names FMP returns in /sector-performance-snapshot
FMP_SECTORS: list[str] = [
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


@dataclass
class SectorDataBundle:
    """All sector/industry data collected in a single FMP pass."""

    collected_at: datetime

    # Snapshot tables (today)
    sector_snapshot:   pd.DataFrame
    industry_snapshot: pd.DataFrame
    sector_pe:         pd.DataFrame
    industry_pe:       pd.DataFrame

    # Historical series keyed by sector name
    hist_sector_perf: dict[str, pd.DataFrame] = field(default_factory=dict)
    hist_sector_pe:   dict[str, pd.DataFrame] = field(default_factory=dict)

    # Market movers
    gainers: pd.DataFrame = field(default_factory=pd.DataFrame)
    losers:  pd.DataFrame = field(default_factory=pd.DataFrame)
    actives: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.collected_at).total_seconds()

    @property
    def sector_names(self) -> list[str]:
        """Sector names present in this bundle's snapshot."""
        if not self.sector_snapshot.empty and "sector" in self.sector_snapshot.columns:
            return self.sector_snapshot["sector"].dropna().tolist()
        return FMP_SECTORS


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_bundle: Optional[SectorDataBundle] = None
_lock   = threading.Lock()
_thread: Optional[threading.Thread] = None


def prefetch_async() -> None:
    """Kick off background data collection (called once at app startup)."""
    global _thread
    if _bundle is not None:
        return
    if _thread is not None and _thread.is_alive():
        return

    _thread = threading.Thread(target=_fetch, daemon=True, name="sector-prefetch")
    _thread.start()
    log.info("sector data prefetch started in background")


def get_bundle(force: bool = False) -> SectorDataBundle:
    """Return the cached bundle, fetching synchronously if needed.

    Pass ``force=True`` to bypass the cache (e.g. on user-triggered refresh).
    """
    global _bundle
    if _bundle is not None and not force:
        log.debug("sector bundle cache hit (age %.0fs)", _bundle.age_seconds)
        return _bundle

    with _lock:
        # Double-checked locking: another thread may have populated it already
        if _bundle is not None and not force:
            return _bundle
        _fetch()
        return _bundle  # type: ignore[return-value]


def is_ready() -> bool:
    """True if data has been collected at least once."""
    return _bundle is not None


# ---------------------------------------------------------------------------
# Internal fetcher
# ---------------------------------------------------------------------------

def _fetch() -> None:
    global _bundle
    try:
        from ada_research.core.fmp_client import FmpClient
        c = FmpClient()

        log.info("collecting sector data bundle…")
        t0 = datetime.now()

        # ── Snapshot data ────────────────────────────────────────────────
        sector_snap   = c.sector_snapshot()
        industry_snap = c.industry_snapshot()
        sector_pe     = c.sector_pe()
        industry_pe   = c.industry_pe()
        gainers       = c.gainers()
        losers        = c.losers()
        actives       = c.most_actives()

        # Determine sector list from live snapshot (falls back to hardcoded)
        if not sector_snap.empty and "sector" in sector_snap.columns:
            sectors = sector_snap["sector"].dropna().tolist()
        else:
            sectors = FMP_SECTORS

        # ── Historical performance (all sectors, 90 days) ────────────────
        hist_perf: dict[str, pd.DataFrame] = {}
        for s in sectors:
            df = c.historical_sector(s, days=90)
            if not df.empty:
                df = _prep(df, "averageChange")
            hist_perf[s] = df
            log.debug("  hist perf: %s (%d rows)", s, len(df))

        # ── Historical P/E (all sectors, 180 days) ───────────────────────
        hist_pe: dict[str, pd.DataFrame] = {}
        for s in sectors:
            df = c.historical_sector_pe(s, days=180)
            if not df.empty:
                df = _prep(df, "pe")
            hist_pe[s] = df
            log.debug("  hist PE:   %s (%d rows)", s, len(df))

        elapsed = (datetime.now() - t0).total_seconds()
        log.info(
            "sector bundle collected in %.1fs — "
            "%d sectors, %d industries, %d gainers",
            elapsed, len(sectors), len(industry_snap), len(gainers),
        )

        _bundle = SectorDataBundle(
            collected_at=datetime.now(),
            sector_snapshot=sector_snap,
            industry_snapshot=industry_snap,
            sector_pe=sector_pe,
            industry_pe=industry_pe,
            hist_sector_perf=hist_perf,
            hist_sector_pe=hist_pe,
            gainers=gainers,
            losers=losers,
            actives=actives,
        )

    except Exception as exc:
        log.exception("sector data collection failed: %s", exc)


# ---------------------------------------------------------------------------
# Data-prep helper
# ---------------------------------------------------------------------------

def _prep(df: pd.DataFrame, val_col: str) -> pd.DataFrame:
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    if val_col in df.columns:
        df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=[val_col])
    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)
    return df
