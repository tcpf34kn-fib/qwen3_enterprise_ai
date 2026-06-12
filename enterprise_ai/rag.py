from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SearchHit:
    title: str
    path: str
    score: float
    snippet: str
    citation: str
    chunk_id: str
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "path": self.path,
            "score": round(self.score, 4),
            "snippet": self.snippet,
            "citation": self.citation,
            "chunk_id": self.chunk_id,
            "metadata": self.metadata,
        }


@dataclass
class DocumentChunk:
    title: str
    path: str
    chunk_id: str
    text: str
    line_start: int
    line_end: int
    metadata: dict[str, str]
    token_counts: Counter[str]

    @property
    def citation(self) -> str:
        return f"{Path(self.path).name}:L{self.line_start}-L{self.line_end}"


class LocalRagService:
    """Local chunked retrieval with metadata, ACL, and line citations.

    This is intentionally dependency-light for demos and air-gapped labs. For a
    larger production corpus, keep this interface and replace the implementation
    with Chroma, Qdrant, FAISS, or another vector store plus local embeddings.
    """

    def __init__(self, knowledge_base_path: str) -> None:
        self.knowledge_base_path = Path(knowledge_base_path)
        self.chunks = self._load_chunks()
        self.document_frequency = _document_frequency(self.chunks)

    def search(self, query: str, limit: int = 3, roles: set[str] | None = None) -> list[SearchHit]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        query_counts = Counter(query_terms)
        hits: list[SearchHit] = []
        for chunk in self.chunks:
            if not _role_allowed(chunk.metadata, roles):
                continue

            score = self._score_chunk(chunk, query_counts)
            if score <= 0:
                continue

            hits.append(
                SearchHit(
                    title=chunk.title,
                    path=chunk.path,
                    score=score,
                    snippet=_snippet(chunk.text, query_terms),
                    citation=chunk.citation,
                    chunk_id=chunk.chunk_id,
                    metadata=chunk.metadata,
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    def answer_from_docs(self, query: str, roles: set[str] | None = None) -> dict[str, object]:
        hits = self.search(query, roles=roles)
        if not hits:
            return {
                "answer": "No matching internal document was found. Escalate if this is operationally sensitive.",
                "sources": [],
            }

        excerpts = [f"[{hit.citation}] {hit.snippet}" for hit in hits]
        return {
            "answer": "Relevant internal guidance: " + " ".join(excerpts),
            "sources": [hit.to_dict() for hit in hits],
        }

    def _load_chunks(self) -> list[DocumentChunk]:
        if not self.knowledge_base_path.exists():
            return []

        chunks: list[DocumentChunk] = []
        for path in sorted(self.knowledge_base_path.glob("*.md")):
            raw_text = path.read_text(encoding="utf-8")
            metadata, text, source_line_offset = _split_front_matter(raw_text)
            title = _title_from_markdown(text) or path.stem.replace("_", " ").title()
            chunks.extend(_chunk_document(title, path, text, metadata, source_line_offset=source_line_offset))
        return chunks

    def _score_chunk(self, chunk: DocumentChunk, query_counts: Counter[str]) -> float:
        total_chunks = max(1, len(self.chunks))
        score = 0.0
        for term, query_count in query_counts.items():
            term_frequency = chunk.token_counts.get(term, 0)
            if not term_frequency:
                continue

            doc_frequency = self.document_frequency.get(term, 0)
            inverse_doc_frequency = math.log((1 + total_chunks) / (1 + doc_frequency)) + 1.0
            score += query_count * term_frequency * inverse_doc_frequency

        lowered = chunk.text.lower()
        for phrase in _query_phrases(query_counts):
            if phrase in lowered:
                score += 2.5
        return score


def _document_frequency(chunks: list[DocumentChunk]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for chunk in chunks:
        counts.update(set(chunk.token_counts.keys()))
    return counts


def _chunk_document(
    title: str,
    path: Path,
    text: str,
    metadata: dict[str, str],
    max_lines: int = 10,
    source_line_offset: int = 0,
) -> list[DocumentChunk]:
    lines = text.splitlines()
    chunks: list[DocumentChunk] = []
    current: list[tuple[int, str]] = []

    def flush() -> None:
        if not current:
            return
        line_start = current[0][0]
        line_end = current[-1][0]
        chunk_text = "\n".join(line for _, line in current).strip()
        if chunk_text:
            chunk_id = f"{path.stem}:{len(chunks) + 1}"
            chunks.append(
                DocumentChunk(
                    title=title,
                    path=str(path),
                    chunk_id=chunk_id,
                    text=chunk_text,
                    line_start=line_start + source_line_offset,
                    line_end=line_end + source_line_offset,
                    metadata=dict(metadata),
                    token_counts=Counter(_tokenize(chunk_text)),
                )
            )
        current.clear()

    for index, line in enumerate(lines, start=1):
        if line.startswith("## ") and current:
            flush()
        current.append((index, line))
        if len(current) >= max_lines:
            flush()
    flush()
    return chunks


def _split_front_matter(text: str) -> tuple[dict[str, str], str, int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, 0

    metadata: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return metadata, "\n".join(lines[index + 1 :]), index + 1
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip().lower()] = value.strip()
    return metadata, text, 0


def _role_allowed(metadata: dict[str, str], roles: set[str] | None) -> bool:
    allowed = metadata.get("roles")
    if not allowed or not roles:
        return True
    allowed_roles = {role.strip() for role in allowed.split(",") if role.strip()}
    return bool(allowed_roles.intersection(roles))


def _tokenize(value: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9._-]+", value.lower()) if len(term) > 2]


def _query_phrases(query_counts: Counter[str]) -> list[str]:
    terms = list(query_counts.keys())
    return [" ".join(terms[index : index + 2]) for index in range(max(0, len(terms) - 1))]


def _title_from_markdown(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _snippet(text: str, terms: list[str], length: int = 320) -> str:
    lowered = text.lower()
    first = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(0, first - 80)
    return " ".join(text[start : start + length].split())
