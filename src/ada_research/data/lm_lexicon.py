"""Loughran-McDonald financial sentiment lexicon (curated subset).

The full LM lexicon contains ~2000+ positive and ~2300+ negative terms. This
file contains a working subset (~300 / ~350) covering the highest-frequency
financial sentiment terms. Add more from the master list at:
    https://sraf.nd.edu/loughranmcdonald-master-dictionary/

Lexicons are frozenset for O(1) membership tests.
"""
from __future__ import annotations

POSITIVE_WORDS: frozenset[str] = frozenset({
    # Performance / momentum
    "outperform", "outperformed", "outperforming", "outperformance",
    "rally", "rallied", "rallying", "rebound", "rebounded", "rebounds",
    "surge", "surged", "surging", "soar", "soared", "soaring",
    "advance", "advanced", "advancing",
    "appreciate", "appreciated", "appreciating", "appreciation",
    "strengthen", "strengthened", "strengthening", "strength",
    "robust", "robustness", "resilient", "resilience",
    "momentum", "uptrend", "tailwind", "tailwinds",
    "leadership", "leader", "leading",
    # Fundamentals
    "growth", "grew", "growing", "expand", "expanded", "expanding", "expansion",
    "improve", "improved", "improving", "improvement", "improvements",
    "profitable", "profitability", "profit", "profits",
    "gain", "gains", "gaining", "gained",
    "increase", "increased", "increases", "increasing",
    "exceed", "exceeded", "exceeding", "exceeds",
    "beat", "beats", "beating",
    "upgrade", "upgraded", "upgrades", "upgrading",
    "favorable", "favorably", "constructive",
    "positive", "positively", "optimistic", "optimism",
    "bullish", "bull",
    # Quality / efficiency
    "efficient", "efficiency", "efficiencies",
    "innovative", "innovation", "innovations",
    "accretive", "synergies", "synergistic",
    "sustainable", "sustainability",
    "high-quality", "quality", "premium",
    "best-in-class", "best",
    "successful", "succeed", "succeeded", "succeeding", "success",
    "achieved", "achieving", "achievement", "achievements",
    "strong", "stronger", "strongest", "solid",
    "healthy", "stable", "stability",
    "attractive", "attractively",
    "outpace", "outpacing",
    "milestone", "milestones",
    "pioneer", "pioneering",
    # Capital / yield
    "yield", "yielding",
    "dividend", "dividends",
    "buyback", "buybacks", "repurchase", "repurchased",
    "reward", "rewards", "rewarding",
    # Outlook
    "opportunity", "opportunities",
    "potential", "promising",
    "expected", "expectation", "expectations",
    "guidance", "guide", "guided",
    "raised", "raising", "raise",
    "boost", "boosted", "boosting",
    "accelerate", "accelerated", "accelerating", "acceleration",
    "outlook", "prospects",
    "demand", "robust-demand",
    "recovery", "recovering", "recovered",
    "expansion-mode",
    "outpaced",
    "exceeded-expectations",
    "well-positioned", "positioned",
    "winning", "wins",
    "breakthrough", "breakthroughs",
    "record", "records", "all-time-high", "ath",
    # Sector-specific bullish
    "outflow-reversal", "inflow", "inflows",
    "tailwinded",
    "expansionary",
})


NEGATIVE_WORDS: frozenset[str] = frozenset({
    # Performance / momentum
    "underperform", "underperformed", "underperforming", "underperformance",
    "decline", "declined", "declining", "declines",
    "drop", "dropped", "dropping",
    "fall", "fell", "falling", "falls",
    "plunge", "plunged", "plunging",
    "tumble", "tumbled", "tumbling",
    "slump", "slumped", "slumping",
    "weakness", "weak", "weaken", "weakened", "weakening",
    "headwind", "headwinds", "downtrend",
    "lag", "lagged", "lagging",
    # Fundamentals
    "loss", "losses", "lost", "losing",
    "deficit", "deficits",
    "shortfall", "shortfalls",
    "decrease", "decreased", "decreases", "decreasing",
    "miss", "missed", "missing", "misses",
    "shrink", "shrank", "shrinking", "shrunk",
    "contract", "contracted", "contracting", "contraction",
    "downgrade", "downgraded", "downgrades", "downgrading",
    "negative", "negatively",
    "pessimistic", "pessimism",
    "bearish", "bear",
    # Risk / damage
    "risk", "risks", "risky",
    "concern", "concerns", "concerning",
    "worry", "worried", "worrying", "worries",
    "fear", "fears", "feared",
    "uncertain", "uncertainty", "uncertainties",
    "volatile", "volatility",
    "fragile", "fragility",
    "vulnerable", "vulnerability",
    "exposure", "exposed",
    "stressed", "stress", "distress", "distressed",
    "unstable", "instability",
    "erratic",
    "deteriorate", "deteriorated", "deteriorating", "deterioration",
    "worsen", "worsened", "worsening",
    "impair", "impaired", "impairment", "impairments",
    "writedown", "write-down", "writeoff", "write-off",
    "default", "defaulted", "defaults",
    "bankrupt", "bankruptcy", "insolvent", "insolvency",
    "litigation", "lawsuit", "lawsuits",
    "fraud", "scandal", "scandals",
    "investigation", "investigations",
    "fine", "fined", "fines",
    "penalty", "penalties",
    "violation", "violations",
    "breach", "breached", "breaches",
    "recall", "recalled", "recalls",
    "delay", "delayed", "delays", "delaying",
    "disruption", "disruptions", "disrupted", "disrupting",
    "shortage", "shortages",
    "layoff", "layoffs",
    "restructure", "restructured", "restructuring",
    # Macro
    "recession", "recessionary",
    "downturn", "slowdown", "slowing",
    "stagflation",
    "crisis", "crises",
    "bubble",
    "correction",
    "selloff", "sell-off",
    "crash", "crashed", "crashing",
    "panic",
    "contagion",
    # Outlook
    "lower", "lowered", "lowering",
    "cut", "cuts", "cutting",
    "warning", "warned", "warnings",
    "caution", "cautious", "cautioned",
    "challenge", "challenges", "challenging", "challenged",
    "difficult", "difficulty", "difficulties",
    "tough", "tougher",
    "headwinds-persist",
    "softness", "softening", "softened",
    "muted",
    "tepid",
    "sluggish",
    "anemic",
    "stalled",
    "stagnant", "stagnation",
    # Misc
    "burden", "burdens", "burdened",
    "drag",
    "pressure", "pressured", "pressuring",
    "compress", "compressed", "compressing", "compression",
    "outflow", "outflows",
})


UNCERTAINTY_WORDS: frozenset[str] = frozenset({
    "may", "might", "could", "would", "possibly", "perhaps", "probably",
    "potentially", "potential", "approximately", "approximate",
    "expect", "expects", "expected", "expecting", "expectation",
    "anticipate", "anticipates", "anticipated", "anticipating",
    "estimate", "estimates", "estimated", "estimating",
    "forecast", "forecasts", "forecasted", "forecasting",
    "project", "projected", "projecting", "projection",
    "assume", "assumed", "assuming", "assumption", "assumptions",
    "depend", "depends", "depending", "dependent",
    "subject-to", "contingent",
    "if", "unless", "whether",
    "uncertain", "unclear", "ambiguous",
    "approximately", "around", "roughly",
})


# Words that flip sentiment of the next 1–3 tokens.
NEGATION_WORDS: frozenset[str] = frozenset({
    "not", "no", "never", "none", "neither", "nor",
    "without", "lack", "lacking", "lacks",
    "fail", "failed", "fails", "failing",
    "absent", "absence",
    "cannot", "can't", "won't", "wouldn't",
    "shouldn't", "couldn't", "didn't", "doesn't", "don't",
})


# Multipliers applied when these words precede a sentiment term.
INTENSITY_MULTIPLIERS: dict[str, float] = {
    "very": 1.4,
    "extremely": 1.6,
    "significantly": 1.5,
    "substantially": 1.5,
    "materially": 1.4,
    "considerably": 1.4,
    "notably": 1.3,
    "particularly": 1.3,
    "highly": 1.3,
    "strongly": 1.4,
    "greatly": 1.4,
    "remarkably": 1.4,
    "exceptionally": 1.5,
    "increasingly": 1.2,
    "moderately": 0.7,
    "slightly": 0.6,
    "somewhat": 0.7,
    "marginally": 0.5,
    "barely": 0.5,
}


# Sectors we can detect in narrative. Order matters for first-match wins.
SECTORS: tuple[str, ...] = (
    "Energy",
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Healthcare",
    "Financials",
    "Information Technology",
    "Technology",
    "Communication Services",
    "Utilities",
    "Real Estate",
)


# Aliases / common variants → canonical sector name.
SECTOR_ALIASES: dict[str, str] = {
    "tech": "Technology",
    "it": "Technology",
    "info tech": "Technology",
    "infotech": "Technology",
    "consumer disc": "Consumer Discretionary",
    "discretionary": "Consumer Discretionary",
    "staples": "Consumer Staples",
    "health": "Healthcare",
    "health care": "Healthcare",
    "financial": "Financials",
    "banks": "Financials",
    "telecom": "Communication Services",
    "utility": "Utilities",
    "reit": "Real Estate",
    "reits": "Real Estate",
    "industrial": "Industrials",
    "material": "Materials",
}
