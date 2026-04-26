"""PDF text extraction with section + sector detection.

Uses pdfplumber for both narrative text and tables. Sections are detected
via header heuristics (line starting with a known section keyword, often
in caps or numbered). Sector mentions are matched against the canonical
sector list with alias resolution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ada_research.data.lm_lexicon import SECTOR_ALIASES, SECTORS
from ada_research.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class ExtractedDocument:
    """Output of PDF extraction."""

    path: Path
    full_text: str
    sections: dict[str, str] = field(default_factory=dict)
    sector_mentions: dict[str, list[str]] = field(default_factory=dict)
    page_count: int = 0
    table_count: int = 0


# Section keywords — narrative-style, case-insensitive
_SECTION_KEYWORDS = (
    "commentary", "performance", "outlook", "risk", "risks",
    "summary", "overview", "highlights", "results",
    "macro", "rates", "credit", "equity", "fixed income",
    "themes", "positioning", "strategy",
)

_SECTION_HEADER_RE = re.compile(
    rf"^\s*(?:\d+\.?\s*)?({'|'.join(_SECTION_KEYWORDS)})\b[:\s]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Sentence splitter — quick & good-enough for sector grouping
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def extract_pdf(path: Path) -> ExtractedDocument:
    """Extract text + sections + sector mentions from a PDF."""
    try:
        import pdfplumber
    except ImportError as e:
        raise ImportError(
            "pdfplumber is required for PDF extraction. "
            "Install with: pip install pdfplumber"
        ) from e

    path = Path(path)
    text_parts: list[str] = []
    table_count = 0
    page_count = 0

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
            try:
                tables = page.extract_tables() or []
                table_count += len(tables)
            except Exception as e:
                log.debug("table extraction failed on a page: %s", e)

    full_text = "\n\n".join(text_parts)
    sections = _detect_sections(full_text)
    sector_mentions = _detect_sectors(full_text)

    log.info(
        "extracted %s: %d pages, %d sections, %d sector mentions, %d tables",
        path.name,
        page_count,
        len(sections),
        len(sector_mentions),
        table_count,
    )

    return ExtractedDocument(
        path=path,
        full_text=full_text,
        sections=sections,
        sector_mentions=sector_mentions,
        page_count=page_count,
        table_count=table_count,
    )


def _detect_sections(text: str) -> dict[str, str]:
    """Split full text into named sections using header regex.

    If no headers match, returns a single 'Body' section with all content.
    """
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return {"Body": text.strip()}

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip().title()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()

    return sections


def _detect_sectors(text: str) -> dict[str, list[str]]:
    """Find all sentences mentioning each canonical sector.

    Returns a dict of sector → list of sentences. Aliases are resolved
    to the canonical name.
    """
    sentences = _split_sentences(text)
    out: dict[str, list[str]] = {}

    # Build a single regex per sector covering its name + aliases
    patterns: list[tuple[str, re.Pattern]] = []
    for sector in SECTORS:
        terms = [re.escape(sector)]
        terms.extend(re.escape(a) for a, c in SECTOR_ALIASES.items() if c == sector)
        pattern = re.compile(
            r"\b(?:" + "|".join(terms) + r")\b",
            re.IGNORECASE,
        )
        patterns.append((sector, pattern))

    for sentence in sentences:
        for sector, pattern in patterns:
            if pattern.search(sentence):
                out.setdefault(sector, []).append(sentence)
                # Don't break — a sentence can mention multiple sectors

    return out


def _split_sentences(text: str) -> Iterable[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]
