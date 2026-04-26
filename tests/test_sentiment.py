"""Tests for the core sentiment logic.

These exercise the pipeline's ground truth without touching Qt or any
external API. Run with: pytest tests/ -v
"""
import pytest

from ada_research.core.sentiment_analyzer import (
    SIGNAL_THRESHOLDS,
    aggregate_scores,
    score_text,
    tokenize,
)


class TestTokenize:
    def test_basic_words(self):
        assert tokenize("Hello world") == ["hello", "world"]

    def test_strips_punctuation(self):
        assert tokenize("Profits, losses, gains.") == ["profits", "losses", "gains"]

    def test_keeps_hyphens(self):
        # Hyphenated terms remain a single token (best-in-class is in lexicon)
        assert "best-in-class" in tokenize("It's best-in-class quality.")

    def test_empty(self):
        assert tokenize("") == []
        assert tokenize("   ") == []

    def test_strips_numbers(self):
        # Numbers are not tokens. Single-letter words are also dropped
        # (the regex requires 2+ alpha characters), which is intentional —
        # it filters noise like "Q" / "B" without losing meaningful tokens.
        assert tokenize("Q3 2024 results") == ["results"]
        assert tokenize("growth of 12% in 2024") == ["growth", "of", "in"]


class TestPositiveSentiment:
    def test_strong_positive_text(self):
        text = "Revenue surged with strong outperformance and robust growth across all segments."
        s = score_text(text)
        assert s.positive > s.negative
        assert s.compound > 0
        assert s.signal in ("BUY", "STRONG_BUY")

    def test_records_positive_hits(self):
        s = score_text("strong rally with momentum")
        assert "rally" in s.positive_hits
        assert "strong" in s.positive_hits
        assert "momentum" in s.positive_hits


class TestNegativeSentiment:
    def test_strong_negative_text(self):
        text = "Significant losses and impairments amid weak demand and severe headwinds."
        s = score_text(text)
        assert s.negative > s.positive
        assert s.compound < 0
        assert s.signal in ("SELL", "STRONG_SELL")

    def test_records_negative_hits(self):
        s = score_text("decline and weakness with concerns")
        assert "decline" in s.negative_hits
        assert "weakness" in s.negative_hits


class TestNegation:
    def test_negation_flips_positive_to_negative(self):
        positive = score_text("strong performance")
        negated = score_text("not strong performance")
        # The negated version should score lower than the un-negated one
        assert negated.compound < positive.compound

    def test_negation_flips_negative_to_positive(self):
        negative = score_text("severe weakness")
        negated = score_text("no weakness")
        assert negated.compound > negative.compound

    def test_negation_window(self):
        # Negation should only carry 3 tokens; a sentence with negation
        # far from the sentiment word should not flip.
        close = score_text("not strong")
        far = score_text("not the very obviously and clearly strong")
        # 'far' has too many intervening tokens, so 'strong' stays positive
        assert close.compound < far.compound


class TestIntensity:
    def test_intensity_amplifies(self):
        # Use longer text so compound doesn't saturate at the ±1.0 clip
        base = score_text(
            "the quarterly report from the regional division noted strong "
            "demand among partners and customers in domestic markets"
        )
        intense = score_text(
            "the quarterly report from the regional division noted very strong "
            "demand among partners and customers in domestic markets"
        )
        # 'very' has multiplier 1.4 — should lift the compound score
        assert intense.compound > base.compound

    def test_dampener_reduces(self):
        # Use longer text so compound doesn't saturate
        base = score_text(
            "the quarterly report from the regional division noted strong "
            "demand among partners and customers in domestic markets"
        )
        slight = score_text(
            "the quarterly report from the regional division noted slightly strong "
            "demand among partners and customers in domestic markets"
        )
        # 'slightly' has multiplier 0.6 — should lower the compound score
        assert slight.compound < base.compound


class TestSignalMapping:
    @pytest.mark.parametrize("compound,expected", [
        (0.9,  "STRONG_BUY"),
        (0.6,  "STRONG_BUY"),
        (0.5,  "STRONG_BUY"),    # boundary
        (0.4,  "BUY"),
        (0.2,  "BUY"),            # boundary
        (0.1,  "HOLD"),
        (0.0,  "HOLD"),
        (-0.1, "HOLD"),
        (-0.2, "HOLD"),           # boundary (>= -0.2 is HOLD)
        (-0.3, "SELL"),
        (-0.5, "SELL"),           # boundary
        (-0.7, "STRONG_SELL"),
    ])
    def test_threshold_mapping(self, compound, expected):
        from ada_research.core.sentiment_analyzer import _compound_to_signal
        assert _compound_to_signal(compound) == expected

    def test_signal_in_score_result(self):
        s = score_text("rally surged outperformance momentum gains")
        assert s.signal in ("BUY", "STRONG_BUY")


class TestAggregate:
    def test_aggregate_empty(self):
        agg = aggregate_scores([])
        assert agg.compound == 0.0
        assert agg.signal == "HOLD"

    def test_aggregate_weighted_by_tokens(self):
        # Two scores: one positive, one negative, with different token counts.
        # Aggregate should be weighted by token_count.
        positive = score_text("strong robust outperformance gains rally surged")
        negative_short = score_text("decline weak")
        agg = aggregate_scores([positive, negative_short])
        # Positive has way more tokens, so aggregate should be positive
        assert agg.compound > 0


class TestEdgeCases:
    def test_empty_text(self):
        s = score_text("")
        assert s.compound == 0.0
        assert s.signal == "HOLD"
        assert s.token_count == 0

    def test_no_sentiment_words(self):
        s = score_text("the company released its quarterly report yesterday afternoon")
        assert s.compound == 0.0
        assert s.signal == "HOLD"

    def test_confidence_increases_with_density(self):
        sparse = score_text("the company reported some growth across many regions worldwide")
        dense = score_text("strong growth surged outperformance rally")
        assert dense.confidence > sparse.confidence
