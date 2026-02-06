from __future__ import annotations

import datetime as dt
import io
import re
import unicodedata
from html import escape
from typing import Any
from typing import Mapping
from urllib.parse import urlparse


_BRAND = "#990000"
_TEXT = "#072332"
_MUTED = "#51616A"
_SURFACE = "#F8EFE2"
_SURFACE_ALT = "#F5E3CC"

_SUMMARY_FIELDS: tuple[tuple[str, str], ...] = (
    ("total_intext_citations", "In-text citations"),
    ("total_citations", "References identified"),
    ("missing_bibliography_refs", "Missing refs"),
    ("ambiguous_bibliography_refs", "Ambiguous refs"),
    ("retracted_references", "Retractions"),
    ("predatory_matches", "Venue risk"),
    ("unresolved_references", "Unresolved"),
    ("potentially_inappropriate", "Potential issues"),
)

_ISSUE_LABELS: dict[str, str] = {
    "missing_bibliography_ref": "Missing bibliography entry",
    "ambiguous_bibliography_ref": "Ambiguous bibliography match",
    "unresolved_reference": "Unresolved reference",
    "retracted_article": "Retracted work cited",
    "predatory_venue_match": "Venue risk match",
    "potentially_inappropriate": "Potentially inappropriate citation",
    "needs_manual_review": "Needs manual review",
}

_ISSUE_DESCRIPTIONS: dict[str, str] = {
    "missing_bibliography_ref": "The in-text citation does not appear in the bibliography list.",
    "ambiguous_bibliography_ref": "The in-text citation matched multiple bibliography entries with low confidence.",
    "unresolved_reference": "The bibliography entry exists but could not be matched to metadata.",
    "retracted_article": "This reference matches a retracted record.",
    "predatory_venue_match": "The journal or publisher matches a venue risk watchlist.",
    "potentially_inappropriate": "The citation context appears misaligned with the cited work.",
    "needs_manual_review": "Automated checks could not verify this citation.",
}

_ISSUE_ACTIONS: dict[str, str] = {
    "missing_bibliography_ref": "Add a matching bibliography entry or correct the citation formatting.",
    "ambiguous_bibliography_ref": "Disambiguate the citation or adjust bibliography entries so only one match remains.",
    "unresolved_reference": "Verify DOI, title, author, or year in the bibliography entry.",
    "retracted_article": "Consider replacing the reference or clearly noting the retraction context.",
    "predatory_venue_match": "Confirm the venue quality before citing.",
    "potentially_inappropriate": "Review surrounding text and ensure citation relevance.",
    "needs_manual_review": "Review the citation manually for accuracy.",
}


def _clean_text(value: object, *, max_chars: int | None = 1200) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    if max_chars is not None and len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    normalized = unicodedata.normalize("NFKD", text)
    safe_text = normalized.encode("ascii", "replace").decode("ascii")
    return safe_text.strip() or "?"


def _plain_markdown(value: str, *, max_chars: int | None = None) -> list[str]:
    if not value:
        return []
    lines: list[str] = []
    for raw in value.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        cleaned = _clean_text(line, max_chars=max_chars)
        if cleaned:
            lines.append(cleaned)
    return lines


def _safe_http_url(value: object) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    return raw


def _openalex_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("https://api.openalex.org/works/"):
        raw = raw.replace("https://api.openalex.org/works/", "https://openalex.org/")
    elif raw.startswith("W"):
        raw = f"https://openalex.org/{raw}"
    return _safe_http_url(raw)


def _format_score(value: object) -> str:
    if value is None:
        return ""
    try:
        numeric = float(value)
    except Exception:
        return _clean_text(value, max_chars=60)
    if numeric.is_integer():
        return f"{int(numeric)}"
    return f"{numeric:.2f}"


def _summary_rows(report: Mapping[str, Any] | None) -> list[list[str]]:
    if not isinstance(report, Mapping):
        return []
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        summary = {}
    rows: list[list[str]] = []
    for key, label in _SUMMARY_FIELDS:
        raw = summary.get(key, 0)
        try:
            value = int(raw)
        except Exception:
            value = 0
        rows.append([label, f"{value}"])
    return rows


def _reviewer_entries(report: Mapping[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(report, Mapping):
        return []
    da = report.get("deep_analysis")
    if not isinstance(da, Mapping):
        return []
    raw_reviewers = da.get("potential_reviewers")
    if not isinstance(raw_reviewers, list):
        return []
    reviewers: list[dict[str, str]] = []
    for reviewer in raw_reviewers:
        if not isinstance(reviewer, Mapping):
            continue
        reviewers.append(
            {
                "name": _clean_text(reviewer.get("name") or "Unknown reviewer", max_chars=120),
                "affiliation": _clean_text(reviewer.get("affiliation") or "Affiliation unavailable", max_chars=180),
                "search_url": _safe_http_url(reviewer.get("google_search_url") or ""),
                "popularity": _format_score(reviewer.get("popularity_score")),
            }
        )
    return reviewers


def _issue_entries(report: Mapping[str, Any] | None) -> list[dict[str, object]]:
    if not isinstance(report, Mapping):
        return []
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list):
        return []
    items: list[dict[str, object]] = []
    for issue in raw_issues:
        if not isinstance(issue, Mapping):
            continue

        issue_type = str(issue.get("type") or "").strip()
        details = issue.get("details") if isinstance(issue.get("details"), Mapping) else {}
        citation = details.get("citation") if isinstance(details.get("citation"), Mapping) else {}
        resolution = details.get("resolution") if isinstance(details.get("resolution"), Mapping) else {}
        openalex_url = _openalex_url(resolution.get("openalex_id") or "")

        item: dict[str, object] = {
            "type": issue_type,
            "label": _ISSUE_LABELS.get(issue_type, issue_type.replace("_", " ").title() or "Issue"),
            "description": _ISSUE_DESCRIPTIONS.get(issue_type, ""),
            "action": _ISSUE_ACTIONS.get(issue_type, ""),
            "severity": _clean_text(str(issue.get("severity") or "medium").upper(), max_chars=20),
            "title": _clean_text(issue.get("title") or "", max_chars=400),
            "ref_id": _clean_text(details.get("ref_id") or "", max_chars=80),
            "citation_raw": _clean_text(citation.get("raw") or "", max_chars=300),
            "citation_locator": _clean_text(citation.get("locator") or "", max_chars=120),
            "citation_context": _clean_text(citation.get("context") or "", max_chars=1200),
            "bibliography_raw": _clean_text(details.get("raw") or "", max_chars=800),
            "resolution_title": _clean_text(resolution.get("title") or "", max_chars=450),
            "resolution_doi": _clean_text(resolution.get("doi") or "", max_chars=180),
            "resolution_pmid": _clean_text(resolution.get("pmid") or "", max_chars=80),
            "resolution_pmcid": _clean_text(resolution.get("pmcid") or "", max_chars=80),
            "resolution_arxiv_id": _clean_text(resolution.get("arxiv_id") or "", max_chars=120),
            "resolution_openalex": _clean_text(resolution.get("openalex_id") or "", max_chars=160),
            "resolution_openalex_url": openalex_url,
            "resolution_journal": _clean_text(resolution.get("journal") or "", max_chars=200),
            "resolution_publisher": _clean_text(resolution.get("publisher") or "", max_chars=200),
            "resolution_year": _clean_text(resolution.get("year") or "", max_chars=20),
            "resolution_confidence": _clean_text(resolution.get("confidence") or "", max_chars=20),
            "has_retraction_signal": bool(details.get("retraction")),
            "has_venue_risk_signal": bool(details.get("match")),
        }

        nli = details.get("nli") if isinstance(details.get("nli"), Mapping) else None
        llm = details.get("llm") if isinstance(details.get("llm"), Mapping) else None
        if nli:
            item["automated_label"] = _clean_text(nli.get("label") or "", max_chars=80)
            item["automated_confidence"] = _clean_text(nli.get("confidence") or "", max_chars=20)
        elif llm:
            item["automated_label"] = _clean_text(llm.get("label") or "", max_chars=80)
            item["automated_confidence"] = _clean_text(llm.get("confidence") or "", max_chars=20)
        else:
            item["automated_label"] = ""
            item["automated_confidence"] = ""

        items.append(item)
    return items


def _source_rows(data_sources: list[dict] | None) -> list[list[str]]:
    if not data_sources:
        return []
    rows: list[list[str]] = []
    for src in data_sources:
        if not isinstance(src, Mapping):
            continue
        name = _clean_text(src.get("name") or "Source", max_chars=120)
        detail = _clean_text(src.get("detail") or "", max_chars=500)
        rows.append([name, detail or "-"])
    return rows


def build_report_pdf(
    *,
    site_url: str,
    report_url: str,
    generated_at_utc: dt.datetime,
    document_name: str,
    job_id: str,
    status: str,
    report: Mapping[str, Any] | None,
    data_sources: list[dict] | None,
    methodology_md: str | None,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph
        from reportlab.platypus import SimpleDocTemplate
        from reportlab.platypus import Spacer
        from reportlab.platypus import Table
        from reportlab.platypus import TableStyle
    except Exception as exc:
        raise RuntimeError("PDF export requires reportlab. Install dependencies and retry.") from exc

    generated = generated_at_utc.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    safe_doc_name = _clean_text(document_name, max_chars=260)
    safe_job_id = _clean_text(job_id, max_chars=80)
    safe_status = _clean_text(status, max_chars=40)
    safe_site_url = _clean_text(site_url, max_chars=180)
    safe_report_url = _clean_text(report_url, max_chars=240)

    summary_rows = _summary_rows(report)
    reviewer_entries = _reviewer_entries(report)
    issue_entries = _issue_entries(report)
    source_rows = _source_rows(data_sources)
    methodology_lines = _plain_markdown(methodology_md or "")
    deep_analysis = report.get("deep_analysis") if isinstance(report, Mapping) else None
    if not isinstance(deep_analysis, Mapping):
        deep_analysis = {}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.7 * inch,
        title="miscite citation report",
        author="miscite",
    )

    base_styles = getSampleStyleSheet()
    styles = {
        "Brand": ParagraphStyle(
            "PdfBrand",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=26,
            textColor=colors.HexColor(_BRAND),
            spaceAfter=6,
        ),
        "Subtitle": ParagraphStyle(
            "PdfSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor(_MUTED),
            spaceAfter=8,
        ),
        "Section": ParagraphStyle(
            "PdfSection",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=15,
            textColor=colors.HexColor(_TEXT),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "Subsection": ParagraphStyle(
            "PdfSubsection",
            parent=base_styles["Heading4"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor(_TEXT),
            spaceBefore=7,
            spaceAfter=3,
        ),
        "Body": ParagraphStyle(
            "PdfBody",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.8,
            leading=13.5,
            textColor=colors.HexColor(_TEXT),
            spaceAfter=3,
        ),
        "IssueTitle": ParagraphStyle(
            "PdfIssueTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor(_TEXT),
            spaceBefore=5,
            spaceAfter=3,
        ),
        "TocEntry": ParagraphStyle(
            "PdfTocEntry",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9.6,
            leading=12.5,
            textColor=colors.HexColor(_TEXT),
            leftIndent=10,
            spaceAfter=2,
        ),
    }

    story: list = []

    header = Table(
        [
            [
                Paragraph("miscite", styles["Brand"]),
                Paragraph(escape(safe_site_url), styles["Subtitle"]),
            ]
        ],
        colWidths=[3.4 * inch, 3.2 * inch],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_SURFACE)),
                ("LINEBELOW", (0, 0), (-1, -1), 1.25, colors.HexColor(_BRAND)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Citation Analysis Report", styles["Section"]))

    meta_rows = [
        ["Document", safe_doc_name or "Uploaded manuscript"],
        ["Job ID", safe_job_id],
        ["Status", safe_status],
        ["Generated", generated],
        ["Report URL", safe_report_url],
    ]
    meta_table = Table(meta_rows, colWidths=[1.2 * inch, 5.4 * inch], hAlign="LEFT")
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_SURFACE_ALT)),
                ("BACKGROUND", (1, 0), (1, -1), colors.white),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(_TEXT)),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9DDE0")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DDE0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta_table)

    da_status_for_toc = _clean_text(deep_analysis.get("status") or "", max_chars=40).lower()
    da_refs_for_toc = deep_analysis.get("references") if isinstance(deep_analysis, Mapping) else None
    has_reference_list = da_status_for_toc == "completed" and isinstance(da_refs_for_toc, Mapping) and bool(da_refs_for_toc)
    has_sources_used = bool(source_rows)
    has_methodology = bool(methodology_lines)

    toc_entries: list[tuple[str, str]] = [
        ("summary", "Summary"),
        ("potential-reviewers", "Potential Reviewers"),
        ("flags", "Flags"),
        ("recommendations", "Recommendations"),
    ]
    if has_reference_list:
        toc_entries.append(("complete-reference-list", "Complete Reference List"))
    if has_sources_used:
        toc_entries.append(("sources-used", "Sources Used"))
    if has_methodology:
        toc_entries.append(("methodology-notes", "Methodology Notes"))

    story.append(Paragraph('<a name="toc"/>Table of Contents', styles["Section"]))
    for anchor, label in toc_entries:
        story.append(Paragraph(f'&#8226; <a href="#{anchor}">{escape(label)}</a>', styles["TocEntry"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph('<a name="summary"/>Summary', styles["Section"]))
    if summary_rows:
        summary_table = Table(summary_rows, colWidths=[4.7 * inch, 1.9 * inch], hAlign="LEFT")
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(_TEXT)),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9DDE0")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DDE0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(summary_table)
    else:
        story.append(Paragraph("Summary metrics are not available yet for this job.", styles["Body"]))

    story.append(Paragraph('<a name="potential-reviewers"/>Potential Reviewers', styles["Section"]))
    if reviewer_entries:
        reviewer_rows: list[list[object]] = [
            [
                Paragraph("<b>Name</b>", styles["Body"]),
                Paragraph("<b>Affiliation</b>", styles["Body"]),
                Paragraph("<b>Popularity</b>", styles["Body"]),
            ]
        ]
        for idx, reviewer in enumerate(reviewer_entries, 1):
            name_text = escape(reviewer["name"])
            search_url = reviewer["search_url"]
            if search_url:
                name_text = f'<a href="{escape(search_url)}">{name_text}</a>'
            reviewer_rows.append(
                [
                    Paragraph(f"{idx}. {name_text}", styles["Body"]),
                    Paragraph(escape(reviewer["affiliation"]), styles["Body"]),
                    Paragraph(escape(reviewer["popularity"] or "-"), styles["Body"]),
                ]
            )

        reviewer_table = Table(reviewer_rows, colWidths=[2.5 * inch, 3.4 * inch, 0.7 * inch], hAlign="LEFT")
        reviewer_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_SURFACE_ALT)),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(_TEXT)),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9DDE0")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DDE0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(reviewer_table)
    else:
        da_status = _clean_text(deep_analysis.get("status") or "", max_chars=40).lower()
        if not deep_analysis:
            message = "This report does not include deep-analysis metadata."
        elif da_status == "completed":
            message = "No reviewer candidates were found for this run."
        elif da_status == "skipped":
            message = _clean_text(deep_analysis.get("reason") or "Reviewer suggestions were skipped.")
        elif da_status == "failed":
            message = _clean_text(deep_analysis.get("reason") or "Deep analysis failed before reviewer suggestions completed.")
        else:
            message = "Reviewer suggestions will appear when deep analysis completes."
        story.append(Paragraph(message, styles["Body"]))

    story.append(Paragraph('<a name="flags"/>Flags', styles["Section"]))
    if not issue_entries:
        story.append(Paragraph("No flagged issues were included in this report.", styles["Body"]))
    else:
        for idx, issue in enumerate(issue_entries, 1):
            heading = f"{idx}. [{escape(str(issue['severity']))}] {escape(str(issue['label']))}"
            story.append(Paragraph(heading, styles["IssueTitle"]))
            if issue.get("title"):
                story.append(Paragraph(escape(str(issue["title"])), styles["Body"]))
            if issue.get("description"):
                story.append(Paragraph(escape(str(issue["description"])), styles["Body"]))
            if issue.get("action"):
                story.append(Paragraph(f"<b>Suggested action:</b> {escape(str(issue['action']))}", styles["Body"]))

            if issue.get("ref_id"):
                story.append(Paragraph(f"<b>Reference ID:</b> {escape(str(issue['ref_id']))}", styles["Body"]))
            if issue.get("citation_raw"):
                story.append(Paragraph(f"<b>In-text citation:</b> {escape(str(issue['citation_raw']))}", styles["Body"]))
            if issue.get("citation_locator"):
                story.append(Paragraph(f"<b>Locator:</b> {escape(str(issue['citation_locator']))}", styles["Body"]))
            if issue.get("resolution_title"):
                story.append(Paragraph(f"<b>Resolved title:</b> {escape(str(issue['resolution_title']))}", styles["Body"]))
            if issue.get("resolution_journal"):
                story.append(Paragraph(f"<b>Journal:</b> {escape(str(issue['resolution_journal']))}", styles["Body"]))
            if issue.get("resolution_publisher"):
                story.append(Paragraph(f"<b>Publisher:</b> {escape(str(issue['resolution_publisher']))}", styles["Body"]))
            if issue.get("resolution_year"):
                story.append(Paragraph(f"<b>Year:</b> {escape(str(issue['resolution_year']))}", styles["Body"]))
            if issue.get("resolution_confidence"):
                story.append(
                    Paragraph(
                        f"<b>Resolution confidence:</b> {escape(str(issue['resolution_confidence']))}",
                        styles["Body"],
                    )
                )

            resolution_doi = str(issue.get("resolution_doi") or "").strip()
            if resolution_doi:
                doi_url = _safe_http_url(f"https://doi.org/{resolution_doi}")
                if doi_url:
                    story.append(
                        Paragraph(
                            f"<b>DOI:</b> <a href=\"{escape(doi_url)}\">{escape(resolution_doi)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>DOI:</b> {escape(resolution_doi)}", styles["Body"]))
            if issue.get("resolution_pmid"):
                pmid = str(issue["resolution_pmid"])
                pmid_url = _safe_http_url(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
                if pmid_url:
                    story.append(
                        Paragraph(
                            f"<b>PMID:</b> <a href=\"{escape(pmid_url)}\">{escape(pmid)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>PMID:</b> {escape(pmid)}", styles["Body"]))
            if issue.get("resolution_pmcid"):
                pmcid = str(issue["resolution_pmcid"])
                pmcid_url = _safe_http_url(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
                if pmcid_url:
                    story.append(
                        Paragraph(
                            f"<b>PMCID:</b> <a href=\"{escape(pmcid_url)}\">{escape(pmcid)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>PMCID:</b> {escape(pmcid)}", styles["Body"]))
            if issue.get("resolution_arxiv_id"):
                arxiv_id = str(issue["resolution_arxiv_id"])
                arxiv_url = _safe_http_url(f"https://arxiv.org/abs/{arxiv_id}")
                if arxiv_url:
                    story.append(
                        Paragraph(
                            f"<b>arXiv:</b> <a href=\"{escape(arxiv_url)}\">{escape(arxiv_id)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>arXiv:</b> {escape(arxiv_id)}", styles["Body"]))

            openalex_label = str(issue.get("resolution_openalex") or "").strip()
            openalex_url = str(issue.get("resolution_openalex_url") or "").strip()
            if openalex_label:
                if openalex_url:
                    link_label = openalex_label.replace("https://openalex.org/", "")
                    story.append(
                        Paragraph(
                            f"<b>OpenAlex:</b> <a href=\"{escape(openalex_url)}\">{escape(link_label or openalex_label)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>OpenAlex:</b> {escape(openalex_label)}", styles["Body"]))

            if issue.get("citation_context"):
                story.append(Paragraph(f"<b>Context:</b> {escape(str(issue['citation_context']))}", styles["Body"]))
            if issue.get("bibliography_raw"):
                story.append(
                    Paragraph(
                        f"<b>Bibliography entry:</b> {escape(str(issue['bibliography_raw']))}",
                        styles["Body"],
                    )
                )

            signal_parts: list[str] = []
            if issue.get("has_retraction_signal"):
                signal_parts.append("Retraction signal detected")
            if issue.get("has_venue_risk_signal"):
                signal_parts.append("Venue risk signal detected")
            automated_label = str(issue.get("automated_label") or "").strip()
            automated_confidence = str(issue.get("automated_confidence") or "").strip()
            if automated_label:
                signal_parts.append(
                    f"Automated signal: {automated_label}"
                    + (f" (confidence: {automated_confidence})" if automated_confidence else "")
                )
            if signal_parts:
                story.append(Paragraph(f"<b>Signals:</b> {escape('; '.join(signal_parts))}", styles["Body"]))

            story.append(Spacer(1, 4))

    story.append(Paragraph('<a name="recommendations"/>Recommendations', styles["Section"]))
    if not deep_analysis:
        story.append(Paragraph("This report does not include deep-analysis recommendations.", styles["Body"]))
    else:
        da_status = _clean_text(deep_analysis.get("status") or "", max_chars=40).lower()
        if da_status == "completed":
            recommendations = deep_analysis.get("recommendations")
            if isinstance(recommendations, Mapping):
                rec_status = _clean_text(recommendations.get("status") or "", max_chars=40).lower()
                if rec_status == "completed":
                    overview = _clean_text(recommendations.get("overview") or "", max_chars=1500)
                    if overview:
                        story.append(Paragraph(escape(overview), styles["Body"]))
                    note = _clean_text(recommendations.get("note") or "", max_chars=1000)
                    if note:
                        story.append(Paragraph(escape(note), styles["Body"]))

                    global_actions = recommendations.get("global_actions")
                    if isinstance(global_actions, list) and global_actions:
                        story.append(Paragraph("Top priorities", styles["Subsection"]))
                        for idx, action in enumerate(global_actions, 1):
                            if not isinstance(action, Mapping):
                                continue
                            section_title = _clean_text(action.get("section_title") or "", max_chars=None)
                            action_text = _clean_text(action.get("action") or "", max_chars=None)
                            if not action_text:
                                continue
                            where = _clean_text(action.get("where") or "", max_chars=None)
                            heading = f"Priority {idx}"
                            if section_title:
                                heading += f" · {section_title}"
                            heading += f": {action_text}"
                            if where:
                                heading += f" ({where})"
                            story.append(Paragraph(escape(heading), styles["IssueTitle"]))

                            why = _clean_text(action.get("why") or "", max_chars=900)
                            if why:
                                story.append(Paragraph(f"Why: {escape(why)}", styles["Body"]))
                            anchor = _clean_text(action.get("anchor_quote") or "", max_chars=500)
                            if anchor:
                                story.append(Paragraph(f"Anchor quote: \"{escape(anchor)}\"", styles["Body"]))
                            rids = action.get("rids") if isinstance(action.get("rids"), list) else []
                            if rids:
                                rid_text = ", ".join(
                                    _clean_text(str(rid).replace("[", "").replace("]", ""), max_chars=20)
                                    for rid in rids
                                    if _clean_text(str(rid), max_chars=20)
                                )
                                if rid_text:
                                    story.append(Paragraph(f"Supporting refs: {escape(rid_text)}", styles["Body"]))
                            story.append(Spacer(1, 2))

                    sections = recommendations.get("sections")
                    if isinstance(sections, list) and sections:
                        story.append(Paragraph("Other changes by section", styles["Subsection"]))
                        for idx, section in enumerate(sections, 1):
                            if not isinstance(section, Mapping):
                                continue
                            title = _clean_text(section.get("title") or f"Section {idx}", max_chars=240)
                            story.append(Paragraph(f"{idx}. {escape(title)}", styles["IssueTitle"]))
                            actions = section.get("actions") if isinstance(section.get("actions"), list) else []
                            if not actions:
                                story.append(Paragraph("No recommendations for this section.", styles["Body"]))
                                continue
                            for action in actions:
                                if not isinstance(action, Mapping):
                                    continue
                                action_text = _clean_text(action.get("action") or "", max_chars=900)
                                if not action_text:
                                    continue
                                story.append(Paragraph(f"- {escape(action_text)}", styles["Body"]))
                                why = _clean_text(action.get("why") or "", max_chars=900)
                                if why:
                                    story.append(Paragraph(f"Why: {escape(why)}", styles["Body"]))
                                where = _clean_text(action.get("where") or "", max_chars=700)
                                if where:
                                    story.append(Paragraph(f"Where: {escape(where)}", styles["Body"]))
                                anchor = _clean_text(action.get("anchor_quote") or "", max_chars=500)
                                if anchor:
                                    story.append(Paragraph(f"Anchor quote: \"{escape(anchor)}\"", styles["Body"]))
                                rids = action.get("rids") if isinstance(action.get("rids"), list) else []
                                if rids:
                                    rid_text = ", ".join(
                                        _clean_text(str(rid).replace("[", "").replace("]", ""), max_chars=20)
                                        for rid in rids
                                        if _clean_text(str(rid), max_chars=20)
                                    )
                                    if rid_text:
                                        story.append(Paragraph(f"Supporting refs: {escape(rid_text)}", styles["Body"]))
                            story.append(Spacer(1, 3))
                elif rec_status == "skipped":
                    reason = _clean_text(
                        recommendations.get("reason") or "No recommendations were generated.",
                        max_chars=700,
                    )
                    story.append(Paragraph(escape(reason), styles["Body"]))
                else:
                    story.append(Paragraph("No recommendations were generated for this run.", styles["Body"]))
            else:
                story.append(Paragraph("No recommendations were generated for this run.", styles["Body"]))
        elif da_status == "skipped":
            reason = _clean_text(deep_analysis.get("reason") or "Recommendations were skipped.", max_chars=700)
            story.append(Paragraph(escape(reason), styles["Body"]))
        else:
            reason = _clean_text(deep_analysis.get("reason") or "Recommendations did not complete.", max_chars=700)
            story.append(Paragraph(escape(reason), styles["Body"]))

    da_status = _clean_text(deep_analysis.get("status") or "", max_chars=40).lower() if deep_analysis else ""
    da_references = deep_analysis.get("references") if isinstance(deep_analysis, Mapping) else None
    if da_status == "completed" and isinstance(da_references, Mapping) and da_references:
        story.append(Paragraph('<a name="complete-reference-list"/>Complete Reference List', styles["Section"]))

        citation_groups = deep_analysis.get("citation_groups")
        if isinstance(citation_groups, list) and citation_groups:
            story.append(Paragraph("Reference groups", styles["Subsection"]))
            for group in citation_groups:
                if not isinstance(group, Mapping):
                    continue
                title = _clean_text(group.get("title") or "Group", max_chars=220)
                rids = group.get("rids") if isinstance(group.get("rids"), list) else []
                rid_text = ", ".join(_clean_text(rid or "", max_chars=20) for rid in rids if str(rid or "").strip())
                suffix = f" ({len(rids)})" if rids else ""
                line = f"- {title}{suffix}"
                if rid_text:
                    line += f": {rid_text}"
                story.append(Paragraph(escape(line), styles["Body"]))

        refs: list[Mapping[str, Any]] = []
        for ref in da_references.values():
            if isinstance(ref, Mapping):
                refs.append(ref)
        refs.sort(key=lambda item: _clean_text(item.get("apa_base") or item.get("title") or item.get("rid") or ""))

        for ref in refs:
            rid = _clean_text(ref.get("rid") or "", max_chars=20)
            apa_base = _clean_text(ref.get("apa_base") or "", max_chars=1400)
            if rid and apa_base:
                story.append(Paragraph(f"[{escape(rid)}] {escape(apa_base)}", styles["IssueTitle"]))
            elif apa_base:
                story.append(Paragraph(escape(apa_base), styles["IssueTitle"]))
            elif rid:
                story.append(Paragraph(f"[{escape(rid)}]", styles["IssueTitle"]))

            doi = _clean_text(ref.get("doi") or "", max_chars=200)
            if doi:
                doi_url = _safe_http_url(f"https://doi.org/{doi}")
                if doi_url:
                    story.append(
                        Paragraph(
                            f"<b>DOI:</b> <a href=\"{escape(doi_url)}\">{escape(doi)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>DOI:</b> {escape(doi)}", styles["Body"]))

            openalex_id = _clean_text(ref.get("openalex_id") or "", max_chars=180)
            openalex_url = _openalex_url(ref.get("openalex_id") or "")
            if openalex_id:
                if openalex_url:
                    label = openalex_url.replace("https://openalex.org/", "")
                    story.append(
                        Paragraph(
                            f"<b>OpenAlex:</b> <a href=\"{escape(openalex_url)}\">{escape(label or openalex_id)}</a>",
                            styles["Body"],
                        )
                    )
                else:
                    story.append(Paragraph(f"<b>OpenAlex:</b> {escape(openalex_id)}", styles["Body"]))

            official_url = _safe_http_url(ref.get("official_url") or "")
            if official_url:
                story.append(
                    Paragraph(
                        f"<b>URL:</b> <a href=\"{escape(official_url)}\">{escape(official_url)}</a>",
                        styles["Body"],
                    )
                )

            oa_pdf_url = _safe_http_url(ref.get("oa_pdf_url") or "")
            if oa_pdf_url:
                story.append(
                    Paragraph(
                        f"<b>Open PDF:</b> <a href=\"{escape(oa_pdf_url)}\">{escape(oa_pdf_url)}</a>",
                        styles["Body"],
                    )
                )

            if bool(ref.get("in_paper")):
                story.append(Paragraph("<b>Status:</b> Already cited in manuscript.", styles["Body"]))

            story.append(Spacer(1, 3))

    if source_rows:
        story.append(Paragraph('<a name="sources-used"/>Sources Used', styles["Section"]))
        source_table = Table(source_rows, colWidths=[2.1 * inch, 4.5 * inch], hAlign="LEFT")
        source_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(_SURFACE_ALT)),
                    ("BACKGROUND", (1, 0), (1, -1), colors.white),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(_TEXT)),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9DDE0")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DDE0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(source_table)

    if methodology_lines:
        story.append(Paragraph('<a name="methodology-notes"/>Methodology Notes', styles["Section"]))
        for line in methodology_lines:
            story.append(Paragraph(escape(line), styles["Body"]))

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"Generated by miscite. Visit {escape(safe_site_url)} for the latest report view.",
            styles["Subtitle"],
        )
    )

    def _draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9DDE0"))
        canvas.setLineWidth(0.5)
        canvas.line(40, 38, LETTER[0] - 40, 38)
        if canvas.getPageNumber() > 1:
            label = "Back to TOC"
            label_font = "Helvetica-Bold"
            label_size = 7.2
            text_width = canvas.stringWidth(label, label_font, label_size)
            pad_x = 6
            pad_y = 3
            button_w = text_width + (pad_x * 2)
            button_h = 12
            x = LETTER[0] - 40 - button_w - 66
            y = 20
            canvas.setFillColor(colors.HexColor(_SURFACE_ALT))
            canvas.setStrokeColor(colors.HexColor(_BRAND))
            canvas.roundRect(x, y, button_w, button_h, 3, stroke=1, fill=1)
            canvas.setFont(label_font, label_size)
            canvas.setFillColor(colors.HexColor(_BRAND))
            canvas.drawString(x + pad_x, y + pad_y, label)
            canvas.linkRect("", "toc", (x, y, x + button_w, y + button_h), relative=0, thickness=0)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor(_MUTED))
        canvas.drawString(40, 25, f"miscite | {safe_site_url}")
        canvas.drawRightString(LETTER[0] - 40, 25, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
