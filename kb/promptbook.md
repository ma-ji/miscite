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
TASK: Fix SyntaxError in server/miscite/routes/dashboard.py caused by malformed f-string in balance_display (seen in docker logs for miscite-web-1).
