from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchHit:
    title: str
    path: str
    score: int
    snippet: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "title": self.title,
            "path": self.path,
            "score": self.score,
            "snippet": self.snippet,
        }


@dataclass
class Document:
    title: str
    path: str
    text: str


class LocalRagService:
    def __init__(self, knowledge_base_path: str) -> None:
        self.knowledge_base_path = Path(knowledge_base_path)
        self.documents = self._load_documents()

    def search(self, query: str, limit: int = 3) -> list[SearchHit]:
        terms = _tokenize(query)
        hits: list[SearchHit] = []
        for document in self.documents:
            haystack = document.text.lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                hits.append(
                    SearchHit(
                        title=document.title,
                        path=document.path,
                        score=score,
                        snippet=_snippet(document.text, terms),
                    )
                )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    def answer_from_docs(self, query: str) -> dict[str, object]:
        hits = self.search(query)
        if not hits:
            return {
                "answer": "No matching internal document was found. Escalate if this is operationally sensitive.",
                "sources": [],
            }

        answer = "Relevant internal guidance: " + " ".join(hit.snippet for hit in hits)
        return {
            "answer": answer,
            "sources": [hit.to_dict() for hit in hits],
        }

    def _load_documents(self) -> list[Document]:
        if not self.knowledge_base_path.exists():
            return []

        documents: list[Document] = []
        for path in self.knowledge_base_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            title = _title_from_markdown(text) or path.stem.replace("_", " ").title()
            documents.append(Document(title=title, path=str(path), text=text))
        return documents


def _tokenize(value: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9._-]+", value.lower()) if len(term) > 2]


def _title_from_markdown(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _snippet(text: str, terms: list[str], length: int = 260) -> str:
    lowered = text.lower()
    first = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(0, first - 80)
    snippet = " ".join(text[start : start + length].split())
    return snippet

