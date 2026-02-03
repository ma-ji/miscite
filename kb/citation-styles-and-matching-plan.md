# Citation Styles in Academic Articles + Plan for Citation Matching & Reference Verification

*Date: 2026-02-03*

## Why this matters (context for miscite)

Academic citation formats are not just “stylistic”: they encode (often imperfectly) a linking system between **in‑text pointers** and **bibliographic records**. For a citation-check system like *miscite*, the hard problems come from:

- **Heterogeneity**: disciplines, publishers, and even individual authors apply variants of the “same” style.
- **Information loss**: many in-text citations carry only a subset of metadata (e.g., numeric pointer; author+year; author+page).
- **Ambiguity**: one in-text key can legitimately map to multiple reference entries (e.g., “Smith 2020” when there are multiple Smith 2020 items).
- **Extraction noise**: PDF text extraction and OCR frequently corrupt punctuation, diacritics, superscripts, and line breaks—exactly the characters styles rely on.

This report has three goals:

1. Provide a detailed overview of popular citation styles across **natural sciences**, **social sciences**, and the **humanities** (both **in‑text** and **reference list** conventions).
2. Draft a concrete, implementable plan for **matching in‑text citations to reference list entries**.
3. Draft a plan for **verifying each reference list item** against **OpenAlex, Crossref, and arXiv**, using an LLM only where it adds reliability.

---

## 1) Popular citation styles: how they work in practice

### 1.1 The three big “systems” (families of styles)

Most styles fall into one of three families. Recognizing the family early makes parsing and matching dramatically easier.

#### A) Author–date (a.k.a. “Harvard-style family”)

**In-text**: parenthetical or narrative with *author surname(s) + year*, sometimes with a locator.

- Parenthetical: `(Smith, 2020)` or `(Smith & Jones, 2020, p. 14)`
- Narrative: `Smith (2020) argues…`
- Multiple citations in one parens: `(Smith, 2020; Jones, 2019; Lee et al., 2018)`
- Disambiguation letters: `(Smith, 2020a, 2020b)`

**Reference list**: typically **alphabetical** by first author surname; year is prominent near the start.

**Common in**: social sciences (psychology, education, economics), many natural sciences, interdisciplinary journals.

**Representative styles**: APA, Chicago Author–Date, Harvard variants, ASA, APSA, some “author-year” variants of ACS/CSE.

#### B) Numeric (citation‑sequence)

**In-text**: a number (or range/list of numbers) pointing into the reference list.

- Brackets: `[12]`, `[12–15]`, `[12, 14, 21]`
- Parentheses: `(12)` or `(12–15)`
- Superscripts: `…as shown previously.^12`

**Reference list**: typically **numbered**, often in order of **first appearance** (citation order).

**Common in**: biomed, engineering, physics, many publisher house styles (Nature/Science-like).

**Representative styles**: Vancouver, IEEE, AMA, Nature, many journal custom styles.

#### C) Notes + bibliography (footnote/endnote driven)

**In-text**: footnote/endnote markers (numbers/symbols), sometimes with short parenthetical citations too.

**Notes**: can contain full bibliographic detail on first mention, then shortened forms:

- First note: `1. John Smith, *Book Title* (Chicago: Univ. Press, 2020), 45.`
- Short note: `2. Smith, *Book Title*, 52.`
- Cross-references: `Ibid.` / `ibid.` / `op. cit.` (less common in modern guidance but still appears in manuscripts)

**Bibliography**: optional but common, often **alphabetized**.

**Common in**: history, literature, philosophy, arts, some law and theology.

**Representative styles**: Chicago Notes–Bibliography, Turabian (student adaptation), MHRA, many legal styles (Bluebook/OSCOLA—specialized).

---

### 1.2 What “fields” styles typically encode (and where)

Across styles, references are attempts to encode a subset of the same underlying metadata. The style mainly dictates **order, punctuation, and abbreviations**.

**Core bibliographic fields (works/articles):**

- **Authors**: surname + given names/initials; sometimes “et al.” only after N authors.
- **Year/date**: year only; or full date; or “in press”; or online-ahead-of-print.
- **Title**: article/book/chapter title; sentence case vs title case; quotes vs no quotes.
- **Container**: journal title, book title, proceedings title; often abbreviated in numeric medical/engineering styles.
- **Publication details**: volume, issue, pages or article number/eLocator; edition for books.
- **Publisher info**: for books (city + publisher; sometimes omitted in modern guidance).
- **Identifiers**: DOI (most important), ISBN, ISSN, arXiv ID, PMID/PMCID, URL, accession numbers.

**What’s usually present in the in-text pointer:**

- **Author–date**: author surname(s) + year; sometimes page number.
- **Numeric**: pointer number(s) only.
- **Notes**: footnote marker only in text; the note may contain everything, or a short key.

Implication for matching: in-text to reference list linkage often relies on **partial keys** and therefore needs robust disambiguation.

---

## 1.3 Natural sciences & engineering: common styles and their signatures

### IEEE (engineering/computer science)

**In-text**: bracketed numbers, often multiple: `[1]`, `[1], [3]`, `[1]–[4]`.

**Reference list**: numbered; citation order.

**Reference entry signature**:

- Author initials before surname: `J. A. Smith`
- Title often in quotes: `"Title of article"`
- Journal/proceedings italicized in formatted output (not always in raw text)
- Explicit `vol.`, `no.`, `pp.`, year near end
- `doi:` often included

**Example (typical, not exact punctuation):**

- In-text: `…as shown in [12].`
- Ref: `[12] J. A. Smith and B. C. Jones, "Title," *Journal*, vol. 12, no. 3, pp. 45–67, 2020, doi: 10.…`

**Matching notes**:

- Numeric pointer is the primary key; parsing the reference list numbering correctly is crucial.
- Conference proceedings are very common; titles may include abbreviations and acronyms.

### Vancouver / ICMJE (biomed and many medical journals)

**In-text**: numbers in parentheses, brackets, or superscript; ranges common.

**Reference list**: numbered; citation order.

**Reference entry signature**:

- Surname + initials without punctuation: `Smith JA, Jones BC.`
- Abbreviated journal titles (often NLM abbreviations)
- Date/year early; `2020;12(3):45-67.`
- DOI optional; PMID sometimes present

**Matching notes**:

- Many manuscripts mix Vancouver-like references with journal-specific quirks.
- Journal abbreviations complicate metadata verification; title/DOI become important.

### AMA (American Medical Association)

Very similar operationally to Vancouver (numeric), with differences in punctuation and author limits.

**In-text**: superscript numerals are common in AMA.

**Reference list**: numbered; citation order.

**Matching notes**:

- Same as Vancouver; emphasis on DOI and title matching.

### ACS (chemistry) — three common variants

ACS allows multiple in-text systems in practice (journals choose):

1. **Superscript numbers** (common)
2. **Bracket numbers**
3. **Author–date**

**Reference list**: often numbered for numeric variants; alphabetical for author–date variant.

**Reference entry signature**:

- Strong use of journal abbreviations
- Year prominent
- Volume/pages (or article numbers) standard
- DOI often present

**Matching notes**:

- Need to detect whether the manuscript is using ACS numeric vs ACS author–date; both exist.

### AIP/APS-like physics styles

Often numeric with bracket or superscript citations; references can be minimalist but include DOI.

**Matching notes**:

- arXiv citations are especially common in physics; treat arXiv IDs as first-class identifiers.

### Nature/Science and many publisher house styles

Typically numeric (often superscript) with references in citation order.

**Matching notes**:

- The style itself varies widely across publishers while staying “numeric”.
- Manuscripts sometimes use numeric in-text but provide an alphabetized bibliography (author habit); detect and handle.

---

## 1.4 Social sciences: common styles and their signatures

### APA (psychology, education, many social sciences)

**In-text**: author–date; strong rules for et al. and multiple authors.

- Two authors: `(Smith & Jones, 2020)`
- 3+ authors: `(Smith et al., 2020)` (rules vary by APA version but “et al.” is central)
- Multiple citations: `(Jones, 2019; Smith, 2020)`
- Narrative: `Smith (2020) …`
- Page locator for quotes: `(Smith, 2020, p. 14)`

**Reference list**: alphabetical by first author; hanging indent in formatted output.

**Reference entry signature**:

- Year in parentheses after authors: `Smith, J. A. (2020).`
- Title in **sentence case** (only first word/proper nouns capitalized)
- DOI as URL: `https://doi.org/...`

**Matching notes**:

- Author–date key is often sufficient, but disambiguation letters (`2020a`) and same-author-year collisions are common.
- APA in-text may omit some authors that appear in reference list; use “first author + year” as a base key, then refine.

### Chicago Author–Date (common in some social sciences)

**In-text**: similar to Harvard/APA: `(Smith 2020, 14)` (note: often no comma between author and year).

**Reference list**: alphabetical; year near the front but formatting differs from APA.

**Matching notes**:

- Compare punctuation patterns: Chicago author–date often uses `Smith 2020` (space) rather than `Smith, 2020`.

### Harvard variants (economics, general social science)

“Harvard” is more a family than a single strict standard.

**In-text**: `(Smith 2020)` or `(Smith, 2020)`; often uses `and` instead of `&`.

**Reference list**: alphabetical; year prominent.

**Matching notes**:

- Expect local variations: whether titles are quoted, how many authors shown, whether DOI is included.

### ASA / APSA (sociology / political science)

Also author–date family; differences are mostly reference list punctuation, capitalization, and how access dates/URLs are handled.

**Matching notes**:

- For matching, treat them as author–date; verification relies on parsing titles and containers reliably.

---

## 1.5 Humanities: common styles and their signatures

### MLA (literature, some humanities)

**In-text**: usually author + page, often *without* year:

- `(Smith 45)`
- If author named in prose: `(45)`
- Multiple works by same author: `(Smith, *Short Title* 45)` to disambiguate

**Works Cited**: alphabetical. Often includes publisher + year; journal articles include volume/issue; URLs are common for web sources.

**Matching notes**:

- In-text key is often **author + page**, not author+year. Page numbers do not identify a work uniquely.
- Disambiguation often uses a shortened title; the matcher must incorporate title tokens when present.

### Chicago Notes–Bibliography (history and many humanities)

**In-text**: footnote markers; notes contain full citations first time and short citations later.

**Bibliography**: often alphabetical.

**Matching notes**:

- The “in-text citation” may not contain the author/year at all—linking relies on parsing the **note text**.
- Short-note forms (author + short title + page) require a two-stage approach: resolve short forms to a full note or bibliography entry.

### MHRA (UK humanities)

Also note-based; similar challenges to Chicago NB, with style-specific punctuation.

### Legal styles (Bluebook, OSCOLA) — specialized

Legal citations frequently refer to **cases, statutes, regulations**, not scholarly articles. OpenAlex/Crossref coverage is limited.

**Matching notes**:

- These styles often require a separate resolver for legal materials; treat them as “non-scholarly” references unless the user enables a legal resolver.

---

## 1.6 Cross-cutting style “pain points” (what breaks parsing/matching)

These appear across disciplines and directly affect system reliability.

### A) Author name variation

- Initials vs full given names (`Smith, J.` vs `Smith, John`)
- Particles and compound surnames (`van der Waals`, `de la Cruz`, `García Márquez`)
- Hyphenation and transliteration (`Zhang-Li` vs `Zhang Li`; Cyrillic/Chinese romanization variants)
- Consortium/group authors (`WHO`, `ATLAS Collaboration`)

### B) Year/date ambiguity

- Online ahead of print vs print year differs
- “In press” / “forthcoming” / “n.d.”
- Reprints/editions: original year vs edition year (common in humanities)
- Disambiguation letters: `2020a/2020b` (driven by reference list ordering rules)

### C) Title instability

- Subtitle present/omitted
- Sentence case vs Title Case
- LaTeX/math symbols, Greek letters, chemical names, gene/protein casing
- OCR errors or line-break hyphenation

### D) Container instability

- Journal abbreviations vs full titles
- Proceedings names change year-to-year; workshops embedded in conferences
- Book series vs book title vs chapter title confusion

### E) Identifier inconsistency

- DOI missing, incorrect, or from a preprint rather than the published version
- arXiv ID used for a published paper (both are “true” but different “work records”)
- Multiple DOIs (rare but occurs with corrections/reprints)

These motivate a matching and verification pipeline that:

1. uses **strong identifiers** when available,
2. uses **field-level fuzzy matching** when identifiers are missing,
3. records **confidence and evidence** for traceability,
4. treats **style detection** as a first-class step rather than hoping one parser fits all.

---

## 2) Plan for matching citations

This section focuses on linking **in‑text citations** ↔ **reference list items** (or notes ↔ bibliography) in a robust, style-agnostic way.

### 2.1 Inputs and outputs (recommended data model)

Assume extraction/LLM parsing yields:

**In-text citation objects** (one per citation *span* or *token group*):

- `raw_text`: exact extracted citation text, e.g., `(Smith & Jones, 2020; Lee, 2019)` or `[12–15]`
- `context`: local sentence/paragraph text (optional but helpful)
- `doc_offset`: start/end positions (if available) to support ordering
- `parsed`: structured fields when possible:
  - `system`: `author_date | numeric | notes | unknown`
  - for `numeric`: `numbers=[12, 13, 14, 15]`
  - for `author_date`: `authors=["Smith", "Jones?"]`, `year=2020`, `suffix="a"?`, `locator="p. 14"?`
  - for `notes`: `note_number=23` (and separately the note text)

**Reference entry objects** (one per bibliography item):

- `raw_text`: the full reference line(s) as extracted
- `ref_index`: integer if numbered (or `None`)
- `parsed`: authors/year/title/container/volume/issue/pages/doi/arxiv/etc (best-effort)

Desired output:

- For each in-text citation, a list of `{reference_id, confidence, rationale}` mappings (possibly multiple if the citation includes multiple works).
- For each reference entry, derived properties:
  - cited/un-cited status, citation count, first-cited position, and any match conflicts.
- Explicit issue types:
  - `intext_unresolved`, `reference_uncited` (optional in humanities), `ambiguous_match`, `duplicate_reference_number`, `broken_numbering`.

### 2.2 Step 0: Detect citation system (before deep parsing)

Perform system detection using both in-text evidence and reference list evidence:

**In-text heuristics:**

- Presence of patterns like `(Surname, 20xx` or `Surname (20xx)` → strong author–date signal.
- Bracket/paren numeric like `[\d+]`, `(\d+)`, ranges `\d+–\d+` → numeric signal.
- Superscript digits are often lost in extraction; look for “dangling” numbers after punctuation or footnote markers.

**Reference list heuristics:**

- Many lines starting with `1.` / `[1]` / `1)` → numeric.
- Reference list sorted alphabetically by surname → author–date or bibliography.
- Footnote section present with citation-like lines → notes.

**LLM assist (optional but high leverage):**

- Ask the LLM to classify the citation system with justification, given:
  - a handful of in-text citation snippets (10–20),
  - first ~10 reference entries,
  - and the document’s discipline (if known).

Output a single `system_profile`:

- `primary_system`: `numeric | author_date | notes`
- `secondary_systems`: e.g., numeric + author–date (rare but real in theses)
- style hints: `APA-like`, `IEEE-like`, `Chicago-NB-like` (used for parsing rules, not for “correctness policing”)

### 2.3 Step 1: Parse references into structured fields (best-effort)

Even numeric matching benefits from structured parsing for later verification.

Recommended approach:

1. **Deterministic parsing first**:
   - Extract DOI via regex (`10.\d{4,9}/...` patterns).
   - Extract arXiv IDs (`arXiv:\d{4}\.\d{4,5}` and legacy `hep-th/....`).
   - Extract year candidates (`(19|20)\d{2}`) with context (avoid page ranges).
   - Extract leading numbering tokens (`^\s*(\[\d+\]|\d+[\.\)]|\(\d+\))`).
2. **LLM parsing second** for hard cases:
   - Provide the raw reference string and ask for a JSON schema:
     - `authors[]`, `year`, `title`, `container`, `volume`, `issue`, `pages`, `publisher`, `doi`, `arxiv_id`, `url`, `type`
   - Require the model to echo back which substrings it used for each field (evidence spans) to reduce hallucination.

Key normalizations:

- Canonicalize author surnames (strip punctuation; normalize unicode; keep particles as part of surname tokenization rules).
- Normalize titles (lowercase; collapse whitespace; remove most punctuation; keep alphanumerics and a small set of symbols).
- Normalize years (integer; allow `None`; support `in_press` boolean).

### 2.4 Step 2: Parse in-text citations into “citation atoms”

Many in-text citation spans contain multiple citations.

**Goal**: split each span into a list of atomic references (“citation atoms”), each intended to map to exactly one reference entry.

Examples:

- `(Smith, 2020; Jones, 2019)` → atoms: `Smith 2020`, `Jones 2019`
- `(Smith, 2020a, 2020b)` → atoms: `Smith 2020a`, `Smith 2020b`
- `[12–15]` → atoms: `12`, `13`, `14`, `15`

Approach by system:

**Numeric**:

- Extract list/range of numbers.
- Expand ranges carefully (handle en-dash vs hyphen; OCR issues).
- Preserve original order and duplicates (they can be meaningful).

**Author–date**:

- Split on semicolons for multiple works.
- Within an author group, split on commas for multiple years.
- Detect `&` / `and` for two-author patterns.
- Capture locators: `p.`, `pp.`, `ch.`, `sec.`, etc. (store but don’t require for matching).

**Notes**:

- Use footnote markers to retrieve note text.
- Parse note text similarly to a mini-reference entry; treat first-note full citations differently from short-note citations.

### 2.5 Step 3: Build fast lookup indexes over the reference list

Create indices to propose candidates quickly:

- `by_number[n] -> reference_id` (if numbered)
- `by_first_author_year[(surname, year)] -> [reference_id...]`
- `by_first_author[(surname)] -> [reference_id...]`
- `by_doi[doi] -> reference_id`
- `by_arxiv[arxiv_id] -> reference_id`
- Optional: `by_title_fingerprint[fingerprint] -> [reference_id...]`

Also record the **reference list order** and detect if it appears alphabetical vs citation-order; that influences disambiguation.

### 2.6 Step 4: Candidate generation and scoring (per citation atom)

#### Numeric system: “pointer-driven” matching

1. If references are explicitly numbered and `by_number` is reliable:
   - Map each number directly.
2. If references are not numbered but in-text is numeric:
   - Infer a mapping by **citation order**:
     - assign reference #1 to the first unique in-text citation encountered, etc.
   - Validate by checking whether the inferred ordering correlates with the reference list ordering.
   - If inconsistent, mark the document as “numeric but broken numbering” and fall back to fuzzy reference matching using titles/DOIs when available.

Common numeric failure modes to detect:

- Duplicate numbering in reference list (two entries labeled `[12]`)
- Missing numbers or non-sequential numbering
- In-text cites numbers that exceed reference list length

#### Author–date system: “key-driven” matching with disambiguation

Base candidate set:

- If citation atom has `surname + year`, start with `by_first_author_year[(surname, year)]`.
- If empty, try relaxed rules:
  - year off by ±1 (online vs print) **only if** title similarity supports it,
  - allow larger year gaps only when other signals strongly agree (title + authors), and record a “year mismatch” warning rather than failing the match outright (especially for working-paper/preprint → published mappings where multi‑year gaps are plausible),
  - handle `n.d.` or `in press` with author-only match.

Scoring signals (recommended weights):

- DOI exact match: near-certain (score → 1.0)
- arXiv exact match: very strong
- First author surname exact match: strong
- Coauthor overlap: strong
- Year match: strong; suffix letter match: helpful
- Title similarity: strong, but fuzzy (use token Jaccard / edit distance; be robust to OCR)
- Container/journal match: medium (abbreviations cause noise)
- Volume/issue/pages: medium (often missing or corrupted)

Disambiguation strategies:

- If `(surname, year)` yields multiple candidates:
  - check year suffix (`2020a/2020b`) if present,
  - check title tokens (first 5–8 significant words),
  - check coauthor hints (e.g., “Smith & Jones” should prefer entries with both surnames).

When still ambiguous:

- Keep multiple candidates with confidence distribution and mark `ambiguous_match`.
- Optionally ask the LLM for a disambiguation decision by presenting:
  - the citation atom,
  - the paragraph context,
  - the top 3–5 candidate reference parses.

#### Notes system: “note-resolution” matching

Treat note-based citation matching as a two-stage problem:

1. **Resolve notes to works**:
   - Full notes: parse as reference candidates; match to bibliography entries (if present) or directly verify via APIs.
   - Short notes: attempt to link to a prior full note (“same work”) using author+short title patterns.
2. **Resolve works to bibliography**:
   - If bibliography exists, map works to bibliography entries (alphabetical).
   - If no bibliography, treat notes as the reference system and run verification on notes.

This is more complex, but it is also where many humanities manuscripts live; a citation-check system that ignores notes will miss a large segment of use cases.

### 2.7 Step 5: Consistency checks after initial matching

Once you have provisional mappings, run validation checks:

- **In-text cites to missing reference**: citation atoms with no candidates above threshold.
- **Unused references**:
  - In numeric styles, unused references usually indicate reference list pollution or missing in-text citations.
  - In humanities bibliographies, unused references can be legitimate (bibliography vs works-cited); classify based on section title (“Bibliography” vs “Works Cited”).
- **Duplicate references**: two reference entries that resolve to the same DOI/OpenAlex work; flag and merge suggestion.
- **Reference collisions**: multiple in-text keys mapping to the same reference unexpectedly (can indicate parsing errors).

### 2.8 Output representation for traceability (recommended)

For each match, persist:

- `match_method`: `number_direct | number_inferred | author_year_exact | author_year_fuzzy | doi_direct | llm_disambiguated | note_resolved`
- `evidence`: fields compared (e.g., `year`, `first_author`, `title_similarity=0.82`)
- `confidence`: 0–1

This enables a report UI to show not just “matched/unmatched” but *why*.

---

## 3) Plan for verifying each reference list item (OpenAlex + Crossref + arXiv + LLM)

Verification should be approached as **entity resolution**: take a noisy reference string, resolve it to a canonical work record (or conclude it can’t be resolved), and then compare fields to detect likely errors.

### 3.1 Principles for a reliable verification pipeline

1. **Use the strongest identifier available** before any search:
   - DOI > arXiv ID > PMID/PMCID > ISBN/ISSN (where applicable) > title/author/year.
2. **Query multiple sources** where it improves confidence:
   - Crossref is strong for DOI-centric scholarly metadata.
   - OpenAlex provides broader coverage and additional attributes (concepts, citation network, some retraction signals via sources).
   - arXiv is authoritative for preprints and versions.
3. **Treat the LLM as a judge only when deterministic scoring is uncertain**:
   - The LLM should not be the first resolver; it should adjudicate close calls.
4. **Always record evidence**:
   - The report should show which external record was matched and which fields disagree.

### 3.2 Normalization and parsing (shared prerequisites)

Before calling APIs:

- Extract and normalize:
  - `doi` (lowercase; strip `https://doi.org/`)
  - `arxiv_id` (canonicalize `arXiv:` prefix; parse version `v2` if present)
  - `year` (integer)
  - `title` (string + fingerprint)
  - `authors` (ordered list; at minimum, first author surname)
- Classify `reference_type`:
  - `journal_article`, `conference_paper`, `book`, `book_chapter`, `preprint`, `thesis`, `web`, `dataset`, `software`, `standard`, `legal`, `other`

Type classification matters because search fields differ (e.g., Crossref “works” is great for articles but weak for many web references).

### 3.3 API resolution strategy (recommended order)

#### Step A) Direct identifier lookup (highest precision)

1. If DOI present:
   - Query Crossref by DOI (deterministic).
   - Query OpenAlex by DOI (or resolve via OpenAlex search filtered by DOI).
   - If Crossref and OpenAlex disagree materially (rare but possible), keep both records and prefer the one that best matches parsed citation fields.
2. Else if arXiv ID present:
   - Query arXiv API by ID.
   - Optionally check OpenAlex for the arXiv DOI (if present) or matching title.
3. Else if other strong IDs exist (PMID/ISBN):
   - (Outside this report’s core scope, but the same pattern applies: direct lookup before search.)

#### Step B) Structured search (title + author + year)

When no strong ID exists, do structured search in parallel:

- **Crossref search**:
  - Query primarily by title (and optionally author).
  - Use year filters where available, but treat them as soft/range-based (avoid excluding plausible preprint/working‑paper → published gaps).
  - Retrieve top N (e.g., 5–10) candidates.
- **OpenAlex search**:
  - Search by title; optionally filter by publication year (prefer a range) and author surname.
  - Retrieve top N candidates.
- **arXiv search** (only when preprint is likely):
  - Search by title and/or author; arXiv is sensitive to exactness—use quoted phrases carefully.

#### Step C) Candidate scoring (deterministic)

Compute a similarity score between the parsed reference and each candidate:

- `title_similarity` (robust to punctuation/diacritics/OCR)
- `author_similarity` (surname overlap; order-aware for first author)
- `year_similarity` (exact; small penalty for ±1; wider tolerance with increasing penalty when the reference is plausibly a preprint/working paper and the candidate is the later published version)
- `venue_similarity` (journal/proceedings name similarity; abbreviation tolerant)
- `identifier_bonus` (candidate has DOI and it matches extracted DOI; or candidate DOI appears in raw reference)

Accept if:

- best score ≥ high_threshold → **Verified**
- best score in [low_threshold, high_threshold) → **Needs Review / LLM Adjudication**
- no candidate above low_threshold → **Unverified**

#### Step D) LLM adjudication for borderline cases (selective)

When candidates are close or parsing is uncertain:

Provide the LLM a constrained input:

- The raw reference string
- The parsed fields (your best guess)
- A small table of top candidates from OpenAlex/Crossref/arXiv (title, authors, year, venue, DOI/arXiv/URL)

Ask the model to output JSON:

- `chosen_candidate_id` (or `null`)
- `confidence` (0–1)
- `mismatches[]`: list of `{field, citation_value, candidate_value, severity}`
- `suggested_correction` (optional; normalized canonical citation)
- `reasoning_short` (1–3 sentences; no new facts outside provided candidates)

Important reliability constraints:

- Instruct the model: **do not invent metadata**; only choose among candidates or return null.
- Require that any correction is justified by candidate fields.
- Consider using multiple LLM calls only for highest-impact/most ambiguous cases; otherwise default to “Unverified”.

### 3.4 Cross-source consistency checks (quality and fraud detection)

Once a match is selected, verify internal consistency:

- DOI resolves to same title/authors across Crossref/OpenAlex (allow minor formatting differences).
- arXiv title/authors consistent with selected published record (if both exist).
- Year mismatch should be interpreted type‑aware:
  - For published‑article ↔ published‑article matches, differences beyond ±1 are usually suspicious (but downgrade severity if a strong identifier like a DOI matches, or if “online ahead of print” evidence exists).
  - For preprint/working‑paper ↔ published mappings (common in economics and some social sciences), multi‑year gaps can be normal; treat large gaps as a warning and rely more heavily on title/author consistency and identifiers.
- Author list mismatch where first author differs is a strong error signal.
- Venue mismatch (journal vs conference vs book) is a strong error signal.

Flag results as:

- **Verified**
- **Verified with warnings** (minor mismatches likely due to style/extraction)
- **Suspect** (major mismatches likely indicate miscitation or wrong metadata)
- **Unverified**

### 3.5 Handling preprints vs published versions (especially arXiv)

Common scenarios:

1. **arXiv-only**: no DOI; treat arXiv as canonical.
2. **arXiv + DOI**: both cited; link them:
   - verify arXiv record
   - verify DOI record
   - record relation as `preprint_of` / `published_as`
3. **Published paper cited as arXiv**: not “wrong” but worth flagging as “consider citing published version”.

Matching plan:

- If reference contains arXiv ID but no DOI:
  - use arXiv as base record; then search Crossref/OpenAlex primarily by title+authors (treat year as a weak/optional constraint) to see if a published version exists.
  - allow for multi‑year gaps between preprint posting and journal publication (common in some fields, including economics-style working-paper pipelines); record the relationship and downgrade confidence only if other fields disagree.
- If both DOI and arXiv appear:
  - verify both; if they disagree strongly, flag as suspect (could be a pasted DOI error).

### 3.6 What cannot be reliably verified with these three APIs (and how to handle)

OpenAlex/Crossref/arXiv coverage is strong for scholarly works but weak for:

- many **web pages**, **news**, **policy documents**
- **legal materials**
- some **books** (Crossref coverage varies; OpenAlex coverage varies)
- **unpublished theses**, **internal reports**

Recommendation:

- Classify such items early and mark `verification_scope=limited`.
- Still do lightweight validation:
  - URL presence and basic formatting sanity
  - author/year/title extraction
  - duplicate detection within the bibliography (title fingerprinting)
- Avoid false certainty: prefer “Unverified (out of scope)” to hallucinated matches.

### 3.7 Evidence capture for a “traceable” report

For each reference item, store:

- which resolvers were attempted (DOI lookup, title search, arXiv search)
- candidate list (top few) with scores (at least in logs/debug mode)
- chosen canonical record identifiers (OpenAlex work ID, Crossref DOI, arXiv ID)
- mismatch fields and confidence

This evidence becomes the backbone of:

- “non-existent citation” flags (no match found)
- “wrong metadata” flags (match found but major mismatches)
- “duplicate reference” flags (two refs map to same canonical work)
- downstream checks like retraction/predatory venue detection (based on canonical venue IDs)

---

## 4) Practical implementation checklist (summary)

If you are turning this into pipeline code, a pragmatic minimal-first implementation path is:

1. **Robust system detection** (numeric vs author–date vs notes).
2. **Reference parsing** with deterministic ID extraction + LLM fallback.
3. **In-text parsing** into citation atoms.
4. **Matching** using:
   - numeric direct mapping when possible,
   - author-year candidate retrieval + scoring,
   - ambiguity surfacing (don’t overcommit).
5. **Verification**:
   - DOI/arXiv direct lookup first,
   - title/author/year search + scoring,
   - LLM adjudication only for borderline cases.
6. **Traceability**: store match method, evidence, and confidence for every link.

---

## Appendix A: Quick style signature table (high-level)

| Family | In-text looks like | Ref list order | Common styles | Common fields in-text |
|---|---|---|---|---|
| Author–date | `(Smith, 2020)` / `Smith (2020)` | Alphabetical | APA, Chicago AD, Harvard, ASA/APSA | author, year, sometimes pages |
| Numeric | `[12]`, `^12`, `(12–15)` | Citation order (numbered) | IEEE, Vancouver, AMA, Nature | pointer number(s) only |
| Notes | footnote markers | Alphabetical or none | Chicago NB, Turabian, MHRA | marker only; note contains details |

## Appendix B: Examples of ambiguous in-text keys (and why)

- `Smith (2020)` with multiple `Smith 2020` references → needs title/coauthor disambiguation.
- `(Smith et al., 2020)` where “et al.” hides which of several multi-author Smith papers is meant → needs title/context.
- `[12]` when the reference list numbering is broken or starts at 0/2 → must validate numbering before trusting.
- `(Smith 45)` in MLA → page number is not a unique identifier; requires short title or bibliography mapping.
