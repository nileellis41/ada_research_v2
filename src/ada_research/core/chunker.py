"""Text chunking and TF-IDF embedding for financial report text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class TextChunk:
    """A chunk of text with metadata and an optional TF-IDF embedding."""

    text: str
    chunk_idx: int
    start_char: int
    end_char: int
    sector_tags: list[str] = field(default_factory=list)
    embedding: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class TextChunker:
    """Split text into overlapping word-based chunks and compute TF-IDF embeddings.

    Usage:
        chunker = TextChunker(chunk_size=400, overlap=50)
        chunks = chunker.chunk_and_embed(full_text, sector_list)
        relevant = chunker.retrieve_for_sector(chunks, "Energy", top_k=5)
    """

    def __init__(self, chunk_size: int = 400, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._vocab: dict[str, int] = {}
        self._idf: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_text(
        self,
        text: str,
        sector_list: Optional[list[str]] = None,
    ) -> list[TextChunk]:
        """Split *text* into overlapping word-based chunks."""
        text = re.sub(r"\s+", " ", text).strip()
        words = text.split()
        if not words:
            return []

        char_offsets = self._build_char_offsets(text, words)
        step = max(1, self.chunk_size - self.overlap)
        chunks: list[TextChunk] = []

        for i in range(0, len(words), step):
            chunk_words = words[i : i + self.chunk_size]
            if not chunk_words:
                break

            start_char = char_offsets[i]
            end_word_idx = min(i + len(chunk_words) - 1, len(words) - 1)
            end_char = char_offsets[end_word_idx] + len(words[end_word_idx])

            chunk_text = " ".join(chunk_words)

            tags: list[str] = []
            if sector_list:
                lower = chunk_text.lower()
                for sector in sector_list:
                    if sector.lower() in lower:
                        tags.append(sector)

            chunks.append(
                TextChunk(
                    text=chunk_text,
                    chunk_idx=len(chunks),
                    start_char=start_char,
                    end_char=end_char,
                    sector_tags=tags,
                )
            )

        return chunks

    def _build_char_offsets(self, text: str, words: list[str]) -> list[int]:
        offsets: list[int] = []
        pos = 0
        for word in words:
            while pos < len(text) and text[pos].isspace():
                pos += 1
            offsets.append(pos)
            pos += len(word)
        return offsets

    # ------------------------------------------------------------------
    # Embedding (TF-IDF)
    # ------------------------------------------------------------------

    def embed_chunks(self, chunks: list[TextChunk]) -> list[TextChunk]:
        """Compute L2-normalised TF-IDF vectors and attach them to *chunks*."""
        if not chunks:
            return chunks

        corpus = [self._tokenize(c.text) for c in chunks]

        # Build vocabulary
        all_terms: set[str] = set()
        for tokens in corpus:
            all_terms.update(tokens)
        self._vocab = {term: idx for idx, term in enumerate(sorted(all_terms))}

        vocab_size = len(self._vocab)
        n_docs = len(corpus)

        # Term-frequency matrix
        tf = np.zeros((n_docs, vocab_size), dtype=np.float32)
        for di, tokens in enumerate(corpus):
            if not tokens:
                continue
            counts: dict[str, int] = {}
            for tok in tokens:
                counts[tok] = counts.get(tok, 0) + 1
            for term, cnt in counts.items():
                tf[di, self._vocab[term]] = cnt / len(tokens)

        # IDF with smoothing
        doc_freq = (tf > 0).sum(axis=0)
        self._idf = np.log((n_docs + 1) / (doc_freq + 1)) + 1.0

        tfidf = tf * self._idf

        # L2 normalise
        norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        tfidf /= norms

        for chunk, vec in zip(chunks, tfidf):
            chunk.embedding = vec

        return chunks

    def chunk_and_embed(
        self,
        text: str,
        sector_list: Optional[list[str]] = None,
    ) -> list[TextChunk]:
        """Chunk text and compute TF-IDF embeddings in one pass."""
        chunks = self.chunk_text(text, sector_list)
        return self.embed_chunks(chunks)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve_for_sector(
        self,
        chunks: list[TextChunk],
        sector: str,
        top_k: int = 5,
    ) -> list[TextChunk]:
        """Return the *top_k* chunks most relevant to *sector*."""
        if not chunks:
            return []

        if self._vocab and self._idf is not None:
            query_tokens = self._tokenize(f"{sector} sector performance outlook")
            query_vec = np.zeros(len(self._vocab), dtype=np.float32)
            for tok in query_tokens:
                if tok in self._vocab:
                    query_vec[self._vocab[tok]] += 1.0

            if query_vec.sum() > 0:
                query_vec = query_vec * self._idf
                norm = np.linalg.norm(query_vec)
                if norm > 0:
                    query_vec /= norm

            scored: list[tuple[float, TextChunk]] = []
            for chunk in chunks:
                sim = float(np.dot(query_vec, chunk.embedding)) if chunk.embedding is not None else 0.0
                if sector in chunk.sector_tags:
                    sim += 0.3
                scored.append((sim, chunk))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [c for _, c in scored[:top_k]]

        # Fallback: tagged chunks first, then by index
        tagged = [c for c in chunks if sector in c.sector_tags]
        rest = [c for c in chunks if sector not in c.sector_tags]
        return (tagged + rest)[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return [tok for tok in text.split() if len(tok) > 2]
