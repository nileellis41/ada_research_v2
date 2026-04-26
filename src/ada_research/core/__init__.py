"""Core pipeline + clients."""
from ada_research.core.pipeline import (
    SectorAnalysis,
    Stage1Results,
    run_pipeline_on_pdf,
    run_pipeline_on_text,
)
from ada_research.core.sentiment_analyzer import (
    SentimentScore,
    aggregate_scores,
    score_text,
)

__all__ = [
    "SectorAnalysis",
    "Stage1Results",
    "SentimentScore",
    "aggregate_scores",
    "run_pipeline_on_pdf",
    "run_pipeline_on_text",
    "score_text",
]
