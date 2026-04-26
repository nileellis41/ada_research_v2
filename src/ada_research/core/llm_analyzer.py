"""LLM-based sentiment analysis using the Anthropic Claude API."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from ada_research.utils.logger import get_logger

if TYPE_CHECKING:
    from ada_research.core.chunker import TextChunk

logger = get_logger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_CONTEXT_CHARS = 6000

SYSTEM_PROMPT = (
    "You are a financial analyst assistant specializing in sector sentiment analysis "
    "for institutional investment research. You analyze market commentary and return "
    "a structured assessment. Always respond with valid JSON only — no markdown, no "
    "extra text."
)


@dataclass
class FocusSector:
    """A sector the LLM recommends investigating further in Stage 2."""

    name: str           # standardized name matching SECTOR_INDICATORS keys
    direction: str      # "bullish" | "bearish"
    conviction: str     # "high" | "medium" | "low"
    rationale: str      # one-sentence justification


@dataclass
class LLMSectorAnalysis:
    """LLM-generated sentiment analysis for a single sector."""

    sector: str
    score: float          # [-1.0, +1.0]
    signal: str           # STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
    response: str         # 2-3 sentence narrative
    key_themes: list[str] = field(default_factory=list)
    focus_sectors: list[FocusSector] = field(default_factory=list)
    chunks_used: int = 0
    model: str = DEFAULT_MODEL
    available: bool = True


class LLMAnalyzer:
    """Analyze financial text chunks using Claude.

    Degrades gracefully when the ``anthropic`` package is not installed or
    ``ANTHROPIC_API_KEY`` is not set.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def _client_instance(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------
    # Sector sentiment analysis
    # ------------------------------------------------------------------

    def analyze_sector(
        self,
        sector: str,
        chunks: list["TextChunk"],
    ) -> LLMSectorAnalysis:
        """Run LLM analysis on *chunks* for *sector*."""
        if not self.is_available():
            return self._unavailable(sector, "no API key or anthropic not installed")

        context_parts: list[str] = []
        total_chars = 0
        for chunk in chunks:
            if total_chars + len(chunk.text) > MAX_CONTEXT_CHARS:
                break
            context_parts.append(chunk.text)
            total_chars += len(chunk.text)

        if not context_parts:
            return self._unavailable(sector, "no text chunks available")

        context = "\n---\n".join(context_parts)

        try:
            client = self._client_instance()
            message = client.messages.create(
                model=self.model,
                max_tokens=512,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": self._sector_prompt(sector, context)}],
            )
            data = json.loads(_strip_code_fence(message.content[0].text.strip()))

            score = float(max(-1.0, min(1.0, data.get("score", 0.0))))
            return LLMSectorAnalysis(
                sector=sector,
                score=round(score, 3),
                signal=data.get("signal", _score_to_signal(score)),
                response=str(data.get("response", "")),
                key_themes=list(data.get("key_themes", [])),
                chunks_used=len(context_parts),
                model=self.model,
                available=True,
            )

        except Exception as exc:
            logger.warning(f"LLM analysis failed for {sector}: {exc}")
            return self._unavailable(sector, str(exc))

    # ------------------------------------------------------------------
    # Focus sector extraction (for Stage 2 hand-off)
    # ------------------------------------------------------------------

    def extract_focus_sectors(self, text: str) -> list[FocusSector]:
        """Identify which sectors from *text* deserve Stage 2 macro investigation."""
        if not self.is_available():
            return []

        context = text[:MAX_CONTEXT_CHARS]

        try:
            client = self._client_instance()
            message = client.messages.create(
                model=self.model,
                max_tokens=512,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": self._focus_prompt(context)}],
            )
            data = json.loads(_strip_code_fence(message.content[0].text.strip()))

            results: list[FocusSector] = []
            for item in data.get("focus_sectors", []):
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                direction = str(item.get("direction", "bullish")).lower()
                conviction = str(item.get("conviction", "medium")).lower()
                rationale = str(item.get("rationale", ""))
                if name:
                    results.append(FocusSector(
                        name=name,
                        direction=direction if direction in ("bullish", "bearish") else "bullish",
                        conviction=conviction if conviction in ("high", "medium", "low") else "medium",
                        rationale=rationale,
                    ))
            return results[:4]

        except Exception as exc:
            logger.warning(f"Focus sector extraction failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    @staticmethod
    def _sector_prompt(sector: str, context: str) -> str:
        return (
            f"Analyze the following financial market commentary about the **{sector}** sector.\n\n"
            f"Text:\n{context}\n\n"
            "Return JSON with exactly these fields:\n"
            "{\n"
            '  "score": <float -1.0 to 1.0, -1 = very bearish, +1 = very bullish>,\n'
            '  "signal": <"STRONG_BUY"|"BUY"|"HOLD"|"SELL"|"STRONG_SELL">,\n'
            '  "response": <2-3 sentence narrative for an institutional investor>,\n'
            '  "key_themes": <list of 3-5 concise themes>\n'
            "}"
        )

    @staticmethod
    def _focus_prompt(context: str) -> str:
        return (
            "Read the following financial market commentary and identify which market sectors "
            "have the clearest directional signals — either strongly bullish or strongly bearish — "
            "and would most benefit from macro data validation.\n\n"
            f"Text:\n{context}\n\n"
            "Return JSON with exactly this structure:\n"
            "{\n"
            '  "focus_sectors": [\n'
            '    {\n'
            '      "name": <sector name, e.g. "Energy", "Metals", "Financials">,\n'
            '      "direction": <"bullish" or "bearish">,\n'
            '      "conviction": <"high", "medium", or "low">,\n'
            '      "rationale": <one sentence citing specific evidence from the text>\n'
            '    }\n'
            "  ]\n"
            "}\n\n"
            "List up to 4 sectors ordered by conviction (highest first). "
            "Only include sectors with a clear directional signal in the text."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _unavailable(self, sector: str, reason: str) -> LLMSectorAnalysis:
        return LLMSectorAnalysis(
            sector=sector,
            score=0.0,
            signal="HOLD",
            response=f"LLM analysis unavailable: {reason}.",
            key_themes=[],
            focus_sectors=[],
            chunks_used=0,
            model=self.model,
            available=False,
        )


# ------------------------------------------------------------------
# Module helpers
# ------------------------------------------------------------------

def _strip_code_fence(text: str) -> str:
    text = re.sub(r"^```[a-z]*\n?", "", text)
    return text.rstrip("`").strip()


def _score_to_signal(score: float) -> str:
    if score > 0.5:
        return "STRONG_BUY"
    elif score > 0.2:
        return "BUY"
    elif score > -0.2:
        return "HOLD"
    elif score > -0.5:
        return "SELL"
    return "STRONG_SELL"
