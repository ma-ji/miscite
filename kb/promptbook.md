## Don't read or edit this file. For dev use

THINK HARD: Build a fully functional citation check platform for academic manuscripts:

1. User can upload a PDF file or MS word file.
2. The system produce a report and flag:

- Inappropriate citations.
- Non-exist citations.
- Retracted articles (from retract watch database).
- Predatory publishers and journals.

1. List data sources used.
2. Be clear and transparent about methdology.
3. Able to use GPU and/or CPU, able to process requests in parallel. Pay attention to OOM errors.
4. Use Google style UI.
5. Have a user management system and billing system.
6. Make sure the codebase is optimized, refactored, and exensible for future functions.
7. Use [Preprint-PDF.md](kb/BibAgent-An-Agentic-Framework-for-Traceable-Miscitation-Detection-in-Scientific-Literature/Preprint-PDF.md)and its cited articles as a reference for relevant knowledge.

========
TASK: Implement a modern, Google-inspired (but NOT copied) website design system + a polished starter page in this repo.

GOAL (design feel):

- Calm, clean, whitespace-first, typography-led, friendly, fast.
- Subtle surfaces (soft borders/shadows), consistent rounding, minimal color.
- High scannability: page intent + primary action obvious within 3 seconds.

HARD RULES:

- Do not copy any Google product layout or assets. Use the underlying principles only.
- Match existing repo stack and conventions. If the repo already uses a framework/UI kit, extend it rather than rewriting.
- Accessibility: keyboard nav + visible focus ring + semantic HTML + WCAG AA contrast.
- Performance: keep dependencies minimal; prefer CSS variables + small utility helpers over heavy UI libraries.

STEP 1 — REPO DISCOVERY

- Inspect package.json, existing styling (Tailwind/CSS modules/Styled Components/etc), routing, component patterns, lint/test scripts.
- Identify where global styles and reusable components belong in this codebase.

STEP 2 — DESIGN TOKENS (CSS variables)
Create a token system (light + dark mode) with:

- colors: --bg, --surface, --text, --muted, --border, --primary, --primary-contrast, --focus
- spacing scale: 4/8/12/16/24/32/48
- radii: sm/md/lg (consistent)
- shadows: subtle 1–3 levels
- typography scale: 12/14/16/20/24/32/40 and sensible line-heights
Implement prefers-color-scheme AND a manual toggle if the app already has settings/state patterns.

STEP 3 — CORE COMPONENTS (reusable)
Build or refine:

- AppHeader (logo/title, nav, actions)
- Button (primary/secondary/tertiary) with hover/pressed/disabled
- Input (incl. search), Select, Toggle
- Card (soft surface, consistent padding)
- Alert/Toast (optional if app already uses notifications)
- Modal/Dialog + Dropdown only if needed for the page
Add loading skeleton + empty state patterns.

Component behavior:

- Subtle micro-interactions (150–250ms ease-out). Respect prefers-reduced-motion.
- Touch targets >= 44px where relevant.
- Strong focus styles that work on both themes.

STEP 4 — LAYOUT + PAGE
Implement a responsive starter page that demonstrates the system:

- Centered container with max width; clear section rhythm (header → hero → content cards → footer)
- 12-col grid or equivalent; mobile-first breakpoints
- Example content blocks: feature cards, a search/input row, and a primary CTA.

STEP 5 — VERIFY

- Run lint/tests/build (use repo scripts).
- Fix any type/lint/a11y issues you introduce.
- Ensure the UI looks good on mobile/tablet/desktop.

DELIVERABLES

- Tokens + theme support
- Components + documentation in a short DESIGN.md or README section:
  - token list, spacing scale, typography scale, component inventory, usage notes
- One polished page showcasing the design system

OUTPUT

- Make code changes directly in the repo.
- Summarize what you changed, where, and how to preview (commands + route).

===

THINK HARD: You are OpenAI Codex working in this repo. Implement the Indiana University (IU) brand color palette as the project’s design tokens and semantic theme variables (light + dark). Use the palette faithfully (you may derive tints/shades via opacity for states/surfaces, but do not invent new hues).

IU palette:

- Crimson:        #990000
- Light Crimson:  #F41C40
- Dark Crimson:   #6D0808
- Cream:          #FFFFFF
- Light Cream:    #F8EFE2
- Dark Cream:     #F5E3CC
- Light Gray:     #EEEEF0
- Dark Gray:      #B9C1C6
- IU Black:       #072332

Semantic mapping (web-first):

- --bg:              #FFFFFF
- --surface:         #F8EFE2
- --surface-2:       #F5E3CC
- --text:            #072332
- --border:          #B9C1C6
- --border-soft:     #EEEEF0
- --primary:         #990000
- --primary-hover:   #6D0808
- --primary-active:  #6D0808
- --link:            #990000
- --focus:           #F41C40  (use for focus rings/accents; avoid as a large background behind small text)

Accessibility constraints:

- Default body text should be IU Black (#072332) on light surfaces.
- Treat Dark Gray (#B9C1C6) as border/disabled UI, NOT as body text (too low contrast).
- Prefer white text on Crimson/Dark Crimson buttons. Avoid using Light Crimson as a button background for small text unless contrast is verified.

Dark mode guidance (still IU-branded, not neon):

- Base: --bg: #072332, --text: #FFFFFF
- Use subtle translucent overlays of white/cream for surfaces/borders (opacity) rather than introducing new hex hues.
- Keep Crimson as primary action; use Dark Crimson for hover/active.

Deliverables:

1) Add/modify the repo’s global theme/tokens file (CSS variables or Tailwind theme) with the palette + semantic tokens above.
2) Apply tokens to core components (Button, Input, Card, links, focus states).
3) Add a short DESIGN.md section documenting the palette and token usage.
4) Run lint/tests/build and fix any issues introduced.

======

THINK HARD: You are a senior product designer + frontend engineer. Improve the Dashboard UI (upload manuscript → generate citation report → browse recent jobs). Use the existing visual style as a starting point, but modernize it with clearer hierarchy, better UX states, and more actionable job history.

GOALS

- Make the primary user task unmistakable: upload → analyze → view report.
- Reduce competing emphasis from Account/Billing widgets; keep them actionable when blocking usage.
- Turn “Latest analyses” from a basic log into a searchable, filterable workspace.
- Improve visual hierarchy, spacing, typography, and accessibility.

REWORK THE PAGE AS THREE ZONES

1) Primary zone: “Analyze citations” hero + Upload module (dominant, wide, top-left)
2) Secondary zone: Conditional Billing/Usage banner (only when relevant)
3) Workspace zone: Recent jobs table with real controls and clear actions

SPECIFIC CHANGES TO IMPLEMENT

A) Page framing / copy

- Change main title from “Dashboard” to “Analyze citations”.
- Add a one-sentence value prop below title (what checks are run: OpenAlex/Crossref/arXiv metadata, Retraction Watch, curated lists).
- Add a small privacy/trust note (e.g., “Files are processed securely; reports are workspace-scoped.”)

B) Upload experience (primary module)

- Replace “Choose File” row with a drag-and-drop dropzone:
  - Text: “Drop a PDF/DOCX here, or Browse”
  - Show constraints: supported formats, max size, optional page limit.
- Rename CTA from “Submit for review” to “Generate report” or “Analyze manuscript”.
- Add clear UI states:
  - Idle (no file), File selected, Uploading (progress), Processing (stepper), Completed (link), Failed (error + retry).
- Add “Sample report” link for first-time users.
- Disable primary CTA until a file is selected.

C) Billing/account handling

- Remove duplicated “Billing status: inactive” text.
- If billing is inactive and it blocks usage, show ONE prominent banner/module:
  - “Billing inactive — activate to generate reports” + primary button “Activate billing”.
- Move account email/sign-in info to a less prominent place (top-right dropdown or smaller panel).
- “Manage billing” should look like a button when it’s important; “Refresh” should be an icon button.

D) “Latest analyses” → workspace upgrade

- Convert ISO timestamps to human format + relative time (e.g., “Jan 30, 2026 · 2h ago”).
- Add controls above table:
  - Search by filename
  - Filters: All / Completed / Failed / Processing
  - Sort: Newest / Oldest / Status
- Improve row actions based on status:
  - Completed → “View report”
  - Failed → “View error” + “Retry”
  - Processing → progress indicator + “View status”
- Use consistent status badges (icon + label) and tooltips for failure reasons.
- If multiple rows share the same filename, consider grouping into a single item with version/history expandable.

========
Date: 2026-02-03
Goal: Add absolute links in emails and send Stripe receipts after top-ups/auto-charges.
Prompt: "THINK HARD and FIX: 1. Existing email templates does not have domain, only have path. 2. Send out an email with Strip receipt after charge or auto-charge."
Files touched: server/miscite/core/config.py, server/miscite/core/email.py, server/miscite/routes/billing.py, .env.example, docs/DEVELOPMENT.md, AGENTS.md.
Decision/rationale: Introduced `MISCITE_PUBLIC_ORIGIN` for absolute email links and added receipt-email helper invoked from Stripe webhook handlers for top-up and auto-charge events.

E) Visual system & layout polish

- Reduce excessive card backgrounds; increase whitespace and use fewer boxes.
- Use consistent spacing (8px grid), consistent border radius, consistent shadows.
- Strengthen nav active state for “Dashboard”; make “Theme: Light” a proper toggle.
- Ensure buttons vs links are visually distinct.
- Align card heights and table width; keep content on a clean grid.

F) Accessibility / UX quality

- Improve contrast for light gray text and subtle borders.
- Add visible keyboard focus states for all interactive elements.
- Ensure the file input has an accessible label and dropzone is keyboard-usable.
- Provide friendly, actionable error messages (e.g., parsing error, Crossref timeout, missing DOI) and next steps.

DELIVERABLES

- Produce updated UI code implementing the changes (keep tech stack consistent with the project; prefer componentized approach).
- Create/standardize these components if missing: Button, Badge, Card, Alert/Banner, Table, FileDropzone, Progress/Stepper.
- Keep the page responsive (desktop-first, but works on smaller screens).
- Do not add new product features; only improve UI/UX for the existing flow.

ACCEPTANCE CHECKLIST

- Upload flow feels modern (drag/drop, states, progress).
- Billing status is shown once and is actionable if blocking.
- Job history is searchable/filterable and has status-specific actions.
- Visual hierarchy is clear: primary task first, workspace second, account third.
- Accessibility basics are met (contrast, focus, labels).

========

THINK HARD: Add a Deep Analysis pipeline after the flagging process:

1. Select half of the all verified references (Original Refs) that are key to this study with LLM (Key Refs).

2. Retrive all the references **cited by** these Key Refs (Cited Refs).

3. Retrive all the references **cited by** these Cited Refs (Cited Refs2).

4. Retrive all the references **citing** these Key Refs (Citing Refs). Only take most recent 100 citing articles per Key Ref if too many.

5. Retrive all the references **cited by** these Citing Refs (Citing Refs2).

6. Lit Pool = Original Refs + Cited Refs + Cited Refs2 + Citing Refs + Citing Refs2.

7. Construct a citation network (weighted and directed) with all the references in the Lit Pool. A node is a reference, two nodes connected if they have citation relationship (directed and weighted).

8. Identify Top 10% of the references that have the (1) most inward connections; (2) highest betweenness centralities; (3) highest closeness centrality (higher value means more central); (4) articles in Original Refs but marginalized (How to define? Think of a strong measure given the context and purpose) in the citation network, flagged as "tangencial citation".

9. Review references in each of the four categories, and make suggestions on how to appropriately integrate (or remove) into the current paper.

10. For the user report and suggestions, use user-friendly format and language, no need to mention the background methodology and technical terms. Focus on how to help users improve their paper.

========
Date: 2026-02-06
Goal: Redesign report Recommendations to be concretely actionable for both researchers and editors.
Prompt: "Analyze Recommendations block in the report, propose a plan to improve it... Implement all proposed changes by phases." with decisions: keep "reconsider/justify" language, hide technical metadata, emit top 5 global + up to 3 per section, allow report schema changes, require specific quoted text anchors.
Files touched: server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/analysis/deep_analysis/suggestions.py, server/miscite/analysis/deep_analysis/subsection_recommendations.py, server/miscite/analysis/deep_analysis/recommendations.py, server/miscite/templates/job.html, server/miscite/web/report_pdf.py, server/miscite/prompts/deep_analysis/suggestions/user.txt, server/miscite/prompts/deep_analysis/subsection_plan/user.txt, server/miscite/prompts/schemas/deep_suggestions.schema.json, server/miscite/prompts/schemas/deep_subsection_plan.schema.json, server/miscite/analysis/deep_analysis/test_recommendations.py, server/miscite/analysis/deep_analysis/test_subsection_recommendations.py, server/miscite/analysis/deep_analysis/test_suggestions.py, docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, AGENTS.md.
Decision/rationale: Replaced brittle free-text recommendation parsing with structured recommendation items, introduced deterministic aggregation/ranking limits for clearer prioritization, added location + quote anchors for concrete manuscript edits, and aligned HTML/PDF rendering to a single canonical `deep_analysis.recommendations` contract.

11. Use parallel processing to speedup, pay attention to OOM and rate limit.

======

THINK HARD: For the report page and related processes:

1. In-text citation can have mulitple in one place, such as (Merton 1988; Rigney 2010; Bol, De Vaan, and Van De Rijt 2018), make sure they are split before matching.

2. Enable download the report as a PDF file, not JSON.

3. Remove unnecessary buttons on this page, e.g., Get report, Use an access token, etc.

4. After token generation, shows when the token expires.

For the deep analysis:

1. Use a speperate model for writing the deep analysis report.

2. Organize the suggestions by the order of the article's major sections.

3. Summarize major recommendations with priorities in narrative format with APA style in-text citation (cross-referenced to the reference list).

4. List all references alphabetically, (1) By group, as it is right now; (2) In one reference section at the very end of the report.

5. For "Already cited" label, use a green-like UI-consistent color.

In the end:

1. Double check the design of this page adhere to UI principles and user demands.

====

THINK HARD: Work on the email delivery system and user system:

1. Use Mailgun API for email.
2. Simplify register process: enter email, send a random code to email, use that code as login credential. User can select remain signed in for: current window session, 7 days, 30 days.
3. Merge the sign in and register buttons elsewhere given the new simplified process. Keep using the color for register.
4. Generate an access token automatically once a job starts and email it with the related information. Users can use this token to check progress or access the report.
5. By default, the access token and report are valid for 7 days and then auto-deleted.

====

THINK HARD: Refactor and reorganize the codebase to be more modularized:

1. Scripts related to each major step of the pipeline or function is under one folder. Shared components are also under one folder.
2. Under each such folder, there is a readme file documenting the details.
3. Simplify the contents of the main readme file under the root folder, with links to readme files under subfolders that provide more details.
4. Optimize this strategy if necessary.

====

THINK HARD: create a fully functional billing system.

1. Pull latest model price from openrouter via API, update hourly: <https://openrouter.ai/docs/api/api-reference/models/get-models>

2. Monitor the use of LLM API, calculate actual cost using the latest price.

3. Allowing setting up a multiplier in .env file for calculating final cost.

4. Deduct that final cost from user's balance only after job successfully completed.

5. Allow users to charge balance via Stripe. Have an auto-charge option. Minimal charge amount is configurable via .env. Auto-charge option mimics how OpenAI billing system works.

====

2026-02-02
Goal: Update LLM cache matching criteria.
Prompt: Change LLM cache matching to model + temperature + prompt texts.
Files touched: server/miscite/llm/openrouter.py
Decision/rationale: Use global cache scope and key parts derived directly from model/temperature/system/user text to ensure cache hits across identical prompts regardless of document scope.

2026-02-02
Goal: Avoid worker crashes on OpenRouter provider errors during match disambiguation.
Prompt: Traceback showed OpenRouter error response "Provider returned error" bubbling from resolve LLM matching.
Files touched: server/miscite/llm/openrouter.py, server/miscite/analysis/pipeline/resolve.py, kb/promptbook.md
Decision/rationale: Treat provider errors as retryable when possible, and skip LLM disambiguation on failure so optional matching does not abort the job.

2026-02-02
Goal: Make Stripe auto-charge workflow robust and idempotent.
Prompt: Double check the auto-charge function and confirm the end-to-end workflow works correctly.
Files touched: server/miscite/worker/**init**.py, server/miscite/billing/stripe.py, server/miscite/routes/billing.py, server/miscite/routes/dashboard.py, server/miscite/core/models.py, server/miscite/core/config.py, server/miscite/templates/billing.html, .env.example, docs/DEVELOPMENT.md, kb/promptbook.md
Decision/rationale: Add an in-flight auto-charge lock (plus Stripe idempotency keys) to prevent duplicate charges under concurrency, require webhook configuration for top-ups/auto-charge, verify a saved payment method exists before treating auto-charge as “ready”, clear in-flight state on webhook success/failure, and enforce uniqueness for Stripe IDs on billing transactions to prevent double-credits.

2026-02-02
Goal: Improve billing/auto-charge UX clarity.
Prompt: Improve the UI/UX to make it easy and simple to follow.
Files touched: server/miscite/routes/billing.py, server/miscite/templates/billing.html, server/miscite/templates/dashboard.html, kb/promptbook.md
Decision/rationale: Add a clear on-page auto-charge setup checklist, surface missing Stripe/webhook prerequisites, and disable top-up actions when billing is not fully configured to reduce user confusion.

2026-02-02
Goal: Make pay-as-you-go the primary billing path and fix confusing auto-charge saves.
Prompt: List pay-as-you-go option first; after clicking "save auto-charge", nothing changed.
Files touched: server/miscite/routes/billing.py, server/miscite/templates/billing.html, server/miscite/templates/dashboard.html, kb/promptbook.md
Decision/rationale: Reframe the billing checklist around pay-as-you-go first (with a primary CTA), adjust banner copy to match, and ensure auto-charge threshold/amount edits persist with accurate success messages for enable/disable/save flows.

2026-02-02
Goal: Refresh the Billing balance and usage UI for clearer hierarchy, payment-grade trust, and better validation feedback.
Prompt: Improve the Billing -> Balance & usage page layout, copy, states, and accessibility without changing billing logic.
Files touched: server/miscite/templates/billing.html, server/miscite/static/styles.css, server/miscite/routes/billing.py, server/miscite/routes/test_billing_formatting.py, kb/promptbook.md
Decision/rationale: Replace the redundant billing setup block with a contextual payment-method stepper, build a two-column layout with prominent balance/actions, add presets and inline validation/disabled states with loading feedback, improve activity formatting and mobile responsiveness, and fix currency display for negative balances.

2026-02-02
Goal: Reposition billing balance summary and reorder billing layout for clearer hierarchy.
Prompt: Move balance block to top-right aligned with title, remove actions, and place recent activity left with add funds and auto-charge stacked on the right.
Files touched: server/miscite/templates/billing.html, server/miscite/static/styles.css, kb/promptbook.md
Decision/rationale: Align balance summary with the page title using the existing ds-panel style, simplify the balance block by removing CTAs, and reorder the billing grid so recent activity leads on the left with add funds and auto-charge stacked on the right.

2026-02-02
Goal: Align billing UI with shared design system and add client-side activity filters.
Prompt: Remove billing-specific CSS, auto-save auto-charge on toggle, and add transaction type/date filters.
Files touched: server/miscite/templates/billing.html, server/miscite/static/styles.css, kb/promptbook.md
Decision/rationale: Rebuild the billing layout using existing ds-* components only, switch auto-charge to automatic submission on toggle/value changes, and add client-side filters for transaction type/date without changing backend logic.

2026-02-02
Goal: Prevent grid column overlap from wide content (tables/filters) in billing and other pages.
Prompt: Recent activity card still overlaps the right column; ensure proper spacing.
Files touched: server/miscite/static/styles.css, kb/promptbook.md
Decision/rationale: Add `min-width: 0` to immediate children of `.ds-grid` so grid items can shrink and let internal overflow/scroll behave correctly instead of bleeding into adjacent columns.

2026-02-02
Goal: Stop tables from forcing oversized widths in multi-column layouts.
Prompt: Recent activity table in billing still overflows/bleeds into the adjacent column.
Files touched: server/miscite/static/styles.css, server/miscite/templates/dashboard.html, kb/promptbook.md
Decision/rationale: Remove the hard-coded min-width from the base `ds-table` and introduce `ds-table--wide` for pages that want an intentional horizontal-scroll minimum, so narrower columns (like Billing activity) can shrink without overflowing.

2026-02-02
Goal: Align auto-charge threshold and recharge fields in the billing UI.
Prompt: Auto-charge trigger/recharge inputs are misaligned.
Files touched: server/miscite/static/styles.css, server/miscite/templates/billing.html, kb/promptbook.md
Decision/rationale: Add a general design-system modifier (`ds-input-row--top`) to top-align multi-field rows when help text heights differ, preventing input misalignment without introducing billing-specific CSS.

2026-02-02
Goal: Move auto-charge trigger/recharge settings into a popout to avoid alignment issues.
Prompt: In the auto-charge block, make trigger balance and recharge amount a popout window and show the current settings as text.
Files touched: server/miscite/templates/billing.html, server/miscite/static/styles.css, kb/promptbook.md
Decision/rationale: Use a native `<dialog>` styled as a reusable design-system component (`ds-dialog`) with an embedded `ds-card` to keep a payment-grade feel while avoiding brittle side-by-side alignment; keep auto-save on toggle and apply setting edits via a modal “Done” action so users can update both fields together.

2026-02-03
Goal: Document citation style landscape and a robust plan for citation matching + reference verification.
Prompt: Provide a detailed analysis of popular citation styles (sciences/social sciences/humanities) and draft a plan to (1) match in-text citations to reference list entries and (2) verify references via OpenAlex/Crossref/arXiv with selective LLM assistance.
Files touched: kb/citation-styles-and-matching-plan.md, kb/promptbook.md
Decision/rationale: Organize styles by the three core citation systems (author–date, numeric, notes+bibliography) and propose a traceable matching/verification pipeline that prioritizes strong identifiers, uses deterministic scoring for candidate selection, and reserves LLM calls for borderline disambiguation.

2026-02-03
Goal: Implement robust citation↔bibliography matching and type-aware year handling in reference resolution.
Prompt: Update the citation check pipeline to follow kb/citation-styles-and-matching-plan.md (better in-text↔bibliography matching, ambiguity handling, and improved verification behavior for preprint→published year gaps).
Files touched: AGENTS.md, docs/ARCHITECTURE.md, server/miscite/analysis/match/**init**.py, server/miscite/analysis/match/index.py, server/miscite/analysis/match/match.py, server/miscite/analysis/match/types.py, server/miscite/analysis/parse/citation_parsing.py, server/miscite/analysis/parse/llm_parsing.py, server/miscite/analysis/pipeline/**init**.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/checks/reference_flags.py, server/miscite/analysis/checks/inappropriate.py, server/miscite/analysis/deep_analysis/prep.py, server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/templates/job.html, kb/promptbook.md
Decision/rationale: Introduce a dedicated `analysis/match/` module to index references and link citations with confidence/ambiguity and candidate evidence; propagate match objects through checks and deep analysis for traceability; relax year usage in OpenAlex/Crossref search/scoring when a reference looks preprint/working-paper-like to avoid false mismatches due to multi-year publication gaps.

2026-02-03
Goal: Make preprint year-gap tolerance configurable and use LLM to disambiguate ambiguous citation↔bibliography matches.
Prompt: Make the preprint year gap configurable (default 5 years max) and enable LLM disambiguation for ambiguous citation matches.
Files touched: .env.example, AGENTS.md, docs/DEVELOPMENT.md, server/miscite/core/config.py, server/miscite/prompts/matching/bibliography_candidate/system.txt, server/miscite/prompts/matching/bibliography_candidate/user.txt, server/miscite/prompts/registry.yaml, server/miscite/analysis/match/**init**.py, server/miscite/analysis/match/llm_disambiguate.py, server/miscite/analysis/pipeline/**init**.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/deep_analysis/prep.py, server/miscite/analysis/report/methodology.py, kb/promptbook.md
Decision/rationale: Add `MISCITE_PREPRINT_YEAR_GAP_MAX` to tune how metadata resolution scores year differences for preprint/working-paper-like references; add an LLM-only disambiguation step for ambiguous citation→bibliography links (with memoization and a shared per-job match-call budget) to improve matching accuracy while bounding cost.

2026-02-03
Goal: Add NCBI/PubMed as an additional metadata source in reference resolution.
Prompt: Also add NCBI/PubMed to data sources (E-utilities guidance).
Files touched: .env.example, AGENTS.md, docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, server/miscite/core/config.py, server/miscite/sources/pubmed.py, server/miscite/analysis/checks/reference_flags.py, server/miscite/analysis/pipeline/**init**.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/pipeline/types.py, server/miscite/analysis/report/methodology.py, kb/promptbook.md
Decision/rationale: Implement an NCBI E-utilities client (ESearch/ESummary) with caching and NCBI-recommended `tool`/`email` (plus optional `api_key`), extract PMID signals from references when present, and insert PubMed into the resolver chain (OpenAlex → Crossref → PubMed → arXiv) with deterministic scoring and optional LLM disambiguation for borderline candidates.

2026-02-03
Goal: Prefer PubMed first when PMID is present, fetch PubMed abstracts, and improve report link UX for verification.
Prompt: If explicit PMID try PubMed first; fetch abstracts; show DOI and other IDs (PMID/arXiv/OpenAlex) as clickable links, with DOI first.
Files touched: server/miscite/sources/pubmed.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/pipeline/**init**.py, server/miscite/analysis/report/methodology.py, server/miscite/templates/job.html, kb/promptbook.md
Decision/rationale: Treat explicit PMIDs as strong identifiers (prefer PubMed before DOI/title search), fetch abstracts via EFetch to improve downstream relevance checks, and render DOI/PMID/arXiv/OpenAlex identifiers as outbound links to make manual verification fast and reliable.

2026-02-03
Goal: Add PMCID support and a complete bibliography section with verification links.
Prompt: Also recognize/link PMCID, and show an "All bibliography references" section with DOI first and all IDs as links.
Files touched: server/miscite/sources/pubmed.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/pipeline/types.py, server/miscite/templates/job.html, kb/promptbook.md
Decision/rationale: Extract PMCID from both references and PubMed metadata, map PMCID to PubMed records when possible, and surface a full bibliography view so users can quickly verify each entry across DOI/PubMed/PMC/arXiv/OpenAlex.

2026-02-03
Goal: Fix PubMed first-author parsing for reliable matching.
Prompt: Some records can be searched on PubMed but appear unresolved; analyze root causes and validate PubMed API responses.
Files touched: server/miscite/sources/pubmed.py, server/miscite/sources/test_pubmed.py, kb/promptbook.md
Decision/rationale: PubMed ESummary author names are typically formatted as "Family Initials" (e.g., "Smyth EC"); extracting the last token incorrectly treated initials as the surname, reducing match scores and causing false unresolved results. Parse the family token instead and add an offline regression test.

2026-02-03
Goal: Standardize resolver lookup order across all references.
Prompt: Keep the citation pipeline standardized: even if a record has PMID/PMCID, still use the standard source order and short-circuits.
Files touched: server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/pipeline/test_resolve_order.py, server/miscite/analysis/report/methodology.py, docs/DEVELOPMENT.md, kb/promptbook.md
Decision/rationale: Remove PMID/PMCID PubMed prefetch so every reference follows the same deterministic resolver order (OpenAlex → Crossref → PubMed → arXiv) with predictable short-circuiting. Treat PMID/PMCID as strong identifiers when the PubMed stage is reached and preserve PMID/PMCID from the bibliography for verification links without adding extra upstream lookups.

2026-02-03
Goal: Prevent false unmatched in-text citations due to multi-author locators and noisy first-author fields.
Prompt: Fix citation↔bibliography matching where citations like "(Matta, 2026a)" and "(Varela, Thompson, & Rosch, 1991)" were reported as not found in the reference list.
Files touched: server/miscite/analysis/shared/normalize.py, server/miscite/analysis/parse/llm_parsing.py, server/miscite/analysis/match/match.py, server/miscite/analysis/match/test_match.py, kb/promptbook.md
Decision/rationale: Normalize author-year locators and LLM-parsed bibliography `first_author` down to the first-author family token when multi-author strings/initials leak into those fields; add a conservative fallback that extracts the first surname from the raw in-text citation when the locator author doesn’t correspond to any bibliography author; cover with offline regression tests.

2026-02-04
Goal: Reduce report-page redundancy and make deep-analysis references usable at 1K+ scale.
Prompt: Optimize the report UI/UX for researcher integrity screening; user reported repeated sections and requested keeping the alphabetized deep-analysis list with a group filter.
Files touched: server/miscite/templates/job.html, server/miscite/static/styles.css, kb/promptbook.md
Decision/rationale: Remove deep-analysis reference duplication and consolidate `[R#]` jump targets into a single alphabetized “Complete reference list”; reuse recommendation groupings as a filter for the alphabetized list (with a live “showing X of Y” counter) and remove the Shortlists block; remove the Bibliography section to cut scroll weight; rewrite Recommendations to a narrative summary that only surfaces high-priority (not-already-in-manuscript) items; fix progress/report empty-state duplication (only show live progress for PENDING/RUNNING, and show report placeholders only when appropriate); add a Sources & Methodology disclosure section (using existing `data_sources` + `methodology_md`) to improve auditability; add a human label for `ambiguous_bibliography_ref` and a small design-system class to keep source names readable.

2026-02-04
Goal: Add deep-analysis subsection-by-subsection revision recommendations using citation-subnetwork neighborhoods.
Prompt: For deep analysis, after constructing the citation network, produce recommendations subsection-by-subsection: build a subsection-specific citation graph (neighbors up to 3rd degree), pass subsection text + reference metadata/abstracts to the LLM for a prioritized revision plan, and parallelize where appropriate.
Files touched: server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/analysis/deep_analysis/references.py, server/miscite/analysis/deep_analysis/subsections.py, server/miscite/analysis/deep_analysis/subsection_recommendations.py, server/miscite/analysis/deep_analysis/types.py, server/miscite/analysis/pipeline/__init__.py, server/miscite/core/config.py, server/miscite/prompts/registry.yaml, server/miscite/prompts/deep_analysis/subsection_plan/system.txt, server/miscite/prompts/deep_analysis/subsection_plan/user.txt, server/miscite/prompts/schemas/deep_subsection_plan.schema.json, server/miscite/templates/job.html, .env.example, docs/DEVELOPMENT.md, kb/promptbook.md
Decision/rationale: Split the manuscript into subsection-like chunks via heading heuristics, then map each subsection’s cited bibliography items to verified references and expand into a bounded 3-hop neighborhood within the deep-analysis graph. Convert node-IDs to stable `[R#]` ids, include clipped abstracts in the deep-analysis reference payload, and generate per-subsection plans via parallel LLM calls within a call budget; fall back to a heuristic plan when LLM is disabled or budget is exhausted. Surface results in the report UI as disclosure panels per subsection with concrete edit steps and suggested reference additions.

2026-02-04
Goal: Make subsection splitting robust and scope "uncited" to the subsection (not the whole manuscript).
Prompt: Use LLM to convert the manuscript into a standardized structure without renaming sections; subsequent steps should use that structure. Also, treat "not cited" as not cited in that subsection.
Files touched: server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/analysis/deep_analysis/structure.py, server/miscite/analysis/deep_analysis/subsection_recommendations.py, server/miscite/analysis/report/methodology.py, server/miscite/core/config.py, server/miscite/prompts/registry.yaml, server/miscite/prompts/deep_analysis/structure/system.txt, server/miscite/prompts/deep_analysis/structure/user.txt, server/miscite/prompts/deep_analysis/subsection_plan/user.txt, server/miscite/prompts/schemas/deep_structure.schema.json, .env.example, docs/DEVELOPMENT.md, AGENTS.md, kb/promptbook.md
Decision/rationale: Add an LLM-assisted manuscript structuring step (via heading candidates + preserved titles) to build a consistent subsection list used by deep analysis; keep a heuristic fallback for safety. Update subsection recommendation prompting/validation to prioritize integrating references not cited in that subsection (distance>0), regardless of whether the reference is cited elsewhere in the manuscript. Document new env toggles/caps and update methodology for traceability.

2026-02-04
Goal: Run section-level revision plans at the top-level only and label pre-heading content as "opening".
Prompt: Label the pre-heading chunk as "opening"; generate recommendations only for the highest level and combine all sublevels; keep subsection-seed citations restricted to verified references.
Files touched: server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/analysis/deep_analysis/subsections.py, server/miscite/analysis/deep_analysis/structure.py, server/miscite/analysis/report/methodology.py, server/miscite/templates/job.html, kb/promptbook.md
Decision/rationale: Collapse the extracted manuscript structure to top-level sections (merging nested subsection text under the nearest top-level header) so recommendations map cleanly to major manuscript sections. Standardize the preamble as "opening" for consistent reporting and ensure subsection citation-graph seeds remain limited to verified references for reliability.

2026-02-04
Goal: Generate plans for every top-level section (including "opening").
Prompt: Opening section gets a plan; run plans for all top-level sections (combining sublevels).
Files touched: .env.example, docs/DEVELOPMENT.md, server/miscite/core/config.py, server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/analysis/deep_analysis/subsection_recommendations.py, kb/promptbook.md
Decision/rationale: Always emit a plan item per top-level section even if no section-specific citation graph exists (e.g., no verified citations in that section). Default to analyzing all top-level sections by setting `MISCITE_DEEP_ANALYSIS_SUBSECTION_MAX_SUBSECTIONS=0`, while retaining an optional cap for unusually long/fragmented documents.

2026-02-04
Goal: Fix author-year citation splitting when text contains HTML entities like `&amp;`.
Prompt: THINK HARD: The in-text citations like this are not matched correctly: (Greenlee &amp; Trussel, 2000; Hodge &amp; Piccolo, 2005; Trussel, 2002)
Files touched: server/miscite/analysis/parse/citation_parsing.py, server/miscite/analysis/parse/test_citation_parsing.py, kb/promptbook.md
Decision/rationale: HTML entities like `&amp;` include semicolons that were incorrectly treated as citation separators, corrupting multi-citation splitting and downstream matching. Unescape HTML entities before detecting/splitting multi-citation markers and add regression tests for both single- and multi-citation cases.

2026-02-04
Goal: Prevent SQLite "database is locked" errors under concurrent web/worker access and fix subsection recommendation rendering.
Prompt: THINK HARD and fix errors: SQLite database locked in job events; Jinja `subrec.items` not iterable.
Files touched: server/miscite/core/db.py, server/miscite/templates/job.html, kb/promptbook.md
Decision/rationale: Configure SQLite connections with WAL + busy timeout (and normal synchronous) to reduce lock contention while serving event polls/streams; update the report template to access subsection recommendation items via mapping-safe getters to avoid colliding with dict methods.

2026-02-04
Goal: Remove meaningless items from the deep-analysis reference list.
Prompt: THINK HARD: In the deep analysis report's reference list, I see a lot of useless records like "[R230] Unknown author (n.d.). Untitled." Make sure to clean the list to only contain verified and meaningful records.
Files touched: server/miscite/analysis/deep_analysis/references.py, kb/promptbook.md
Decision/rationale: Add a metadata-quality filter during deep-analysis reference list construction so only references with real titles plus supporting metadata (author/year/venue/DOI) are included. Apply the filter to group assignment and RID mapping so unusable placeholders are removed across the report and downstream suggestions.

========
DATE: 2026-02-05
GOAL: Exclude secondary references from deep analysis.
PROMPT: THINK HARD: Exclude secondary references from deep analysis. For example, include primary sources of books, but not any reviews.
FILES TOUCHED: server/miscite/analysis/deep_analysis/secondary.py; server/miscite/analysis/deep_analysis/prep.py; server/miscite/analysis/deep_analysis/references.py; AGENTS.md.
DECISION/RATIONALE: Added secondary-reference detection (OpenAlex type/type_crossref plus conservative review-title heuristics) to filter deep analysis seeds and reference outputs, keeping reviews and book reviews out of recommendations.

========
DATE: 2026-02-05
GOAL: Allow literature reviews while still excluding book reviews in deep analysis.
PROMPT: Literature review is fine, just don't mistreat book reviews as primary sources because they usually have the same title.
FILES TOUCHED: server/miscite/analysis/deep_analysis/secondary.py.
DECISION/RATIONALE: Narrowed secondary-reference detection to focus on book-review signals (OpenAlex type/genre tokens and book-review title patterns) while allowing literature/systematic/scoping reviews and meta-analyses.

========
DATE: 2026-02-05
GOAL: Improve book-review detection when titles lack "review".
PROMPT: Many book reviews won't have "review" in title and may share the same title with books. Can these be identified?
FILES TOUCHED: server/miscite/analysis/deep_analysis/secondary.py.
DECISION/RATIONALE: Extended secondary-reference detection to scan OpenAlex keyword/concept/topic labels for book-review signals while keeping review-article allowlists intact.

========
DATE: 2026-02-05
GOAL: Exclude specific source/venue names from analysis across the pipeline.
PROMPT: Prepare a file of list of source names to be excluded from analysis.
FILES TOUCHED: docs/excluded_sources.txt; server/miscite/analysis/shared/excluded_sources.py; server/miscite/analysis/pipeline/__init__.py; AGENTS.md; kb/promptbook.md.
DECISION/RATIONALE: Added a docs-backed exclusion list and wired it into pipeline checks and deep analysis so references from excluded venues (e.g., Choice Reviews Online) are skipped across metadata-based analysis stages.

========
DATE: 2026-02-05
GOAL: Fully drop excluded sources from deep-analysis reference lists.
PROMPT: THINK HARD: The Choice Reviews Online references still appear in the reference list. Make sure items matching the excluded sources get completed dropped.
FILES TOUCHED: server/miscite/analysis/deep_analysis/references.py; kb/promptbook.md.
DECISION/RATIONALE: Added excluded-source filtering (venue/publisher/source) to deep-analysis reference list construction so excluded venues are removed even when they appear via OpenAlex neighborhood expansion.

========
DATE: 2026-02-05
GOAL: Drop excluded sources immediately from all analysis and deep-analysis networks.
PROMPT: THINK HARD: Make sure these excluded items do not enter any analysis or networks. Drop them immediately.
FILES TOUCHED: server/miscite/analysis/pipeline/__init__.py; server/miscite/analysis/shared/excluded_sources.py; server/miscite/analysis/deep_analysis/deep_analysis.py; kb/promptbook.md.
DECISION/RATIONALE: Added early exclusion based on bibliography metadata/raw text to remove excluded references and their citations before matching/resolution, and filtered deep-analysis citation networks to remove excluded works when OpenAlex metadata indicates an excluded venue.

========
DATE: 2026-02-05
GOAL: Ensure excluded venues never enter the deep-analysis citation network.
PROMPT: THINK HARD: Don't included the excluded items in the networks at all. Drop them before constructing networks and any analysis.
FILES TOUCHED: server/miscite/analysis/deep_analysis/deep_analysis.py; kb/promptbook.md.
DECISION/RATIONALE: Filter excluded venues at the point of adding OpenAlex citing-works nodes (using list results when available, with a fallback metadata fetch) so excluded works are never added as nodes/edges in the deep-analysis graph.

========
DATE: 2026-02-05
GOAL: Ensure excluded-sources list is available in Docker builds so exclusions apply in production-ish Compose runs.
PROMPT: THINK HARD: Trace the pipeline, double check if and how excluded references are actually excluded every step immediately.
FILES TOUCHED: Dockerfile; kb/promptbook.md.
DECISION/RATIONALE: Dockerfile previously copied only `server/` (not `docs/`), so `docs/excluded_sources.txt` was missing in the container and exclusions silently did nothing. Updated Dockerfile to copy `docs/` into the image so `load_excluded_sources()` works in web + worker containers.

========
DATE: 2026-02-05
GOAL: Add report-page navigation sidebar + potential reviewer suggestions.
PROMPT: Add a floating navigation sidebar for long reports; add “Potential Reviewers” under the report title sourced from bibliographic coupling (“works that cite many of your references”).
FILES TOUCHED: server/miscite/analysis/deep_analysis/references.py; server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/templates/job.html; server/miscite/static/styles.css; AGENTS.md; kb/promptbook.md.
DECISION/RATIONALE: Derived reviewer candidates from OpenAlex authorships (name + institution) on bibliographic-coupling works and exposed them as `report.deep_analysis.potential_reviewers` for rendering; added a sticky sidebar TOC to keep long reports scannable while remaining responsive on small screens.

========
DATE: 2026-02-05
GOAL: Ensure all LLM and metadata API calls in the analysis pipeline are cached.
PROMPT: THINK HARD: Trace the whole pipleline, make sure all LLM and API calls are cached.
FILES TOUCHED: server/miscite/sources/predatory_api.py; server/miscite/sources/retraction_api.py; server/miscite/sources/test_list_api_cache.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: The only uncached runtime API path was “list-mode” custom predatory/retraction APIs, which previously fetched the full list over HTTP on every process/job. Added file-backed caching for these list fetches (via `Cache.get_text_file`/`set_text_file`) and unit tests to prevent regressions; documented cache layers and env vars in the dev docs.

========
DATE: 2026-02-05
GOAL: Report cache hits/misses in analysis outputs for debugging.
PROMPT: Report cache hitting for debugging purposes.
FILES TOUCHED: server/miscite/core/cache.py; server/miscite/analysis/pipeline/__init__.py; server/miscite/core/test_cache_debug.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added thread-safe cache debug counters (hit/miss/error/set) shared across cache scopes and surfaced a per-run snapshot as `report.cache_debug` so pipeline/debug reviews can see which namespaces hit cache without parsing logs.

========
DATE: 2026-02-05
GOAL: Confirm terminal output reports cache-hit diagnostics.
PROMPT: Double check the terminal reports cache hits.
FILES TOUCHED: server/miscite/worker/__init__.py; server/miscite/worker/test_cache_debug_summary.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added worker-side logging of per-job cache-debug summaries (hits/misses/errors/sets plus top namespaces) sourced from `report.cache_debug`, plus a unit test for summary formatting so terminal diagnostics remain stable.

========
DATE: 2026-02-05
GOAL: Make “Potential Reviewers” reliably populate from bibliographic coupling.
PROMPT: “Still shows ‘No reviewer candidates were found for this run.’”
FILES TOUCHED: server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/analysis/deep_analysis/references.py; server/miscite/templates/job.html; kb/promptbook.md.
DECISION/RATIONALE: Deep analysis could hit the node limit during second-hop expansion before collecting citing works, leaving the bibliographic-coupling bucket empty. Reordered expansion to collect citing papers first and changed OpenAlex summary fetching to preserve priority order (so coupling works get author/affiliation metadata within fetch limits). Updated the report template to distinguish “unavailable” (older reports without precomputed reviewers) from true empty results and to surface a hint when no citing works were collected.

========
DATE: 2026-02-05
GOAL: Clarify mismatch between cache misses and observed OpenAlex HTTP call volume.
PROMPT: “The API calls definately more than 282.”
FILES TOUCHED: server/miscite/sources/openalex.py; server/miscite/worker/__init__.py; server/miscite/worker/test_cache_debug_summary.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added explicit OpenAlex HTTP attempt counters (`http_request`) to cache debug metrics and surfaced `http_calls` in terminal summaries, so cache misses and raw outbound request volume are reported separately and can be compared directly.

========
DATE: 2026-02-05
GOAL: Report cache hits/misses per request type (with HTTP counts) for debugging.
PROMPT: Report cache hits by per request for debugging purposes.
FILES TOUCHED: server/miscite/worker/__init__.py; server/miscite/worker/test_cache_debug_summary.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Extended the worker’s per-job cache summary to include per-namespace `http` counts (when available) so you can correlate cache behavior with outbound request volume per request type without relying on verbose urllib3 debug logs.

========
DATE: 2026-02-05
GOAL: Report cache HIT/MISS for every cache lookup.
PROMPT: I mean report cache status for every request.
FILES TOUCHED: server/miscite/core/cache.py; server/miscite/core/config.py; .env.example; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added an opt-in debug flag (`MISCITE_CACHE_DEBUG_LOG_EACH`) that emits per-lookup cache HIT/MISS/EXPIRED lines (with safe OpenAlex hints) so request-by-request cache behavior can be audited without conflating misses with raw HTTP calls.

========
DATE: 2026-02-05
GOAL: Reduce repeat OpenAlex API calls on reruns by making deep-analysis expansion deterministic.
PROMPT: “Why still so many OpenAlex requests? … same manuscript … second time. Shouldn't have so many API calls.”
FILES TOUCHED: server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/analysis/deep_analysis/network.py; server/miscite/analysis/deep_analysis/test_network_determinism.py; kb/promptbook.md.
DECISION/RATIONALE: OpenAlex calls were dominated by deep-analysis neighborhood expansion, which previously used set→list conversions and `as_completed` ordering under node/edge budgets. That made the explored seed subset vary between runs/processes (hash randomization + completion timing), so reruns still discovered uncached work IDs and triggered fresh HTTP. Deep analysis now preserves key-ref order, uses ordered seed lists, and processes fetched works in input order; network-metric tie-breaking is also made stable. Added a regression test that runs the metric computation under different `PYTHONHASHSEED` values and asserts identical output.

========
DATE: 2026-02-05
GOAL: Make `http_calls` include all outbound analysis HTTP calls (not only OpenAlex).
PROMPT: “I want http_calls to count all outgoing calls.”
FILES TOUCHED: server/miscite/sources/http.py; server/miscite/llm/openrouter.py; server/miscite/sources/crossref.py; server/miscite/sources/pubmed.py; server/miscite/sources/arxiv.py; server/miscite/sources/predatory_api.py; server/miscite/sources/retraction_api.py; server/miscite/llm/test_openrouter_cache_debug.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added a shared `record_http_request()` helper and invoked it in every analysis-time outbound request path (OpenRouter, Crossref, PubMed, arXiv, predatory API, retraction API), counting each real HTTP attempt (including retries) under the same request namespace used for cache keys. This makes worker `http_calls` and per-namespace `http=` values reflect total outbound call volume across the full analysis pipeline.

========
DATE: 2026-02-05
GOAL: Split cache-hit diagnostics by storage type (JSON vs file) in worker summaries.
PROMPT: “Why separate JSON hits and file hits? ... Yes, differ the two types of hits.”
FILES TOUCHED: server/miscite/worker/__init__.py; server/miscite/worker/test_cache_debug_summary.py; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Worker cache summaries now expose `json_hits` and `file_hits` explicitly (while keeping total `hits`), and `top` namespaces now show `jh`/`fh` instead of a single aggregated `h`. This removes ambiguity for namespaces like `openrouter.chat_json` that can miss JSON cache but still hit file cache.

========
DATE: 2026-02-05
GOAL: Improve potential-reviewer selection to prioritize recency.
PROMPT: THINK HARD: improve Potential Reviewers selection logic by selecting authors of the most recent 10 "works that cite many of your references."
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/test_reviewers.py; server/miscite/templates/job.html; kb/promptbook.md.
DECISION/RATIONALE: Potential reviewers were previously aggregated from all bibliographic-coupling works, which could bias toward older or overly broad pools. Added a deterministic recency-first cutoff (10 newest coupling works, tie-broken by coupling order) before author aggregation, added unit tests for the cutoff behavior, and updated report copy to reflect the new selection rule.

========
DATE: 2026-02-05
GOAL: Redo potential-reviewer selection with coupling-order, recency, and cited-source overlap.
PROMPT: THINK HARD: Redo/improve the selection logic: top 50 coupling order, past 10 years, authors of those, keep authors with at least one publication in sources cited by the manuscript.
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/test_reviewers.py; server/miscite/templates/job.html; kb/promptbook.md.
DECISION/RATIONALE: Reviewer selection now follows a strict pipeline: take the top 50 coupling works in original order, filter to the past 10 years, collect authors from those works, and keep only authors whose recent coupling publications appear in the same sources (venue/source labels) as the manuscript’s cited references. This narrows reviewers to recent, source-aligned candidates while remaining deterministic.

========
DATE: 2026-02-05
GOAL: Make reviewer recency window configurable.
PROMPT: Make the 10-year window to be configurable, set 10 year as default.
FILES TOUCHED: server/miscite/core/config.py; server/miscite/analysis/deep_analysis/deep_analysis.py; .env.example; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added `MISCITE_DEEP_ANALYSIS_REVIEWER_RECENT_YEARS` (default 10) to Settings and wired it into the reviewer selection so recency can be tuned without code changes.

========
DATE: 2026-02-05
GOAL: Disable potential reviewers.
PROMPT: Return 0 reviewers. Double check.
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/test_reviewers.py; .env; .env.example; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Interpreted a 0-year reviewer window as “disable reviewer suggestions,” returning an empty reviewer list; updated the env and docs accordingly and added a test to enforce the behavior.

========
DATE: 2026-02-05
GOAL: Fix reviewer window behavior after misunderstanding.
PROMPT: “You misunderstood me, I mean I ran a test and got 0 reviewer, which is incorrect.”
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/test_reviewers.py; .env; .env.example; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Restored `recent_years=0` to mean “no recency filter” (include all years) and reset the local env to 10 so reviewer suggestions populate again.

========
DATE: 2026-02-05
GOAL: Add reviewer-debug stats to terminal logs.
PROMPT: Report related stats in terminal for debugging.
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/worker/__init__.py; server/miscite/worker/test_reviewer_debug_summary.py; kb/promptbook.md.
DECISION/RATIONALE: Added reviewer-debug counters during deep analysis and surfaced a concise summary in worker logs so terminal output shows where reviewer filtering is dropping candidates.

========
DATE: 2026-02-05
GOAL: Check author publication lists for source overlap and cache author retrieval.
PROMPT: THINK HARD: For inspecting source overlap: get detailed publication list of each candidate author; keep authors with at least one publication from sources cited by the manuscript; cache author retrieval calls and report it in cache summary stats.
FILES TOUCHED: server/miscite/sources/openalex.py; server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/analysis/deep_analysis/test_reviewers.py; server/miscite/worker/__init__.py; server/miscite/worker/test_reviewer_debug_summary.py; kb/promptbook.md.
DECISION/RATIONALE: Reviewer filtering now consults OpenAlex author works (cached via `openalex.list_author_works`) to verify source overlap with the manuscript’s cited venues; added reviewer-debug counters for author work lookups and surfaced them in terminal logs.

========
DATE: 2026-02-05
GOAL: Make author-works fetch size configurable for reviewer screening.
PROMPT: Fetch an author's most recent N works; make N configurable (default 100).
FILES TOUCHED: server/miscite/core/config.py; server/miscite/analysis/deep_analysis/deep_analysis.py; .env.example; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added `MISCITE_DEEP_ANALYSIS_REVIEWER_AUTHOR_WORKS_MAX` so reviewer screening can tune how many recent works per author are fetched without code changes, defaulting to 100.

========
DATE: 2026-02-05
GOAL: Use uncapped coupling list for reviewer suggestions and fill missing coupling metadata.
PROMPT: For reviewer suggestion, use the uncapped coupling list.
FILES TOUCHED: server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/worker/__init__.py; server/miscite/worker/test_reviewer_debug_summary.py; kb/promptbook.md.
DECISION/RATIONALE: Reviewer selection now pulls coupling nodes directly from network metrics (uncapped by display limits) and resolves missing coupling metadata via OpenAlex work lookups when needed; added debug counters for coupling work fetches in terminal logs.

========
DATE: 2026-02-05
GOAL: Print cited source names in reviewer debug logs.
PROMPT: Print out the names of these cited_sources in terminal for debugging.
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/worker/__init__.py; server/miscite/worker/test_reviewer_debug_summary.py; kb/promptbook.md.
DECISION/RATIONALE: Added a small deterministic sample of normalized cited-source names to the reviewer debug payload and surfaced it in worker logs for quick inspection.

========
DATE: 2026-02-05
GOAL: Use all cited references (not filtered deep-analysis refs) to derive cited_sources.
PROMPT: Significant sources cited are missed from the cited source sample. Double check the pipeline.
FILES TOUCHED: server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/worker/__init__.py; server/miscite/worker/test_reviewer_debug_summary.py; kb/promptbook.md.
DECISION/RATIONALE: Build cited-source labels from the full set of verified original references (using resolved metadata + OpenAlex records) and pass them into reviewer screening, so missing sources aren’t dropped by deep-analysis reference filtering. Added counts of cited refs with source metadata to the terminal debug summary.

========
DATE: 2026-02-05
GOAL: Order reviewer suggestions by author centrality with configurable metric.
PROMPT: Improve the order of authors: build coauthor network from coupling_top articles; compute degree/closeness/betweenness; order by degree by default; make order configurable.
FILES TOUCHED: server/miscite/analysis/deep_analysis/reviewers.py; server/miscite/analysis/deep_analysis/deep_analysis.py; server/miscite/analysis/deep_analysis/test_reviewers.py; server/miscite/core/config.py; server/miscite/worker/__init__.py; server/miscite/worker/test_reviewer_debug_summary.py; .env.example; docs/DEVELOPMENT.md; kb/promptbook.md.
DECISION/RATIONALE: Added coauthor-network centrality scoring from coupling-top works and ordered reviewers by the configured centrality metric (default degree). Exposed `MISCITE_DEEP_ANALYSIS_REVIEWER_ORDER` and logged the active order rule in terminal debug output.

========
DATE: 2026-02-05
GOAL: Improve end-to-end pipeline efficiency and remove redundant logic across exclusion filtering, matching, and summary aggregation.
PROMPT: THINK HARD: Analyze entire pipeline, improve the efficiency and remove redundancy.
FILES TOUCHED: server/miscite/analysis/shared/excluded_sources.py, server/miscite/analysis/pipeline/__init__.py, server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/analysis/match/match.py, server/miscite/analysis/deep_analysis/subsections.py, server/miscite/analysis/deep_analysis/references.py, server/miscite/analysis/match/test_match.py, kb/promptbook.md.
DECISION/RATIONALE: Added cached excluded-source loading and shared helpers to classify OpenAlex/resolved-work source labels in one place, then reused them in both pipeline and deep analysis to remove duplicated venue-matching code. Eliminated a full post-processing issue recount pass by using counts already returned from check stages. Added optional prebuilt reference indexing in citation↔bibliography matching and reused a single index across subsection-level matching to avoid rebuilding the same index per subsection. Also removed repeated deep-analysis second-hop expansion blocks via a shared helper and minor hot-path set allocation overhead.

========
Date: 2026-02-05
Goal: Simplify and refocus UI/UX across all pages for clearer task flow and better usability.
Prompt: Analyze all pages and optimize for simplicity, focus, and usability (reduce visual noise, tighten copy, improve navigation, and strengthen mobile usability).
Files touched: server/miscite/static/styles.css, server/miscite/templates/base.html, server/miscite/templates/home.html, server/miscite/templates/dashboard.html, server/miscite/templates/login.html, server/miscite/templates/billing.html, server/miscite/templates/report_access.html, server/miscite/templates/billing_success.html, server/miscite/templates/billing_cancel.html, server/miscite/templates/job.html, kb/promptbook.md.
Decision/rationale: Simplified global styling (lighter surfaces, tighter spacing, calmer typography), reduced redundant marketing/dashboard copy, made navigation context-aware, added mobile card-style table behavior, and improved long-report navigation with active section highlighting to keep users oriented and focused on primary actions.

========
Date: 2026-02-05
Goal: Restore decorative color expression after simplification made the UI feel too plain.
Prompt: Reintroduce decorative color elements across the site while preserving simplicity and usability.
Files touched: server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Added layered background gradients, accent treatments for header/footer/cards/panels/banners/alerts, richer hero/highlight card visuals, section-title and hero-title color bars, and re-enabled subtle landing reveal motion to keep the interface visually intentional without returning to clutter.

========
Date: 2026-02-05
Goal: Restore the original color UI after experimental decorative adjustments.
Prompt: Restore original color UI.
Files touched: server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Reverted the shared stylesheet to its original state so the site returns to the baseline brand color treatment and avoids the newer decorative color layer.

========
Date: 2026-02-05
Goal: Improve site-wide SEO coverage and metadata quality for public pages.
Prompt: Improve SEO of the whole site.
Files touched: server/miscite/web/__init__.py, server/miscite/routes/seo.py, server/miscite/routes/dashboard.py, server/miscite/templates/base.html, server/miscite/templates/home.html, server/miscite/static/og-image.svg, kb/promptbook.md.
Decision/rationale: Added path-aware SEO defaults (descriptions, keywords, robots, card types), stabilized canonical/public-origin handling, expanded Open Graph/Twitter metadata globally, enriched homepage JSON-LD with FAQ/WebSite/Organization schemas, introduced a dedicated social preview image, and expanded robots/sitemap coverage to include indexable public routes while keeping private/authenticated surfaces disallowed.

========
Date: 2026-02-06
Goal: Expose all reviewer centralities and allow user-side reviewer reordering.
Prompt: THINK HARD. For potential reviewers block, calculate all three centralities, and provide a filter for user to reorder. degree -> popularity; closeness -> ?? (an intuitive name); betweenness -> interdisciplinarity. Remove the option from env files.
Files touched: server/miscite/analysis/deep_analysis/reviewers.py, server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/templates/job.html, server/miscite/core/config.py, server/miscite/worker/__init__.py, server/miscite/analysis/deep_analysis/test_reviewers.py, server/miscite/worker/test_reviewer_debug_summary.py, .env.example, .env, docs/DEVELOPMENT.md, AGENTS.md, kb/promptbook.md.
Decision/rationale: Reviewer candidates now always include all three coauthor-network centralities (`degree`, `closeness`, `betweenness`) in the report payload and default backend ordering remains degree-first. The report UI now lets users reorder candidates by intuitive labels (Popularity, Reach, Interdisciplinarity) client-side, and the environment-level ordering toggle was removed to keep ranking behavior deterministic and UI-driven.

========
Date: 2026-02-06
Goal: Simplify reviewer scoring to popularity-only and tighten report-page alignment.
Prompt: Remove closeness/betweenness options and related calculations; default to popularity (degree). Double check report-page UI/UX and block alignment.
Files touched: server/miscite/analysis/deep_analysis/reviewers.py, server/miscite/analysis/deep_analysis/test_reviewers.py, server/miscite/templates/job.html, server/miscite/static/styles.css, AGENTS.md, kb/promptbook.md.
Decision/rationale: Removed reviewer-side closeness and betweenness centrality calculations and UI reordering controls, keeping a single deterministic popularity (degree) ranking with optional `popularity_score` display. Cleaned report reviewer block spacing/wrapping/list styling to improve visual alignment and consistency on the report page.

========
Date: 2026-02-06
Goal: Streamline report access-token UX and add downloadable branded PDF exports.
Prompt: "Optimize the UI/UX of the Access token block, remove redundant information. Provide a link to download report as a PDF file. Nicely format the PDF with branding and website information."
Files touched: server/miscite/templates/job.html, server/miscite/routes/dashboard.py, server/miscite/web/report_pdf.py, requirements.txt, AGENTS.md, kb/promptbook.md.
Decision/rationale: Simplified the owner token card by removing duplicate token/link messaging and redundant token-value controls, while keeping share-link generation, expiration controls, and rotation actions. Added owner/public report PDF routes (`/jobs/{id}/report.pdf`, `/reports/{token}/report.pdf`) backed by a new branded ReportLab renderer that includes report metadata, summary metrics, flagged issues, and site/report URLs.

========
Date: 2026-02-06
Goal: Add bounded API parallelism controls and parallelize API-heavy checks without tripping source rate limits.
Prompt: THINK HARD: analyze API calls that can run in parallel, and add two limits (per-job max parallel process + per-source global max parallel cap).
Files touched: server/miscite/sources/concurrency.py, server/miscite/sources/openalex.py, server/miscite/sources/crossref.py, server/miscite/sources/pubmed.py, server/miscite/sources/arxiv.py, server/miscite/sources/retraction_api.py, server/miscite/sources/predatory_api.py, server/miscite/sources/test_concurrency.py, server/miscite/sources/test_list_api_cache.py, server/miscite/llm/openrouter.py, server/miscite/core/config.py, server/miscite/analysis/pipeline/__init__.py, server/miscite/analysis/checks/reference_flags.py, .env.example, docs/DEVELOPMENT.md, AGENTS.md, kb/promptbook.md.
Decision/rationale: Introduced a shared API concurrency gate with one per-job limiter and per-source global limiters (shared across jobs in the same process), then wired all major source clients (including OpenRouter/custom APIs) through it. Added explicit env-configurable caps and propagated them through pipeline client construction. Also parallelized retraction/predatory flag checks across references while preserving deterministic issue order, improving throughput without increasing per-reference API call volume.

========
Date: 2026-02-06
Goal: Expand report PDF export to include full report-page content, including reviewer suggestions with hyperlinks.
Prompt: Improve the PDF to include all contents on the report page, including suggested reviewers (with hyperlink), etc.
Files touched: server/miscite/web/report_pdf.py, kb/promptbook.md.
Decision/rationale: Rebuilt the PDF renderer to cover report-page sections beyond summary/flags: potential reviewers (with clickable search links), deep-analysis recommendations (subsection plans + suggestion bullets), complete deep-analysis reference list with DOI/OpenAlex/official/PDF links, richer issue metadata/signals, and full methodology/source sections when available.

========
Date: 2026-02-06
Goal: Improve workspace usability and screen-space efficiency for day-to-day job management.
Prompt: THINK HARD: Analyze Workspace space, improve UX for usability.
Files touched: server/miscite/routes/dashboard.py, server/miscite/templates/dashboard.html, server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Added workspace-level job status counts and filtered-result metadata, then surfaced them in the dashboard via count-aware status pills, clearer result summaries, and contextual clear-filter controls. Improved upload ergonomics with client-side file type/size validation feedback and more informative file labels. Strengthened filter interactions with a keyboard shortcut (`/` for search focus), async loading state, and resilient fallback navigation. Implemented true mobile card rendering for the jobs table to eliminate horizontal-scroll dependency on smaller screens.

========
Date: 2026-02-06
Goal: Expand dashboard job management controls for faster triage and cleanup.
Prompt: 1) Move "Press / to focus search" inside the search box hint text; 2) Add a delete button to each job item; 3) Add bulk operations: Stop job and Delete report.
Files touched: server/miscite/templates/dashboard.html, server/miscite/static/styles.css, server/miscite/routes/dashboard.py, kb/promptbook.md.
Decision/rationale: Moved the keyboard hint into the search input placeholder while keeping `/` hotkey behavior. Added per-row delete forms in the dashboard actions column for direct cleanup. Introduced checkbox-based bulk selection with Select visible and two actions (Stop job, Delete report), backed by a new authenticated bulk-action route that reuses cancellation semantics and safely deletes uploaded files for owned jobs.

========
Date: 2026-02-06
Goal: Simplify dashboard controls by removing clear-filter shortcuts and consolidating bulk actions.
Prompt: 1. Remove the clear filter button. 2. Make the bulk functions drop list, with an apply button to apply selected bulk operation.
Files touched: server/miscite/templates/dashboard.html, server/miscite/static/styles.css, server/miscite/routes/dashboard.py, kb/promptbook.md.
Decision/rationale: Removed dashboard clear-filter CTA surfaces to reduce control noise and keep filtering interaction centered on direct search/radio/select inputs. Replaced multi-button bulk actions with a single bulk-action dropdown plus Apply button, with client-side state gating (requires selection + chosen action) and delete confirmation on submit.

========
Date: 2026-02-06
Goal: Remove low-value redundancy from report Recommendations and make actions cleaner for users.
Prompt: THINK HARD: Have a plan to improve and optimize the contents for users. Remove redundancies that do not have to much added value. (Dev-only path; no need to support old reports.)
Files touched: server/miscite/analysis/deep_analysis/recommendations.py, server/miscite/analysis/deep_analysis/test_recommendations.py, kb/promptbook.md.
Decision/rationale: Reworked recommendation aggregation to canonicalize section titles, merge near-duplicate actions within sections (same-claim overlaps by anchor/RID/similarity), and apply explicit action-type precedence (`reconsider > justify > add > strengthen`) during merges. Updated rendering payload generation so Top priorities are excluded from By section to avoid repeated content in new reports. Added focused tests for no global/section overlap, duplicate-merge behavior, and precedence handling.

========
Date: 2026-02-06
Goal: Improve recommendation usability with hoverable reference context and cleaner recommendation phrasing.
Prompt: THINK HARD: 1) show text tooltip on reference hover, 2) remove opening section, 3) rename By section, 4) start bullets with topic sentences.
Files touched: server/miscite/web/__init__.py, server/miscite/templates/job.html, server/miscite/web/report_pdf.py, server/miscite/analysis/deep_analysis/recommendations.py, server/miscite/analysis/deep_analysis/test_recommendations.py, server/miscite/web/test_filters.py, kb/promptbook.md.
Decision/rationale: Added tooltip-aware citation link rendering so recommendation reference links expose inline citation text on hover. Filtered synthetic `opening` recommendations at aggregation time. Updated recommendation headings/labels (`Other changes by section`) and rewrote bullet lead lines to start with concise action-first topic sentences (top priorities include section/location context). Added tests for opening-section suppression and tooltip link rendering.

========
Date: 2026-02-06
Goal: Surface source names in the deep-analysis reference list and align recommendation-link tooltips with list content.
Prompt: For the reference in ref list, show source names. (tooltip mirror contents in list)
Files touched: server/miscite/web/__init__.py, server/miscite/templates/job.html, server/miscite/analysis/deep_analysis/references.py, server/miscite/web/test_filters.py, kb/promptbook.md.
Decision/rationale: Added shared reference-format helpers to derive source labels (`source`, `venue`, `publisher`) and reused them for recommendation-link hover tooltips so hover text matches the reference-list presentation. Updated the reference list UI to show source names per entry and expanded deep-analysis reference payloads to include `source`/`publisher`/`openalex_id` consistently for new reports.

========
Date: 2026-02-06
Goal: Improve readability and visual hierarchy of the report Top priorities block based on screenshot feedback.
Prompt: See the screenshot under build. Optimize the layout.
Files touched: server/miscite/templates/job.html, server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Refined Top priorities into compact card-like items with a single lead title line (`• Priority N: short action - location`) and reduced visual clutter by removing duplicate list-dot markers from that block. Tightened spacing around chips/body/anchor/supporting refs to make scanning easier while preserving action semantics.

========
Date: 2026-02-06
Goal: Add PDF navigation aids with a beginning TOC and per-page return control.
Prompt: Build a TOC for the PDF at the beginning. Also add button on each page (except the first) to go back to the TOC.
Files touched: server/miscite/web/report_pdf.py, kb/promptbook.md.
Decision/rationale: Added a clickable Table of Contents block near the start of the PDF and anchored all major sections (`Summary`, `Potential Reviewers`, `Flags`, `Recommendations`, plus conditional sections). Updated footer rendering to draw a visible "Back to TOC" button on pages after page 1 using internal PDF link rectangles targeting the TOC anchor.

========
Date: 2026-02-06
Goal: Make report sharing explicitly owner-controlled with disabled-by-default behavior and cleaner Share access UX.
Prompt: THINK HARD and carefully: add an enable/disable sharing button (default disabled), hide redundant sharing controls while disabled, and move Download PDF to the top-right of the Share access block.
Files touched: server/miscite/routes/dashboard.py, server/miscite/templates/job.html, server/miscite/worker/__init__.py, AGENTS.md, docs/ARCHITECTURE.md, kb/promptbook.md.
Decision/rationale: Introduced an explicit owner sharing toggle route and persisted state using `access_token_hash` presence as the on/off gate. Disabling sharing clears the active token hash (report remains protected); enabling sharing restores/creates token material and reactivates hash with a valid expiration policy. Updated worker completion behavior to seed token material but keep sharing disabled by default (no automatic activation/email send). Simplified the Share access card by hiding token-expiration/rotation/link controls when sharing is off, and moved PDF download actions into each card header’s top-right alignment for faster access.

========
Date: 2026-02-06
Goal: Implement full Share access UX refinement plan (workflow focus, advanced disclosure, danger-zone separation, and measurable interaction metrics).
Prompt: Implement all proposed changes to improve Share access UI/UX (header/action hierarchy, minimal protected state, primary share flow, advanced access settings collapse, separated delete zone, tighter hierarchy, and quick UX metrics).
Files touched: server/miscite/templates/job.html, server/miscite/static/styles.css, server/miscite/routes/dashboard.py, server/miscite/templates/base.html, AGENTS.md, docs/ARCHITECTURE.md, kb/promptbook.md.
Decision/rationale: Rebuilt the owner Share access card around a single top-row control model (state pill + on/off toggle + PDF CTA) and shortened state messaging. When sharing is off, only protected-state guidance remains; when on, the share-link row is primary and token controls move into a collapsed "Advanced access settings" section. Delete action moved into a separate danger-zone card to reduce destructive-action misclicks. Added inline + toast feedback for copy/open/toggle/delete actions and introduced authenticated `POST /api/jobs/{id}/ui-metric` logging (via `AnalysisJobEvent` stage `ui_metric`) to track first copy/open latency, disable/delete misclick cancellations, and advanced-settings open rate without schema changes.

========
Date: 2026-02-06
Goal: Refine the owner report page layout for the protected-sharing state shown in screenshot feedback.
Prompt: THINK HARD: Improve the UI/UX of Screenshot 2026-02-06 125913.png.
Files touched: server/miscite/templates/job.html, server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Reduced right-column clutter in the disabled sharing state by removing the redundant empty control panel and replacing it with a single actionable helper sentence. Tightened Share access header hierarchy by grouping state + toggle together and shortening the PDF CTA label to reduce wrapping pressure. Lowered visual noise/risk for destructive actions by collapsing Danger zone behind a details disclosure and reducing its vertical separation from Share access for better column balance.

========
Date: 2026-02-06
Goal: Improve right-column balance and remove residual redundancy in the protected-share screenshot state.
Prompt: THINK HARD: Improve UI/UX according to Screenshot 2026-02-06 131121.png.
Files touched: server/miscite/static/styles.css, server/miscite/templates/job.html, kb/promptbook.md.
Decision/rationale: Removed flex auto-margin behavior that was forcing large vertical gaps between Share access and Danger zone cards, replacing it with explicit, consistent column spacing. Simplified disabled-sharing messaging by merging protection and next-step guidance into one concise sentence and dropping the extra helper line. Also removed redundant per-card margin utility in the right column to keep spacing system-driven and visually stable.

========
Date: 2026-02-06
Goal: Ensure Danger zone sits directly beneath Share access and expands downward when opened.
Prompt: Current: Clicking Danger zone expands upwards. Expected: place it right under Share access and expand downwards.
Files touched: server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Added section-specific top alignment for `#report-top .ds-grid` and switched the right column (`#report-top .span-5`) from flex to an explicit top-aligned grid stack. This prevents bottom-anchoring/stretch side effects and guarantees the Danger zone remains immediately below Share access with downward expansion behavior.

========
Date: 2026-02-06
Goal: Match the workspace "Recent analyses" table UX to screenshot-driven layout and interaction expectations.
Prompt: THINK HARD: Improve and optimize the UI/UX according to Screenshot 2026-02-06 151244.png.
Files touched: server/miscite/templates/dashboard.html, server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Scoped a workspace-specific UI refresh without changing backend contracts: promoted clearer section typography, tightened search/filter/sort controls, and refined bulk-action ergonomics (right-aligned select + apply flow). Updated jobs table presentation with stronger row hierarchy, status chip styling, processing indicator treatment, and action affordances (`View status` link + consistent report/delete buttons), with responsive adjustments to preserve usability on smaller screens.

========
Date: 2026-02-06
Goal: Remove sensitive source and methodology disclosure from the report page.
Prompt: For the report page, remove the sources and methodology section because the details are business secrets.
Files touched: server/miscite/templates/job.html, kb/promptbook.md.
Decision/rationale: Removed the `Sources & methodology` section from report rendering and deleted its sidebar navigation link/flag to ensure those internal details are not exposed in the report UI.

========
Date: 2026-02-06
Goal: Remove sensitive source and methodology disclosure from PDF exports.
Prompt: Also remove it from PDF.
Files touched: server/miscite/web/report_pdf.py, kb/promptbook.md.
Decision/rationale: Removed `Sources Used` and `Methodology Notes` from PDF output and from the PDF TOC so source/method internals are not disclosed in downloaded reports.

========
Date: 2026-02-06
Goal: Remove business-secret source labeling from per-reference report UX.
Prompt: Yes, also remove the business secrets from per-reference source labels.
Files touched: server/miscite/templates/job.html, server/miscite/web/__init__.py, server/miscite/web/test_filters.py, kb/promptbook.md.
Decision/rationale: Removed visible per-reference `Source(s)` labels from the deep-analysis reference list and changed citation hover tooltips to include only summary citation text (no source/venue/publisher labels). Updated filter tests to enforce source-label exclusion.

========
Date: 2026-02-06
Goal: Ensure PDF exports exclude remaining source-style disclosure fields.
Prompt: Make sure to also remove business secrets from PDF files.
Files touched: server/miscite/web/report_pdf.py, kb/promptbook.md.
Decision/rationale: Removed remaining source-style issue detail output in PDFs (`Journal` and `Publisher` lines under Flags) to keep business-sensitive source labeling out of exported reports.

========
Date: 2026-02-06
Goal: Preserve publication source names while hiding database/provider names in report and PDF surfaces.
Prompt: THINK HARD. Not to remove publication source names, remove database source names.
Files touched: server/miscite/templates/job.html, server/miscite/web/__init__.py, server/miscite/web/report_pdf.py, server/miscite/web/test_filters.py, kb/promptbook.md.
Decision/rationale: Restored publication-source labeling (`source`/`venue`/`publisher`) in the deep-analysis reference list and restored Journal/Publisher fields in PDF Flags output. Removed database/provider labeling by dropping OpenAlex render paths in report UI and PDF, and added a source-label filter that excludes known database names (`OpenAlex`, `Crossref`, `PubMed`/`NCBI`) while retaining publication names.

========
Date: 2026-02-06
Goal: Simplify and tidy the workspace "Recent analyses" controls based on screenshot feedback.
Prompt: THINK HARD: Improve the UI/UX based on Screenshot 2026-02-06 163634.png. It's too complicated and not neat.
Files touched: server/miscite/templates/dashboard.html, server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Reworked the workspace control hierarchy to reduce cognitive load: search + sort now anchor the top control row, status filters moved into a labeled compact cluster, typography scale was reduced for section title/subtitle, and bulk actions were redesigned into a tighter two-column control bar with clearer idle/active selection states. This keeps the same workflow while reducing visual noise and misaligned control emphasis.

========
Date: 2026-02-06
Goal: Make workspace filters/search more compact and align bulk controls on one right-aligned row.
Prompt: THINK HARD: For the Recent analyses, make the filer and search box smaller, in one row if possible. For the bulk action area, line dropdown menu and apply button on the same row ("apply" on right of dropdown, both right aligned).
Files touched: server/miscite/static/styles.css, kb/promptbook.md.
Decision/rationale: Tightened control sizing (search input, status chips, sort select) and switched desktop workspace controls to a compact three-column row so search + status filters + sort stay aligned on one line when space allows. Updated bulk-action controls to force a no-wrap, right-aligned inline arrangement with `Apply` immediately to the right of the dropdown.

========
Date: 2026-02-07
Goal: Expand handwritten red-stroke brand treatment to every major public brand surface.
Prompt: THINK HARD: Make it every major brand surface.
Files touched: server/miscite/templates/home.html, kb/promptbook.md.
Decision/rationale: Applied `miscite-wordmark` to all prominent visible `miscite` mentions on the landing page (hero lead, trust/governance messaging, and FAQ answers) while avoiding low-signal body overuse and non-visual metadata/JSON-LD strings. This keeps the branded signature consistent across high-impact marketing surfaces without reducing readability in dense prose.
