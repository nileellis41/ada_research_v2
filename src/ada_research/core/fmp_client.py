"""FMP (Financial Modeling Prep) client — lifted from the sprint notebooks.

Consolidates the four sprints into one client:
  Sprint 1 — quotes, historical prices
  Sprint 2 — sectors, industries, movers
  Sprint 3 — analyst estimates, ratings, grades
  Sprint 4 — stock screener with named presets

All endpoints use FMP's `/stable/` API base. The legacy `/api/v3/` endpoints
were retired August 2025.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Literal

import pandas as pd
import requests

from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)

BASE_URL = "https://financialmodelingprep.com/stable"


class FMPPremiumError(Exception):
    """Raised when an endpoint requires a paid subscription."""


class FmpClient:
    """One client for all four sprints."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.fmp_api_key
        if not self.api_key:
            raise RuntimeError(
                "FMP_API_KEY missing. Get a free key at "
                "https://site.financialmodelingprep.com/ and add it to .env"
            )

    # ---- HTTP layer ---------------------------------------------------------

    def _get(self, path: str, **params) -> Any:
        params["apikey"] = self.api_key
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get(url, params=params, timeout=20)
        except requests.RequestException as e:
            log.warning("FMP request failed: %s %s", path, e)
            raise
        if r.status_code >= 500:
            r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Error Message" in data:
            msg = data["Error Message"]
            if "Premium" in msg or "subscription" in msg.lower():
                raise FMPPremiumError(msg)
            raise ValueError(f"FMP API error ({path}): {msg}")
        return data

    def safe(self, path: str, **params) -> Any:
        """Call _get but return None on premium-gating or recoverable errors."""
        try:
            return self._get(path, **params)
        except FMPPremiumError as e:
            log.info("paid plan required for %s: %s", path, e)
            return None
        except (ValueError, requests.RequestException) as e:
            log.warning("failed call %s: %s", path, e)
            return None

    # ---- Sprint 1: quotes & historical -------------------------------------

    def quote(self, symbol: str) -> dict | None:
        data = self.safe("/quote", symbol=symbol)
        if isinstance(data, list) and data:
            return data[0]
        return None

    def historical_prices(self, symbol: str, periods: int | None = None) -> pd.DataFrame:
        data = self.safe("/historical-price-eod/full", symbol=symbol)
        if data is None:
            return pd.DataFrame()
        records = data.get("historical", data) if isinstance(data, dict) else data
        df = pd.DataFrame(records)
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        if periods is not None and len(df) > periods:
            df = df.tail(periods).reset_index(drop=True)
        return df

    # ---- Sprint 2: sectors, industries, movers -----------------------------

    @staticmethod
    def _latest_business_day() -> str:
        d = date.today()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.isoformat()

    def sector_snapshot(self, snap_date: str | None = None) -> pd.DataFrame:
        snap_date = snap_date or self._latest_business_day()
        return pd.DataFrame(self.safe("/sector-performance-snapshot", date=snap_date) or [])

    def industry_snapshot(self, snap_date: str | None = None) -> pd.DataFrame:
        snap_date = snap_date or self._latest_business_day()
        return pd.DataFrame(self.safe("/industry-performance-snapshot", date=snap_date) or [])

    def historical_sector(self, sector: str, days: int = 90) -> pd.DataFrame:
        params = {
            "sector": sector,
            "from": (date.today() - timedelta(days=days)).isoformat(),
            "to": date.today().isoformat(),
        }
        return pd.DataFrame(self.safe("/historical-sector-performance", **params) or [])

    def historical_industry(self, industry: str, days: int = 90) -> pd.DataFrame:
        params = {
            "industry": industry,
            "from": (date.today() - timedelta(days=days)).isoformat(),
            "to": date.today().isoformat(),
        }
        return pd.DataFrame(self.safe("/historical-industry-performance", **params) or [])

    def historical_sector_pe(self, sector: str, days: int = 180) -> pd.DataFrame:
        params = {
            "sector": sector,
            "from": (date.today() - timedelta(days=days)).isoformat(),
            "to": date.today().isoformat(),
        }
        return pd.DataFrame(self.safe("/historical-sector-pe", **params) or [])

    def historical_industry_pe(self, industry: str, days: int = 180) -> pd.DataFrame:
        params = {
            "industry": industry,
            "from": (date.today() - timedelta(days=days)).isoformat(),
            "to": date.today().isoformat(),
        }
        return pd.DataFrame(self.safe("/historical-industry-pe", **params) or [])

    def sector_pe(self, snap_date: str | None = None) -> pd.DataFrame:
        snap_date = snap_date or self._latest_business_day()
        return pd.DataFrame(self.safe("/sector-pe-snapshot", date=snap_date) or [])

    def industry_pe(self, snap_date: str | None = None) -> pd.DataFrame:
        snap_date = snap_date or self._latest_business_day()
        return pd.DataFrame(self.safe("/industry-pe-snapshot", date=snap_date) or [])

    def gainers(self) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/biggest-gainers") or [])

    def losers(self) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/biggest-losers") or [])

    def most_actives(self) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/most-actives") or [])

    # ---- Sprint 3: analyst features ----------------------------------------

    def analyst_estimates(
        self,
        symbol: str,
        period: Literal["annual", "quarter"] = "annual",
        limit: int = 10,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            self.safe("/analyst-estimates", symbol=symbol, period=period, page=0, limit=limit) or []
        )

    def ratings_snapshot(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/ratings-snapshot", symbol=symbol) or [])

    def ratings_historical(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/ratings-historical", symbol=symbol, limit=limit) or [])

    def price_target_summary(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/price-target-summary", symbol=symbol) or [])

    def price_target_consensus(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/price-target-consensus", symbol=symbol) or [])

    def grades(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/grades", symbol=symbol) or [])

    def grades_summary(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/grades-summary", symbol=symbol) or [])

    def grades_latest_news(self, limit: int = 30) -> pd.DataFrame:
        return pd.DataFrame(self.safe("/grades-latest-news", page=0, limit=limit) or [])

    # ---- Sprint 4: screener ------------------------------------------------

    def screen(
        self,
        *,
        market_cap_min: float | None = None,
        market_cap_max: float | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        beta_min: float | None = None,
        beta_max: float | None = None,
        volume_min: int | None = None,
        dividend_min: float | None = None,
        sector: str | None = None,
        industry: str | None = None,
        country: str | None = "US",
        exchange: str | None = None,
        is_etf: bool = False,
        is_fund: bool = False,
        is_actively_trading: bool = True,
        limit: int = 50,
    ) -> pd.DataFrame:
        raw = {
            "marketCapMoreThan": market_cap_min,
            "marketCapLowerThan": market_cap_max,
            "priceMoreThan": price_min,
            "priceLowerThan": price_max,
            "betaMoreThan": beta_min,
            "betaLowerThan": beta_max,
            "volumeMoreThan": volume_min,
            "dividendMoreThan": dividend_min,
            "sector": sector,
            "industry": industry,
            "country": country,
            "exchange": exchange,
            "isEtf": str(is_etf).lower(),
            "isFund": str(is_fund).lower(),
            "isActivelyTrading": str(is_actively_trading).lower(),
            "limit": limit,
        }
        params = {k: v for k, v in raw.items() if v is not None}
        return pd.DataFrame(self.safe("/company-screener", **params) or [])


# ---- Screener presets (Sprint 4) ----------------------------------------------

def screen_large_cap_stable(client: FmpClient, limit: int = 30) -> pd.DataFrame:
    return client.screen(market_cap_min=50_000_000_000, beta_max=1.0, limit=limit)


def screen_dividend_income(client: FmpClient, limit: int = 30) -> pd.DataFrame:
    return client.screen(market_cap_min=10_000_000_000, dividend_min=1.0, limit=limit)


def screen_tech_growth(client: FmpClient, limit: int = 30) -> pd.DataFrame:
    return client.screen(
        sector="Technology",
        market_cap_min=5_000_000_000,
        volume_min=1_000_000,
        limit=limit,
    )


def screen_small_cap_movers(client: FmpClient, limit: int = 30) -> pd.DataFrame:
    return client.screen(
        market_cap_min=300_000_000,
        market_cap_max=2_000_000_000,
        price_min=5.0,
        volume_min=500_000,
        limit=limit,
    )


def screen_defensive(client: FmpClient, limit: int = 15) -> pd.DataFrame:
    frames = []
    for sector in ("Consumer Defensive", "Healthcare", "Utilities"):
        df = client.screen(sector=sector, market_cap_min=10_000_000_000,
                           beta_max=1.0, limit=limit)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def screen_aggressive(client: FmpClient, limit: int = 30) -> pd.DataFrame:
    return client.screen(
        beta_min=1.5,
        market_cap_min=1_000_000_000,
        price_min=10.0,
        limit=limit,
    )


SCREEN_PRESETS: dict[str, tuple[Any, str]] = {
    "large_cap_stable": (screen_large_cap_stable, "Big, established names with low volatility"),
    "dividend_income":  (screen_dividend_income,  "Mid/large caps with meaningful dividends"),
    "tech_growth":      (screen_tech_growth,      "Liquid tech names worth tracking"),
    "small_cap_movers": (screen_small_cap_movers, "Smaller companies with enough liquidity"),
    "defensive":        (screen_defensive,        "Defensive sectors for risk-off regimes"),
    "aggressive":       (screen_aggressive,       "High-beta names for risk-on regimes"),
}
