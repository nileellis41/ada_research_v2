"""FRED macro data client.

Wraps `fredapi` with a curated catalog of macro indicators organized into
categories that drive sector theses. Tab 2 (Macro Validation) consumes this.

Usage:
    client = FredClient()
    series = client.get_series("DGS10", periods=252)   # daily, 1Y
    multi = client.get_many(["DGS10", "DGS2"])        # multiple series
    snapshot = client.snapshot()                       # latest values for all curated indicators
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from ada_research.utils.config import config
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Indicator:
    """Static metadata about a FRED series we surface in the UI."""

    series_id: str
    name: str
    category: str
    units: str
    frequency: str
    description: str = ""


# Curated catalog. Add/remove freely — UI categories pull from here.
INDICATORS: tuple[Indicator, ...] = (
    # === Rates & Curve =========================================================
    Indicator("DFF", "Fed Funds Rate", "Rates & Curve", "%", "Daily",
              "Effective federal funds rate"),
    Indicator("DGS3MO", "3-Month Treasury", "Rates & Curve", "%", "Daily",
              "3-month Treasury constant maturity"),
    Indicator("DGS2", "2-Year Treasury", "Rates & Curve", "%", "Daily",
              "2-year Treasury constant maturity"),
    Indicator("DGS10", "10-Year Treasury", "Rates & Curve", "%", "Daily",
              "10-year Treasury constant maturity — benchmark long rate"),
    Indicator("T10Y2Y", "10Y-2Y Spread", "Rates & Curve", "% pts", "Daily",
              "10-year minus 2-year — classic recession indicator when negative"),
    Indicator("T10Y3M", "10Y-3M Spread", "Rates & Curve", "% pts", "Daily",
              "10-year minus 3-month — preferred recession indicator"),
    Indicator("MORTGAGE30US", "30Y Mortgage Rate", "Rates & Curve", "%", "Weekly",
              "30-year fixed mortgage rate — housing transmission"),
    Indicator("SOFR", "SOFR", "Rates & Curve", "%", "Daily",
              "Secured Overnight Financing Rate"),

    # === Inflation =============================================================
    Indicator("CPIAUCSL", "Headline CPI", "Inflation", "Index", "Monthly",
              "Consumer Price Index, all urban consumers, seasonally adjusted"),
    Indicator("CPILFESL", "Core CPI", "Inflation", "Index", "Monthly",
              "Core CPI — excludes food and energy"),
    Indicator("PCEPI", "Headline PCE", "Inflation", "Index", "Monthly",
              "Personal Consumption Expenditures price index"),
    Indicator("PCEPILFE", "Core PCE", "Inflation", "Index", "Monthly",
              "Core PCE — Fed's preferred inflation measure"),
    Indicator("T5YIE", "5Y Breakeven", "Inflation", "%", "Daily",
              "5-year breakeven inflation expectations from TIPS"),
    Indicator("T10YIE", "10Y Breakeven", "Inflation", "%", "Daily",
              "10-year breakeven inflation expectations from TIPS"),
    Indicator("PPIACO", "PPI All Commodities", "Inflation", "Index", "Monthly",
              "Producer Price Index — upstream inflation pressure"),

    # === Growth ================================================================
    Indicator("GDPC1", "Real GDP", "Growth", "$B", "Quarterly",
              "Real Gross Domestic Product"),
    Indicator("INDPRO", "Industrial Production", "Growth", "Index", "Monthly",
              "Industrial production index"),
    Indicator("RSXFS", "Retail Sales", "Growth", "$M", "Monthly",
              "Retail sales ex food services"),
    Indicator("PAYEMS", "Nonfarm Payrolls", "Growth", "Thousands", "Monthly",
              "Total nonfarm payroll employment"),
    Indicator("ICSA", "Initial Claims", "Growth", "Number", "Weekly",
              "Initial unemployment insurance claims"),
    Indicator("UNRATE", "Unemployment Rate", "Growth", "%", "Monthly",
              "Civilian unemployment rate"),
    Indicator("UMCSENT", "Consumer Sentiment", "Growth", "Index", "Monthly",
              "U Michigan Consumer Sentiment Index"),

    # === Manufacturing & Housing ==============================================
    Indicator("HOUST", "Housing Starts", "Activity", "Thousands", "Monthly",
              "New privately-owned housing units started"),
    Indicator("PERMIT", "Building Permits", "Activity", "Thousands", "Monthly",
              "New private housing units authorized by building permits"),

    # === Commodities & Dollar =================================================
    Indicator("DCOILWTICO", "WTI Crude Oil", "Commodities & Dollar", "$/bbl", "Daily",
              "West Texas Intermediate spot price"),
    Indicator("DCOILBRENTEU", "Brent Crude", "Commodities & Dollar", "$/bbl", "Daily",
              "Brent crude oil spot price"),
    Indicator("DHHNGSP", "Natural Gas", "Commodities & Dollar", "$/MMBtu", "Daily",
              "Henry Hub natural gas spot price"),
    Indicator("GOLDAMGBD228NLBM", "Gold", "Commodities & Dollar", "$/oz", "Daily",
              "Gold fixing price, London"),
    Indicator("DTWEXBGS", "Dollar Index (Broad)", "Commodities & Dollar", "Index", "Daily",
              "Trade-weighted broad dollar index"),

    # === Credit & Risk ========================================================
    Indicator("BAMLH0A0HYM2", "HY Credit Spread", "Credit & Risk", "% pts", "Daily",
              "ICE BofA US High Yield Index option-adjusted spread"),
    Indicator("BAMLC0A0CM", "IG Credit Spread", "Credit & Risk", "% pts", "Daily",
              "ICE BofA US Corporate Investment Grade option-adjusted spread"),
    Indicator("VIXCLS", "VIX", "Credit & Risk", "Index", "Daily",
              "CBOE Volatility Index"),
    Indicator("NFCI", "Financial Conditions", "Credit & Risk", "Index", "Weekly",
              "Chicago Fed National Financial Conditions Index — neg = loose"),
)


# Lookup helpers
INDICATORS_BY_ID: dict[str, Indicator] = {i.series_id: i for i in INDICATORS}
CATEGORIES: tuple[str, ...] = tuple(
    sorted({i.category for i in INDICATORS},
           key=lambda c: list(dict.fromkeys(i.category for i in INDICATORS)).index(c))
)


def indicators_in(category: str) -> list[Indicator]:
    return [i for i in INDICATORS if i.category == category]


class FredClient:
    """Thin wrapper around fredapi.Fred with caching of recent calls."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.fred_api_key
        if not self.api_key:
            raise RuntimeError(
                "FRED_API_KEY missing. Get a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html and "
                "add it to .env"
            )
        try:
            from fredapi import Fred
        except ImportError as e:
            raise ImportError(
                "fredapi is required. Install with: pip install fredapi"
            ) from e
        self._fred = Fred(api_key=self.api_key)
        self._cache: dict[tuple, pd.Series] = {}

    def get_series(
        self,
        series_id: str,
        periods: int | None = 252,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.Series:
        """Fetch a single series, optionally limited to `periods` most recent observations.

        If both `start` and `end` are None, defaults to the last `periods` business days
        ending today.
        """
        cache_key = (series_id, periods, start, end)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if start is None and end is None and periods is not None:
            # Use a generous lookback to absorb any non-business-day padding
            end_dt = datetime.today()
            start_dt = end_dt - timedelta(days=int(periods * 1.6) + 30)
            start = start_dt.strftime("%Y-%m-%d")
            end = end_dt.strftime("%Y-%m-%d")

        try:
            data = self._fred.get_series(
                series_id, observation_start=start, observation_end=end
            )
        except Exception as e:
            log.warning("FRED fetch failed for %s: %s", series_id, e)
            return pd.Series(dtype=float, name=series_id)

        data.name = series_id
        if periods is not None and len(data) > periods:
            data = data.tail(periods)
        self._cache[cache_key] = data
        return data

    def get_many(
        self,
        series_ids: Iterable[str],
        periods: int | None = 252,
    ) -> pd.DataFrame:
        """Fetch multiple series and return as a DataFrame (one column per series)."""
        frames = {}
        for sid in series_ids:
            s = self.get_series(sid, periods=periods)
            if not s.empty:
                frames[sid] = s
        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames)

    def latest_value(self, series_id: str) -> tuple[float | None, pd.Timestamp | None]:
        """Most recent non-null value + its date for a series."""
        s = self.get_series(series_id, periods=20)
        s = s.dropna()
        if s.empty:
            return None, None
        return float(s.iloc[-1]), s.index[-1]

    def snapshot(self, indicators: Iterable[Indicator] | None = None) -> pd.DataFrame:
        """Pull latest value + 1-week change for each indicator.

        Returns a DataFrame with columns: series_id, name, category, value,
        as_of, change_1w, units.
        """
        indicators = list(indicators or INDICATORS)
        rows = []
        for ind in indicators:
            s = self.get_series(ind.series_id, periods=15).dropna()
            if s.empty:
                rows.append({
                    "series_id": ind.series_id,
                    "name": ind.name,
                    "category": ind.category,
                    "units": ind.units,
                    "value": None,
                    "as_of": None,
                    "change_1w": None,
                })
                continue
            value = float(s.iloc[-1])
            as_of = s.index[-1]
            # 1-week change: 5 business days back if available
            change_1w = None
            if len(s) >= 6:
                prior = float(s.iloc[-6])
                change_1w = value - prior
            rows.append({
                "series_id": ind.series_id,
                "name": ind.name,
                "category": ind.category,
                "units": ind.units,
                "value": value,
                "as_of": as_of,
                "change_1w": change_1w,
            })
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 11-sector macro map
# ---------------------------------------------------------------------------

# bias: +1 = rising series is bullish for the sector, -1 = rising is bearish
SECTOR_MACRO_MAP: dict[str, dict] = {
    "Energy": {
        "description": "Oil and gas prices, industrial demand, and the dollar are the primary macro drivers for Energy.",
        "bull_when":   "Oil/gas prices rising, dollar weakening, industrial output expanding",
        "bear_when":   "Oil/gas prices falling, dollar strengthening, industrial contraction",
        "series": ["DCOILWTICO", "DCOILBRENTEU", "DHHNGSP", "DTWEXBGS", "INDPRO"],
        "bias":   {"DCOILWTICO": +1, "DCOILBRENTEU": +1, "DHHNGSP": +1,
                   "DTWEXBGS": -1, "INDPRO": +1},
    },
    "Materials": {
        "description": "Commodity prices, the dollar, and industrial demand drive Materials sector returns.",
        "bull_when":   "Gold/commodities rising, weak dollar, expanding industrial output, PPI rising",
        "bear_when":   "Commodity deflation, strong dollar, industrial contraction",
        "series": ["GOLDAMGBD228NLBM", "PPIACO", "DTWEXBGS", "INDPRO", "T10Y2Y"],
        "bias":   {"GOLDAMGBD228NLBM": +1, "PPIACO": +1, "DTWEXBGS": -1,
                   "INDPRO": +1, "T10Y2Y": +1},
    },
    "Industrials": {
        "description": "GDP growth, employment trends, and industrial output directly drive Industrials earnings.",
        "bull_when":   "Expanding industrial production, falling claims, rising payrolls, normal yield curve",
        "bear_when":   "Contracting industrial output, rising unemployment claims, inverted curve",
        "series": ["INDPRO", "PAYEMS", "ICSA", "T10Y2Y", "GDPC1"],
        "bias":   {"INDPRO": +1, "PAYEMS": +1, "ICSA": -1, "T10Y2Y": +1, "GDPC1": +1},
    },
    "Consumer Discretionary": {
        "description": "Consumer spending power, confidence, employment, and interest rates drive discretionary demand.",
        "bull_when":   "Strong retail sales, high consumer sentiment, low unemployment, falling mortgage rates",
        "bear_when":   "Weak spending, falling confidence, high rates, rising unemployment",
        "series": ["RSXFS", "UMCSENT", "UNRATE", "MORTGAGE30US", "CPIAUCSL"],
        "bias":   {"RSXFS": +1, "UMCSENT": +1, "UNRATE": -1, "MORTGAGE30US": -1,
                   "CPIAUCSL": -1},
    },
    "Consumer Staples": {
        "description": "Defensive sector; volumes tied to employment while high inflation compresses margins.",
        "bull_when":   "Moderating inflation, stable employment, steady consumer demand",
        "bear_when":   "High/rising inflation compressing margins, deteriorating employment",
        "series": ["CPIAUCSL", "CPILFESL", "UMCSENT", "UNRATE", "PAYEMS"],
        "bias":   {"CPIAUCSL": -1, "CPILFESL": -1, "UMCSENT": +1,
                   "UNRATE": -1, "PAYEMS": +1},
    },
    "Health Care": {
        "description": "Relatively defensive; rates and employment affect insurance access; medical inflation impacts costs.",
        "bull_when":   "Falling rates, strong employment, moderating medical cost inflation",
        "bear_when":   "Rising rates, high medical cost inflation, weak employment",
        "series": ["CPILFESL", "PCEPILFE", "DFF", "UNRATE", "PAYEMS"],
        "bias":   {"CPILFESL": -1, "PCEPILFE": -1, "DFF": -1,
                   "UNRATE": -1, "PAYEMS": +1},
    },
    "Financials": {
        "description": "Net interest margins, yield curve shape, credit spreads, and volatility are the core drivers.",
        "bull_when":   "Steep yield curve, tight spreads, low VIX, loose financial conditions",
        "bear_when":   "Inverted curve, wide credit spreads, high VIX, tight financial conditions",
        "series": ["T10Y2Y", "BAMLH0A0HYM2", "BAMLC0A0CM", "VIXCLS", "NFCI", "DFF"],
        "bias":   {"T10Y2Y": +1, "BAMLH0A0HYM2": -1, "BAMLC0A0CM": -1,
                   "VIXCLS": -1, "NFCI": -1, "DFF": +1},
    },
    "Information Technology": {
        "description": "Long-duration growth assets sensitive to interest rates; VIX and risk appetite drive multiples.",
        "bull_when":   "Falling long-end rates, low VIX, strong consumer sentiment, risk-on environment",
        "bear_when":   "Rising rates compressing multiples, risk-off, high VIX",
        "series": ["DGS10", "T10Y2Y", "VIXCLS", "UMCSENT", "NFCI"],
        "bias":   {"DGS10": -1, "T10Y2Y": +1, "VIXCLS": -1,
                   "UMCSENT": +1, "NFCI": -1},
    },
    "Communication Services": {
        "description": "Ad revenue and streaming subscriptions tied to consumer health; rate-sensitive growth.",
        "bull_when":   "Strong consumer spending and sentiment, low VIX, falling long rates",
        "bear_when":   "Weak consumer environment, ad budget cuts, rising rates, risk-off",
        "series": ["UMCSENT", "RSXFS", "UNRATE", "DGS10", "VIXCLS"],
        "bias":   {"UMCSENT": +1, "RSXFS": +1, "UNRATE": -1,
                   "DGS10": -1, "VIXCLS": -1},
    },
    "Utilities": {
        "description": "Rate-sensitive dividend proxies; natural gas costs drive electricity margins.",
        "bull_when":   "Falling long rates and fed funds, low natural gas prices, loose financial conditions",
        "bear_when":   "Rising rates, high energy input costs, tight credit",
        "series": ["DGS10", "DFF", "DHHNGSP", "NFCI", "MORTGAGE30US"],
        "bias":   {"DGS10": -1, "DFF": -1, "DHHNGSP": -1,
                   "NFCI": -1, "MORTGAGE30US": -1},
    },
    "Real Estate": {
        "description": "Highly rate-sensitive; mortgage rates, housing activity, and credit conditions are key.",
        "bull_when":   "Falling mortgage/long rates, rising permits and starts, loose financial conditions",
        "bear_when":   "High mortgage rates, falling housing starts/permits, tight credit",
        "series": ["MORTGAGE30US", "HOUST", "PERMIT", "DGS10", "NFCI"],
        "bias":   {"MORTGAGE30US": -1, "HOUST": +1, "PERMIT": +1,
                   "DGS10": -1, "NFCI": -1},
    },
}

SECTORS: list[str] = list(SECTOR_MACRO_MAP.keys())


def sector_macro_signal(
    sector: str,
    snapshot_df: pd.DataFrame,
) -> dict:
    """Derive a macro signal for a sector from the FRED snapshot.

    Returns a dict with keys:
      signal         : "BULLISH" | "NEUTRAL" | "BEARISH"
      score          : float in [-1, +1]
      indicator_rows : list[dict] for the validation DataTable
      description    : str
      bull_when      : str
      bear_when      : str
    """
    profile = SECTOR_MACRO_MAP.get(sector)
    if profile is None:
        return {"signal": "NEUTRAL", "score": 0.0, "indicator_rows": [],
                "description": "", "bull_when": "", "bear_when": ""}

    bias_map: dict[str, int] = profile["bias"]
    relevant_ids: list[str] = profile["series"]

    rows_by_id: dict[str, dict] = {}
    if not snapshot_df.empty:
        for _, row in snapshot_df.iterrows():
            sid = row.get("series_id")
            if sid in relevant_ids:
                rows_by_id[sid] = row.to_dict()

    contributions: list[float] = []
    indicator_rows: list[dict] = []

    for sid in relevant_ids:
        ind = INDICATORS_BY_ID.get(sid)
        if ind is None:
            continue

        r = rows_by_id.get(sid, {})
        value    = r.get("value")
        change   = r.get("change_1w")
        as_of    = r.get("as_of")
        units    = ind.units

        latest_str = _fmt_snap_value(value, units)
        change_str = _fmt_snap_change(change)

        # Compute contribution based on change direction × bias
        contribution = 0.0
        reading = "—"
        reading_tone = "neutral"
        if change is not None:
            try:
                chg = float(change)
                b = bias_map.get(sid, 0)
                if chg != 0 and b != 0:
                    contribution = 1.0 if (chg > 0) == (b > 0) else -1.0
                    reading = "Bullish signal" if contribution > 0 else "Bearish signal"
                    reading_tone = "good" if contribution > 0 else "bad"
            except (TypeError, ValueError):
                pass

        if contribution != 0.0:
            contributions.append(contribution)

        indicator_rows.append({
            "name":          ind.name,
            "series_id":     sid,
            "latest":        latest_str,
            "change_1w":     change_str,
            "reading":       reading,
            "reading_tone":  reading_tone,
            "as_of":         _fmt_snap_date(as_of),
        })

    # Overall score
    score = (sum(contributions) / len(contributions)) if contributions else 0.0
    score = max(-1.0, min(1.0, score))

    if score > 0.2:
        signal = "BULLISH"
    elif score < -0.2:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    return {
        "signal":         signal,
        "score":          round(score, 3),
        "indicator_rows": indicator_rows,
        "description":    profile["description"],
        "bull_when":      profile["bull_when"],
        "bear_when":      profile["bear_when"],
    }


def _fmt_snap_value(value, units: str) -> str:
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


def _fmt_snap_change(change) -> str:
    if change is None:
        return "—"
    try:
        return f"{float(change):+.3f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_snap_date(d) -> str:
    if d is None:
        return "—"
    try:
        return d.strftime("%Y-%m-%d")
    except Exception:
        return str(d)[:10]


def regime_classification(snapshot_df: pd.DataFrame) -> dict[str, str]:
    """Lightweight regime read from a snapshot DataFrame.

    Returns a dict of {dimension: label}. Dimensions:
      - growth: 'expansion' | 'slowing' | 'contraction'
      - inflation: 'cooling' | 'stable' | 'hot'
      - liquidity: 'easy' | 'neutral' | 'tight'
      - risk: 'on' | 'neutral' | 'off'
      - curve: 'steepening' | 'flat' | 'inverted'
    """
    def get(series_id: str) -> float | None:
        row = snapshot_df[snapshot_df["series_id"] == series_id]
        if row.empty:
            return None
        v = row.iloc[0]["value"]
        return float(v) if v is not None and not pd.isna(v) else None

    out: dict[str, str] = {}

    # Curve — direct from T10Y2Y
    spread = get("T10Y2Y")
    if spread is None:
        out["curve"] = "n/a"
    elif spread < 0:
        out["curve"] = "inverted"
    elif spread < 0.5:
        out["curve"] = "flat"
    else:
        out["curve"] = "normal"

    # Liquidity — NFCI: negative = loose, positive = tight
    nfci = get("NFCI")
    if nfci is None:
        out["liquidity"] = "n/a"
    elif nfci < -0.25:
        out["liquidity"] = "easy"
    elif nfci > 0.25:
        out["liquidity"] = "tight"
    else:
        out["liquidity"] = "neutral"

    # Risk — VIX + HY spread combo
    vix = get("VIXCLS")
    hy = get("BAMLH0A0HYM2")
    if vix is None and hy is None:
        out["risk"] = "n/a"
    else:
        risk_score = 0
        if vix is not None:
            risk_score += 1 if vix < 18 else (-1 if vix > 25 else 0)
        if hy is not None:
            risk_score += 1 if hy < 4.0 else (-1 if hy > 6.0 else 0)
        out["risk"] = "on" if risk_score >= 1 else ("off" if risk_score <= -1 else "neutral")

    # Growth — claims trend + unemployment level (rough proxy without trend data)
    claims = get("ICSA")
    unrate = get("UNRATE")
    if unrate is None:
        out["growth"] = "n/a"
    elif unrate < 4.0:
        out["growth"] = "expansion"
    elif unrate < 5.0:
        out["growth"] = "slowing"
    else:
        out["growth"] = "contraction"

    # Inflation — core PCE level vs 2.0 / 3.0 thresholds (latest YoY would be better,
    # but level-based heuristic works as a placeholder; refine with YoY computation)
    core_pce = get("PCEPILFE")
    if core_pce is None:
        out["inflation"] = "n/a"
    else:
        # Heuristic placeholder — real implementation should compute YoY
        out["inflation"] = "tracking"

    return out
