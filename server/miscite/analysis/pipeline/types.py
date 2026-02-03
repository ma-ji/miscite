from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedWork:
    doi: str | None
    title: str | None
    abstract: str | None
    year: int | None
    journal: str | None
    publisher: str | None
    issn: str | None
    is_retracted: bool | None
    retraction_detail: dict | None
    openalex_id: str | None
    openalex_record: dict | None
    openalex_match: dict | None
    crossref_match: dict | None
    pmid: str | None
    pmcid: str | None
    pubmed_record: dict | None
    pubmed_match: dict | None
    arxiv_id: str | None
    arxiv_record: dict | None
    arxiv_match: dict | None
    source: str | None
    confidence: float
    resolution_notes: str
