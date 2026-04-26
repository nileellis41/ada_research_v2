# Ada Research

**Top-down financial research workbench. PyQt6 desktop app, six tabs, fully offline-capable for Stage 1.**

This is the multi-stage extension of [Ada_research](https://github.com/nileellis41/Ada_research). Stage 1 (PDF sentiment) is unchanged in spirit. Stages 2–5 are now implemented as additional tabs alongside the original work.

---

## Why PyQt6

This is a desktop application, not a web app. The reasoning:

* **Native performance** — no browser overhead, no HTTP round-trips for the UI
* **Offline by default** — no server, no ports, nothing listening
* **Proper drag-and-drop** — OS-level file integration
* **Financial tooling standard** — Bloomberg Terminal, Refinitiv Eikon, and most professional trading platforms are built on Qt
* **Real threading** — background data fetches without blocking the UI
* **Single binary path forward** — packagable with PyInstaller into a standalone `.app` / `.exe`

---

## Six tabs, self-contained

Each tab is independent. If a tab's API key is missing, it shows a configuration prompt — the rest of the app stays usable.

| Tab | Source | Key needed | Description |
|-----|--------|-----------|-------------|
| **Stage 1 · Sentiment** | PDF + LM lexicon | none | Drag-and-drop PDF → sector BUY/HOLD/SELL signals |
| **Stage 2 · Macro** | FRED | `FRED_API_KEY` | ~30 macro indicators across 6 categories + regime read |
| **Sprint 1 · Market** | FMP | `FMP_API_KEY` | Quote, history, volatility, MA trend for any ticker |
| **Sprint 2 · Sectors** | FMP | `FMP_API_KEY` | Sector/industry performance, P/E, gainers/losers/actives |
| **Sprint 3 · Analysts** | FMP | `FMP_API_KEY` | Price targets, BHS distribution, recent grade actions |
| **Sprint 4 · Screener** | FMP | `FMP_API_KEY` | 6 named presets (large_cap_stable, dividend_income, tech_growth, etc.) |

**Stage 1 needs no keys.** Clone the repo, install, run — works fully offline.

---

## Project layout

```
ada_research/
├── pyproject.toml              # Modern packaging (pip install -e .)
├── requirements.txt            # Direct pip install
├── .env.example                # API key template
├── run.py                      # Launch without installing
│
├── src/ada_research/
│   ├── app.py                  # Entry point
│   │
│   ├── core/                   # Stateless logic
│   │   ├── pdf_extractor.py    # pdfplumber wrapper + section parsing
│   │   ├── sentiment_analyzer.py
│   │   ├── pipeline.py         # Stage1Pipeline orchestrator
│   │   ├── fred_client.py      # FRED + curated indicator catalog
│   │   └── fmp_client.py       # FMP /stable/ endpoints
│   │
│   ├── tabs/                   # One file per tab
│   │   ├── stage1_sentiment.py
│   │   ├── stage2_macro.py
│   │   ├── sprint1_market.py
│   │   ├── sprint2_sectors.py
│   │   ├── sprint3_analysts.py
│   │   └── sprint4_screener.py
│   │
│   ├── ui/
│   │   ├── main_window.py      # QTabWidget host
│   │   ├── widgets.py          # Card, StatCard, SignalBadge, PlaceholderPanel
│   │   ├── workers.py          # QObject-moved-to-thread workers
│   │   └── theme.py            # Single-file dark theme stylesheet
│   │
│   ├── data/lm_lexicon.py
│   └── utils/{config.py, logger.py}
│
├── tests/test_sentiment.py
├── data/                       # Input PDFs (gitignored)
└── outputs/                    # Exported CSVs / JSON (gitignored)
```

---

## Setup

### Prerequisites

* Python 3.10+
* macOS, Linux, or Windows

### Install

```bash
cd ada_research

# Recommended: virtualenv
python3 -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt

# Or install as a package (enables the `ada-research` CLI command)
pip install -e .
```

### Configure API keys (optional)

```bash
cp .env.example .env
# Edit .env to add FRED_API_KEY and/or FMP_API_KEY
```

Both are free:
* FRED: https://fred.stlouisfed.org/docs/api/api_key.html
* FMP: https://site.financialmodelingprep.com/

### Run

```bash
# Without installation
python run.py

# Or, after `pip install -e .`
ada-research
```

---

## Stage 1 — PDF Sentiment Analysis

Drag a PDF onto the upload zone (or click Browse). The pipeline:

1. Extracts text + tables using `pdfplumber`
2. Detects section headers (Commentary, Performance, Risk, etc.)
3. For each canonical sector mentioned, pulls related sentences
4. Scores with the Loughran-McDonald financial sentiment lexicon (negation + intensity)
5. Generates BUY / HOLD / SELL per sector

The "Analyze text directly" panel takes raw text and returns a single score, optionally tagged to a sector.

**Signal mapping:**

| Compound | Signal |
| --- | --- |
| > +0.5 | STRONG_BUY |
| +0.2 to +0.5 | BUY |
| −0.2 to +0.2 | HOLD |
| −0.5 to −0.2 | SELL |
| < −0.5 | STRONG_SELL |

Export to CSV/JSON via the buttons in the results header.

---

## Stage 2 — Macro Validation

Pulls ~30 curated FRED series across 6 categories:

| Category | Indicators |
|----------|-----------|
| **Rates & Curve** | DFF, DGS3MO, DGS2, DGS10, T10Y2Y, T10Y3M, MORTGAGE30US, SOFR |
| **Inflation** | CPIAUCSL, CPILFESL, PCEPI, PCEPILFE, T5YIE, T10YIE, PPIACO |
| **Growth** | GDPC1, INDPRO, RSXFS, PAYEMS, ICSA, UNRATE, UMCSENT |
| **Activity** | HOUST, PERMIT |
| **Commodities & Dollar** | DCOILWTICO, DCOILBRENTEU, DHHNGSP, GOLD, DTWEXBGS |
| **Credit & Risk** | BAMLH0A0HYM2, BAMLC0A0CM, VIXCLS, NFCI |

Top-of-tab **regime read**: curve shape (normal/flat/inverted), liquidity (easy/neutral/tight), risk (on/neutral/off), growth (expansion/slowing/contraction), inflation tracking. Color-coded so a glance tells you the macro setup.

To extend: add an `Indicator(...)` entry to the catalog in `core/fred_client.py`. It auto-appears in the right category tab on next load.

---

## Sprints 1–4 — FMP Data

All four use FMP's `/stable/` endpoints (legacy `/api/v3/` retired Aug 2025).

* **Sprint 1 (Market)** — single ticker quote + 1Y history, with annualized volatility and 50/200-day MA trend.
* **Sprint 2 (Sectors)** — 5 sub-tabs: sector perf, industry perf, sector P/E, industry P/E, movers (gainers/losers/actives).
* **Sprint 3 (Analysts)** — single ticker: price target consensus (high/median/consensus/low), BHS distribution, recent grade actions.
* **Sprint 4 (Screener)** — preset dropdown: `large_cap_stable`, `dividend_income`, `tech_growth`, `small_cap_movers`, `defensive`, `aggressive`. Configurable result limit. Tables are sortable.

---

## Architecture notes

**Dataclass-driven core.** `Stage1Results`, `SectorAnalysis`, `SentimentScore`, `Indicator` are all `@dataclass` types. Returns are typed objects, not dicts. The UI consumes typed attributes; the core is testable in isolation and usable from notebooks.

**QObject-moved-to-QThread.** The modern Qt pattern, not `QThread.run()` subclassing. Signals/slots play nicely; lifecycle cleanup is straightforward (see `ui/workers.py::run_in_thread`).

**Single-file stylesheet.** Theme consistency lives in `ui/theme.py`. Tabs reference `COLORS["good"] / ["bad"] / ["warn"]` for tone-coded values. To swap to a light theme, edit one file.

**`src/` layout.** Prevents the import-from-project-root foot-gun where tests import the in-development copy instead of the installed copy.

**Self-contained tabs.** Each tab checks its required key at construction and shows a `PlaceholderPanel` if the key is missing — the app never crashes for missing config.

---

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

Covers the core sentiment logic: positive/negative scoring, negation flipping, intensity amplification, signal boundary mapping, aggregation weighting.

---

## Customizing the lexicon

Add words to `src/ada_research/data/lm_lexicon.py`:

```python
POSITIVE_WORDS = frozenset({
    ...,  # existing
    "my_custom_bullish_term",
})
```

For intensity modifiers:

```python
INTENSITY_MULTIPLIERS = {
    ...,
    "extremely": 1.6,
}
```

---

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+1`..`Ctrl+6` | Jump to tab |
| `Ctrl+Q` | Quit |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'PyQt6'`**
→ `pip install -r requirements.txt`

**PyQt6 fails to install on Linux**
→ Install Qt deps: `sudo apt install libxcb-cursor0 libxcb-xinerama0`

**Qt platform plugin error on Linux**
→ `export QT_QPA_PLATFORM=xcb`

**PDF produces no sectors**
→ The PDF is likely image-only (scanned). Run OCR first: `ocrmypdf input.pdf output.pdf`.

**Macro tab says "FRED_API_KEY not set" after editing .env**
→ Restart the app; `.env` is loaded once at startup. Or click the Reload button on the placeholder.

---

## Roadmap

This implements Stages 1–2 of the original 5-stage plan and adds the four data sprints from the FMP exploration notebooks. Still ahead:

* **Stage 3 — Cross-validation.** Wire macro reality back into Stage 1 sector signals (e.g., suppress an Energy BUY if WTI is in a downtrend).
* **Stage 4 — Fundamentals + DCF.** Pull statements, compute ROIC / FCF margin, run a 2-stage DCF.
* **Stage 5 — ML forecast.** GradientBoostingRegressor on price/macro/fundamental features, regime-conditioned, with confidence bands.

---

## License

MIT.
