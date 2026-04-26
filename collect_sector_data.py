"""Sprint 2 — Sector / Industry / Movers data collector.

Mirrors sprint2_sectors_industries_movers.ipynb.
Runs standalone: python collect_sector_data.py

Fetches all 11 endpoints and prints formatted summaries.
Pass --save to write CSV files to outputs/sector_data/.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

# Make src/ importable when run directly from the project root
SRC = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")


def _header(title: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def _latest_business_day() -> str:
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def run(save: bool = False) -> None:
    from ada_research.core.fmp_client import FmpClient
    import pandas as pd

    c = FmpClient()
    snap_date = _latest_business_day()
    today     = date.today().isoformat()
    from_90   = (date.today() - timedelta(days=90)).isoformat()
    from_180  = (date.today() - timedelta(days=180)).isoformat()

    out_dir = Path(__file__).parent / "outputs" / "sector_data"
    if save:
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Saving CSVs to {out_dir}/")

    print(f"\nSnapshot date: {snap_date}")

    # ── 1. Sector performance snapshot ──────────────────────────────────
    _header("1. Sector Performance Snapshot")
    df_sector = c.sector_snapshot(snap_date)
    if not df_sector.empty:
        df_sector["averageChange"] = pd.to_numeric(df_sector["averageChange"], errors="coerce")
        df_s = df_sector.sort_values("averageChange", ascending=False)
        print(df_s[["sector", "averageChange"]].to_string(index=False))
        if save:
            df_s.to_csv(out_dir / "sector_snapshot.csv", index=False)
    else:
        print("No data returned.")

    # ── 2. Industry performance snapshot ────────────────────────────────
    _header("2. Industry Performance Snapshot")
    df_industry = c.industry_snapshot(snap_date)
    if not df_industry.empty:
        df_industry["averageChange"] = pd.to_numeric(df_industry["averageChange"], errors="coerce")
        print(f"Total industries: {len(df_industry)}")
        print("\nTop 10:")
        print(df_industry.nlargest(10, "averageChange")[["industry", "averageChange"]].to_string(index=False))
        print("\nBottom 10:")
        print(df_industry.nsmallest(10, "averageChange")[["industry", "averageChange"]].to_string(index=False))
        if save:
            df_industry.sort_values("averageChange", ascending=False).to_csv(
                out_dir / "industry_snapshot.csv", index=False
            )
    else:
        print("No data returned.")

    # ── 3. Historical sector performance (all 11 sectors, 90 days) ──────
    _header("3. Historical Sector Performance (last 90 days)")
    sectors = df_sector["sector"].tolist() if not df_sector.empty else []
    for sector in sectors:
        df_hs = c.historical_sector(sector, days=90)
        if not df_hs.empty:
            df_hs["averageChange"] = pd.to_numeric(df_hs["averageChange"], errors="coerce")
            df_hs = df_hs.sort_values("date")
            latest_row = df_hs.iloc[-1]
            mtd_sum    = df_hs.tail(22)["averageChange"].sum()
            print(f"  {sector:<28} latest: {latest_row['averageChange']:+.3f}%  "
                  f"MTD sum: {mtd_sum:+.2f}%  rows: {len(df_hs)}")
            if save:
                safe = sector.replace(" ", "_").replace("/", "_")
                df_hs.to_csv(out_dir / f"hist_sector_{safe}.csv", index=False)
        else:
            print(f"  {sector:<28} no data")

    # ── 4. Sector P/E snapshot ───────────────────────────────────────────
    _header("4. Sector P/E Snapshot")
    df_spe = c.sector_pe(snap_date)
    if not df_spe.empty and "pe" in df_spe.columns:
        df_spe["pe"] = pd.to_numeric(df_spe["pe"], errors="coerce")
        df_spe = df_spe[(df_spe["pe"] > 0) & (df_spe["pe"] < 500)]
        print(df_spe.sort_values("pe", ascending=False)[["sector", "pe"]].to_string(index=False))
        if save:
            df_spe.to_csv(out_dir / "sector_pe_snapshot.csv", index=False)
    else:
        print("No data returned.")

    # ── 5. Industry P/E snapshot ─────────────────────────────────────────
    _header("5. Industry P/E Snapshot")
    df_ipe = c.industry_pe(snap_date)
    if not df_ipe.empty and "pe" in df_ipe.columns:
        df_ipe["pe"] = pd.to_numeric(df_ipe["pe"], errors="coerce")
        clean = df_ipe[(df_ipe["pe"] > 0) & (df_ipe["pe"] < 500)]
        print(f"Total: {len(df_ipe)}  (valid PE: {len(clean)})")
        print("\nHighest P/E:")
        print(clean.nlargest(10, "pe")[["industry", "pe"]].to_string(index=False))
        print("\nLowest P/E:")
        print(clean.nsmallest(10, "pe")[["industry", "pe"]].to_string(index=False))
        if save:
            df_ipe.sort_values("pe", ascending=False).to_csv(
                out_dir / "industry_pe_snapshot.csv", index=False
            )
    else:
        print("No data returned.")

    # ── 6. Historical sector P/E (all sectors, 180 days) ─────────────────
    _header("6. Historical Sector P/E (last 180 days)")
    for sector in sectors:
        df_hspe = c.historical_sector_pe(sector, days=180)
        if not df_hspe.empty and "pe" in df_hspe.columns:
            df_hspe["pe"] = pd.to_numeric(df_hspe["pe"], errors="coerce")
            df_hspe = df_hspe.dropna(subset=["pe"]).sort_values("date")
            if len(df_hspe) >= 2:
                lo  = df_hspe["pe"].min()
                hi  = df_hspe["pe"].max()
                cur = df_hspe["pe"].iloc[-1]
                print(f"  {sector:<28} current: {cur:.1f}x  range: [{lo:.1f}–{hi:.1f}]  "
                      f"rows: {len(df_hspe)}")
            if save:
                safe = sector.replace(" ", "_").replace("/", "_")
                df_hspe.to_csv(out_dir / f"hist_sector_pe_{safe}.csv", index=False)
        else:
            print(f"  {sector:<28} no data")

    # ── 7. Biggest Gainers ───────────────────────────────────────────────
    _header("7. Biggest Gainers (today)")
    df_g = c.gainers()
    if not df_g.empty:
        cols = [c for c in ("symbol", "name", "price", "changesPercentage") if c in df_g.columns]
        print(df_g[cols].head(20).to_string(index=False))
        if save:
            df_g.to_csv(out_dir / "gainers.csv", index=False)
    else:
        print("No data returned.")

    # ── 8. Biggest Losers ────────────────────────────────────────────────
    _header("8. Biggest Losers (today)")
    df_l = c.losers()
    if not df_l.empty:
        cols = [c for c in ("symbol", "name", "price", "changesPercentage") if c in df_l.columns]
        print(df_l[cols].head(20).to_string(index=False))
        if save:
            df_l.to_csv(out_dir / "losers.csv", index=False)
    else:
        print("No data returned.")

    # ── 9. Most Active ───────────────────────────────────────────────────
    _header("9. Most Active (today)")
    df_a = c.most_actives()
    if not df_a.empty:
        cols = [c for c in ("symbol", "name", "price", "changesPercentage") if c in df_a.columns]
        print(df_a[cols].head(20).to_string(index=False))
        if save:
            df_a.to_csv(out_dir / "most_actives.csv", index=False)
    else:
        print("No data returned.")

    if save:
        print(f"\nAll CSVs written to {out_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Sprint 2 sector/industry data")
    parser.add_argument("--save", action="store_true", help="Write CSV files to outputs/sector_data/")
    args = parser.parse_args()
    run(save=args.save)
