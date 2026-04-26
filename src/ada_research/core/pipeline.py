"""Stage 1 pipeline: PDF → sentiment → sector signals + TF-IDF chunking + LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ada_research.core.pdf_extractor import ExtractedDocument, extract_pdf
from ada_research.core.sentiment_analyzer import (
    SentimentScore,
    aggregate_scores,
    score_text,
)
from ada_research.utils.logger import get_logger

if TYPE_CHECKING:
    from ada_research.core.chunker import TextChunk
    from ada_research.core.llm_analyzer import LLMSectorAnalysis

log = get_logger(__name__)


@dataclass
class SectorAnalysis:
    """Per-sector aggregate result."""

    sector: str
    sentiment: SentimentScore
    sentence_count: int
    sample_sentences: list[str] = field(default_factory=list)

    @property
    def signal(self) -> str:
        return self.sentiment.signal

    @property
    def compound(self) -> float:
        return self.sentiment.compound

    @property
    def confidence(self) -> float:
        return self.sentiment.confidence


@dataclass
class Stage1Results:
    """Full Stage 1 pipeline output."""

    source: Path | None
    document: ExtractedDocument | None
    overall: SentimentScore
    sectors: list[SectorAnalysis] = field(default_factory=list)
    chunks: list["TextChunk"] = field(default_factory=list)
    llm_analyses: dict[str, "LLMSectorAnalysis"] = field(default_factory=dict)

    @property
    def sector_count(self) -> int:
        return len(self.sectors)

    @property
    def llm_available(self) -> bool:
        return bool(self.llm_analyses) and any(
            a.available for a in self.llm_analyses.values()
        )

    def to_rows(self) -> list[dict]:
        """Flat dict list for CSV / DataFrame export."""
        rows = []
        for s in self.sectors:
            rows.append({
                "sector": s.sector,
                "signal": s.signal,
                "compound": round(s.compound, 4),
                "confidence": round(s.confidence, 4),
                "positive_score": round(s.sentiment.positive, 2),
                "negative_score": round(s.sentiment.negative, 2),
                "uncertainty": round(s.sentiment.uncertainty, 4),
                "sentence_count": s.sentence_count,
                "tokens": s.sentiment.token_count,
            })
        return rows


def run_pipeline_on_pdf(path: Path | str) -> Stage1Results:
    """Run the full pipeline on a PDF file."""
    path = Path(path)
    log.info("running pipeline on %s", path)
    doc = extract_pdf(path)
    return _run_on_document(doc, source=path)


def run_pipeline_on_text(text: str, sector_name: str | None = None) -> Stage1Results:
    """Run the pipeline on raw text. Used for the 'Analyze excerpt' panel.

    If sector_name is given, the result has a single SectorAnalysis tagged
    with that name. Otherwise all detected sectors are scored.
    LLM analysis is not run for direct text input (no document to chunk).
    """
    overall = score_text(text)

    if sector_name:
        sectors = [
            SectorAnalysis(
                sector=sector_name,
                sentiment=overall,
                sentence_count=1,
                sample_sentences=[text[:240]],
            )
        ]
    else:
        from ada_research.core.pdf_extractor import _detect_sectors

        sector_mentions = _detect_sectors(text)
        sectors = _score_sectors(sector_mentions)

    return Stage1Results(source=None, document=None, overall=overall, sectors=sectors)


def _run_on_document(doc: ExtractedDocument, source: Path) -> Stage1Results:
    overall = score_text(doc.full_text)
    sectors = _score_sectors(doc.sector_mentions)

    from ada_research.core.chunker import TextChunker
    from ada_research.core.llm_analyzer import LLMAnalyzer

    sector_names = [s.sector for s in sectors]

    # Chunk + embed the full document text for retrieval
    chunker = TextChunker(chunk_size=400, overlap=50)
    chunks = chunker.chunk_and_embed(doc.full_text, sector_names)
    log.info("chunked document into %d chunks", len(chunks))

    # LLM analysis per sector (skipped gracefully when API key absent)
    llm = LLMAnalyzer()
    llm_analyses: dict = {}
    if llm.is_available():
        log.info("LLM analysis with %s", llm.model)
        for sector in sector_names:
            relevant = chunker.retrieve_for_sector(chunks, sector, top_k=5)
            result = llm.analyze_sector(sector, relevant)
            llm_analyses[sector] = result
            log.debug(
                "LLM %s: score=%+.3f signal=%s chunks=%d",
                sector, result.score, result.signal, result.chunks_used,
            )
        log.info("LLM: analyzed %d sectors", len(llm_analyses))
    else:
        log.info("LLM: skipped (ANTHROPIC_API_KEY not set or anthropic not installed)")

    return Stage1Results(
        source=source,
        document=doc,
        overall=overall,
        sectors=sectors,
        chunks=chunks,
        llm_analyses=llm_analyses,
    )


def _score_sectors(sector_mentions: dict[str, list[str]]) -> list[SectorAnalysis]:
    out: list[SectorAnalysis] = []
    for sector, sentences in sector_mentions.items():
        if not sentences:
            continue
        per_sentence_scores = [score_text(s) for s in sentences]
        agg = aggregate_scores(per_sentence_scores)
        out.append(
            SectorAnalysis(
                sector=sector,
                sentiment=agg,
                sentence_count=len(sentences),
                sample_sentences=sentences[:3],
            )
        )
    # Sort by absolute conviction (compound), so strongest signals float to top
    out.sort(key=lambda s: abs(s.compound), reverse=True)
    return out
