from __future__ import annotations

from server.miscite.core.config import Settings


def build_methodology_md(
    settings: Settings,
    *,
    used_sources: list[dict],
    llm_used: bool,
    limitations: list[str],
) -> str:
    lines: list[str] = []
    lines.append("# miscite report methodology")
    lines.append("")
    lines.append("This report is designed to be *traceable* and *transparent*.")
    lines.append("")
    lines.append("## Pipeline")
    backend_label = "Docling" if settings.text_extract_backend == "docling" else "MarkItDown"
    lines.append(f"1) **Text extraction**: extract manuscript content using {backend_label}.")
    lines.append("2) **LLM parsing**: extract in-text citations and bibliography entries into structured records.")
    lines.append(
        "3) **Citation ↔ bibliography matching**: link each in-text citation to a bibliography entry when possible. "
        "Ambiguous matches are tracked (multiple plausible candidates). A configured LLM may be used to conservatively "
        "choose among candidates (or abstain) within a per-job match-call budget."
    )
    lines.append(
        "4) **Reference resolution**: attempt to link bibliography entries to OpenAlex, then Crossref, then PubMed, then arXiv "
        "(PubMed treats explicit PMID/PMCID in the bibliography as strong identifiers when reached). "
        "Each source prefers DOI/ID lookup when available; otherwise it searches by title/author/year. "
        "For ambiguous search results, a configured LLM may be used to conservatively choose a match (or abstain). "
        "Resolution stops after the first matching source."
    )
    lines.append("5) **Objective flags**:")
    lines.append("   - In-text citation missing from bibliography.")
    lines.append("   - In-text citation maps to multiple bibliography candidates (ambiguous match).")
    lines.append("   - Bibliography item unresolved in metadata sources (potentially non-existent / incomplete / non-indexed).")
    lines.append(
        "   - Retracted works (via OpenAlex/Crossref retraction flags when present, plus optional custom retraction API and/or local dataset file)."
    )
    lines.append("   - Predatory venue matches (via optional custom predatory API and/or local dataset file).")
    lines.append("6) **Potentially inappropriate citations**:")
    lines.append("   - Compute a lightweight relevance heuristic between the citing context and the cited work’s title/abstract (when available).")
    if llm_used:
        lines.append("   - For low-relevance cases, optionally ask a configured LLM to classify as appropriate/inappropriate/uncertain.")
    else:
        lines.append("   - No cases required LLM adjudication in this run; only heuristics (and optional local NLI) were applied.")
    lines.append("")
    lines.append("## Data sources used")
    for src in used_sources:
        name = src.get("name", "Unknown")
        detail = src.get("detail", "")
        lines.append(f"- **{name}**: {detail}".strip())
    lines.append("")
    lines.append("## Notes / limitations")
    if limitations:
        for item in limitations:
            lines.append(f"- {item}")
    else:
        lines.append("- None reported.")
    lines.append("")
    lines.append("## Reference inspiration")
    lines.append(
        "This implementation is inspired by the multi-stage, evidence-first approach discussed in "
        "`kb/BibAgent-An-Agentic-Framework-for-Traceable-Miscitation-Detection-in-Scientific-Literature/Preprint-PDF.md`."
    )
    lines.append("")
    lines.append("## Configuration snapshot")
    lines.append(f"- Text extraction backend: `{settings.text_extract_backend}`")
    lines.append(f"- Accelerator: `{settings.accelerator}`")
    lines.append(f"- LLM model: `{settings.llm_model}`")
    lines.append(f"- LLM parse model: `{settings.llm_parse_model}`")
    lines.append(f"- LLM match model: `{settings.llm_match_model}`")
    lines.append(f"- LLM max calls (inappropriate checks): `{settings.llm_max_calls}`")
    lines.append(f"- LLM max calls (match disambiguation): `{settings.llm_match_max_calls}`")
    lines.append(f"- Preprint year gap max: `{settings.preprint_year_gap_max}`")
    lines.append(f"- Billing enabled: `{settings.billing_enabled}`")
    lines.append(f"- Billing cost multiplier: `{settings.billing_cost_multiplier}`")
    lines.append(f"- Billing currency: `{settings.billing_currency}`")
    return "\n".join(lines)
