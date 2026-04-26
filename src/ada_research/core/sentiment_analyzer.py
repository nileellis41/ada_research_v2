"""Loughran-McDonald sentiment analyzer.

Scoring approach:
1. Tokenize text into words (lowercased, alphanumeric).
2. For each token, check whether it's in POSITIVE_WORDS or NEGATIVE_WORDS.
3. Look back up to 3 tokens for a NEGATION_WORD — if found, flip the sign.
4. Look back 1 token for an INTENSITY_MULTIPLIER — if found, multiply.
5. Compound score = (pos_score - neg_score) / sqrt(token_count).
6. Confidence = min(1.0, total_sentiment_words / max(1, token_count) * 5).

Returns a `SentimentScore` dataclass — never a dict.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from ada_research.data.lm_lexicon import (
    INTENSITY_MULTIPLIERS,
    NEGATION_WORDS,
    NEGATIVE_WORDS,
    POSITIVE_WORDS,
    UNCERTAINTY_WORDS,
)


# Range of `compound` that maps to each signal label.
SIGNAL_THRESHOLDS: list[tuple[float, str]] = [
    (0.5,  "STRONG_BUY"),
    (0.2,  "BUY"),
    (-0.2, "HOLD"),
    (-0.5, "SELL"),
]
# Anything below SIGNAL_THRESHOLDS[-1][0] becomes STRONG_SELL.


@dataclass
class SentimentScore:
    """Result of scoring a piece of text."""

    text: str
    positive: float
    negative: float
    uncertainty: float
    compound: float
    confidence: float
    signal: str
    positive_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)
    token_count: int = 0


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")


def tokenize(text: str) -> list[str]:
    """Lowercase tokenize. Hyphens preserved (so 'best-in-class' stays one token)."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def score_text(text: str) -> SentimentScore:
    """Score a single block of text.

    The look-back window for negation is 3 tokens; for intensity it's 1.
    These are tunable but track standard NLP heuristics.
    """
    tokens = tokenize(text)
    n = len(tokens)
    if n == 0:
        return SentimentScore(
            text=text,
            positive=0.0,
            negative=0.0,
            uncertainty=0.0,
            compound=0.0,
            confidence=0.0,
            signal="HOLD",
            token_count=0,
        )

    pos_score = 0.0
    neg_score = 0.0
    unc_count = 0
    pos_hits: list[str] = []
    neg_hits: list[str] = []

    for i, tok in enumerate(tokens):
        if tok in UNCERTAINTY_WORDS:
            unc_count += 1

        is_pos = tok in POSITIVE_WORDS
        is_neg = tok in NEGATIVE_WORDS
        if not (is_pos or is_neg):
            continue

        # Base weight is 1.0; adjust for intensity preceding word
        weight = 1.0
        if i > 0 and tokens[i - 1] in INTENSITY_MULTIPLIERS:
            weight *= INTENSITY_MULTIPLIERS[tokens[i - 1]]

        # Negation flip — search 3 tokens back
        negated = any(
            tokens[j] in NEGATION_WORDS
            for j in range(max(0, i - 3), i)
        )
        if negated:
            is_pos, is_neg = is_neg, is_pos

        if is_pos:
            pos_score += weight
            pos_hits.append(tok)
        else:
            neg_score += weight
            neg_hits.append(tok)

    # Compound: net sentiment normalized by sqrt(N) so longer texts don't dominate.
    raw_compound = (pos_score - neg_score) / math.sqrt(max(1, n))
    # Clip to [-1, 1] for stability of downstream signal mapping.
    compound = max(-1.0, min(1.0, raw_compound))

    sentiment_word_count = len(pos_hits) + len(neg_hits)
    confidence = min(1.0, sentiment_word_count / max(1, n) * 5.0)

    signal = _compound_to_signal(compound)

    return SentimentScore(
        text=text,
        positive=pos_score,
        negative=neg_score,
        uncertainty=unc_count / max(1, n),
        compound=compound,
        confidence=confidence,
        signal=signal,
        positive_hits=pos_hits,
        negative_hits=neg_hits,
        token_count=n,
    )


def _compound_to_signal(compound: float) -> str:
    for threshold, label in SIGNAL_THRESHOLDS:
        if compound >= threshold:
            return label
    return "STRONG_SELL"


def aggregate_scores(scores: Iterable[SentimentScore]) -> SentimentScore:
    """Combine multiple sentiment scores into a single weighted result.

    Weighted by token_count so a 1000-word section counts more than a
    20-word one. Returns a SentimentScore with text="(aggregate)".
    """
    scores = list(scores)
    if not scores:
        return SentimentScore(
            text="(aggregate)",
            positive=0.0,
            negative=0.0,
            uncertainty=0.0,
            compound=0.0,
            confidence=0.0,
            signal="HOLD",
        )

    total_tokens = sum(s.token_count for s in scores) or 1

    pos_total = sum(s.positive for s in scores)
    neg_total = sum(s.negative for s in scores)
    unc_weighted = sum(s.uncertainty * s.token_count for s in scores) / total_tokens

    compound_weighted = sum(s.compound * s.token_count for s in scores) / total_tokens
    confidence_weighted = sum(s.confidence * s.token_count for s in scores) / total_tokens

    return SentimentScore(
        text="(aggregate)",
        positive=pos_total,
        negative=neg_total,
        uncertainty=unc_weighted,
        compound=compound_weighted,
        confidence=confidence_weighted,
        signal=_compound_to_signal(compound_weighted),
        positive_hits=[h for s in scores for h in s.positive_hits],
        negative_hits=[h for s in scores for h in s.negative_hits],
        token_count=total_tokens,
    )
