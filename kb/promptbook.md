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
Files touched: server/miscite/worker/__init__.py, server/miscite/billing/stripe.py, server/miscite/routes/billing.py, server/miscite/routes/dashboard.py, server/miscite/core/models.py, server/miscite/core/config.py, server/miscite/templates/billing.html, .env.example, docs/DEVELOPMENT.md, kb/promptbook.md
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
Files touched: AGENTS.md, docs/ARCHITECTURE.md, server/miscite/analysis/match/__init__.py, server/miscite/analysis/match/index.py, server/miscite/analysis/match/match.py, server/miscite/analysis/match/types.py, server/miscite/analysis/parse/citation_parsing.py, server/miscite/analysis/parse/llm_parsing.py, server/miscite/analysis/pipeline/__init__.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/checks/reference_flags.py, server/miscite/analysis/checks/inappropriate.py, server/miscite/analysis/deep_analysis/prep.py, server/miscite/analysis/deep_analysis/deep_analysis.py, server/miscite/templates/job.html, kb/promptbook.md
Decision/rationale: Introduce a dedicated `analysis/match/` module to index references and link citations with confidence/ambiguity and candidate evidence; propagate match objects through checks and deep analysis for traceability; relax year usage in OpenAlex/Crossref search/scoring when a reference looks preprint/working-paper-like to avoid false mismatches due to multi-year publication gaps.

2026-02-03
Goal: Make preprint year-gap tolerance configurable and use LLM to disambiguate ambiguous citation↔bibliography matches.
Prompt: Make the preprint year gap configurable (default 5 years max) and enable LLM disambiguation for ambiguous citation matches.
Files touched: .env.example, AGENTS.md, docs/DEVELOPMENT.md, server/miscite/core/config.py, server/miscite/prompts/matching/bibliography_candidate/system.txt, server/miscite/prompts/matching/bibliography_candidate/user.txt, server/miscite/prompts/registry.yaml, server/miscite/analysis/match/__init__.py, server/miscite/analysis/match/llm_disambiguate.py, server/miscite/analysis/pipeline/__init__.py, server/miscite/analysis/pipeline/resolve.py, server/miscite/analysis/deep_analysis/prep.py, server/miscite/analysis/report/methodology.py, kb/promptbook.md
Decision/rationale: Add `MISCITE_PREPRINT_YEAR_GAP_MAX` to tune how metadata resolution scores year differences for preprint/working-paper-like references; add an LLM-only disambiguation step for ambiguous citation→bibliography links (with memoization and a shared per-job match-call budget) to improve matching accuracy while bounding cost.
