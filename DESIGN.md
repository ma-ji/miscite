# Design system (miscite)

This design system powers the FastAPI/Jinja templates and lives in `server/miscite/static/styles.css`.
It is a calm, typography-led system with subtle surfaces, consistent rounding, and clear focus states.

## Tokens

### Colors (light + dark)

Palette is based on Indiana University brand colors (Cream, Crimson, Light/Dark Crimson, Light/Dark Cream, Light/Dark Gray, IU Black).
Light theme uses the exact semantic mapping requested; dark theme keeps IU Black base with cream/white overlays and crimson actions.

IU palette reference:

- Crimson: `#990000`
- Light Crimson: `#F41C40`
- Dark Crimson: `#6D0808`
- Cream: `#FFFFFF`
- Light Cream: `#F8EFE2`
- Dark Cream: `#F5E3CC`
- Light Gray: `#EEEEF0`
- Dark Gray: `#B9C1C6`
- IU Black: `#072332`

- `--bg`
- `--surface`
- `--surface-2`
- `--control-bg`
- `--control-bg-disabled`
- `--text`
- `--muted`
- `--border`
- `--border-soft`
- `--primary`
- `--primary-hover`
- `--primary-active`
- `--primary-contrast`
- `--focus`
- `--focus-ring`
- `--link`
- `--link-hover`
- `--primary-soft`
- `--primary-soft-2`
- `--primary-border-soft`
- `--severity-high`
- `--severity-high-soft`
- `--severity-high-border`
- `--severity-medium`
- `--severity-medium-soft`
- `--severity-medium-border`
- `--severity-low`
- `--severity-low-soft`
- `--severity-low-border`
- `--bg-gradient-1`
- `--bg-gradient-2`
- `--skeleton-base`
- `--skeleton-sheen`

### Spacing scale

- `--space-1`: 4px
- `--space-2`: 8px
- `--space-3`: 12px
- `--space-4`: 16px
- `--space-5`: 24px
- `--space-6`: 32px
- `--space-7`: 48px

### Radii

- `--radius-sm`
- `--radius-md`
- `--radius-lg`

### Shadows

- `--shadow-1`
- `--shadow-2`
- `--shadow-3`

### Typography scale

- `--text-12`
- `--text-14`
- `--text-16`
- `--text-20`
- `--text-24`
- `--text-32`
- `--text-40`

## Theme support

- Automatic light/dark via `prefers-color-scheme`.
- Manual override: the header toggle sets `data-theme="light"` or `data-theme="dark"` on `:root` and persists to `localStorage` (`miscite-theme`).

## Component inventory

- **AppHeader**: `app-header`, `app-nav`, `app-actions`, `ds-theme-toggle`.
- **Buttons**: `ds-button`, `ds-button--primary`, `ds-button--secondary`, `ds-button--ghost`.
- **Inputs**: `form-field`, `form-label`, `ds-input-with-icon`, styled `input`, `select`, `textarea`.
- **Toggle**: `ds-toggle`, `ds-toggle-track`.
- **Card**: `ds-card`, `ds-card--subtle`, `ds-card--highlight`, `card-content`, `card-action`.
- **Alerts**: `ds-alert` with `--info`, `--success`, `--warning`, `--error`.
- **Table**: `ds-table`.
- **Disclosure**: `ds-disclosure-list`, `ds-disclosure` (native `details/summary`), severity variants `ds-disclosure--high|medium|low`.
- **Report layout**: `ds-severity-grid`, `ds-issue-grid`, `ds-meta`, `ds-quote`, `ds-chip`.
- **Empty state**: `ds-empty`.
- **Skeleton**: `ds-skeleton`, `skeleton-line`.
- **Layout utilities**: `ds-container`, `ds-grid`, `span-*`, `ds-section`, `ds-stack`.

## Usage notes

- Keep touch targets at least 44px (buttons, inputs, nav links already comply).
- Focus rings are always visible via `:focus-visible` and `--focus` tokens.
- Prefer the layout utilities and tokens instead of inline styles.
- Motion respects `prefers-reduced-motion` automatically.

## Starter page

The public landing page is `server/miscite/templates/home.html` and demonstrates the system:
hero + proof tiles, report preview, feature grid, workflow stepper, trust section, use-case cards,
FAQ disclosures, and CTA.

## Purpose

This document defines reusable UI/UX principles for building clear, consistent, and accessible product interfaces. These guidelines apply across pages and features.

---

## Universal UI Principles

### 1) One primary action per page

**Goal:** Make the user’s main task unmistakable.

- Every page must have a single primary user job that is visually dominant (placement, size, contrast).
- Secondary actions are allowed, but they must not compete with the primary action.

**Do**

- Make the primary CTA dominant in placement and contrast; keep secondary panels visually quiet.

**Don’t**

- Show multiple “primary” buttons or status panels that compete with the main workflow.

---

### 2) State-first design

**Goal:** The interface should always communicate what’s happening and what to do next.

- Design critical flows as explicit states: **idle → ready → in progress → success → failure**.
- Each state must include:
  - Clear status (what’s happening)
  - Next action (what the user can do now)
  - Recovery path (retry, help, details)

**Do**

- Use progress indicators and provide a clear next step on success (e.g., “View report”).

**Don’t**

- Leave users guessing about status or hide recovery behind vague errors.

---

### 3) Make blockers explicit and actionable

**Goal:** If something prevents progress, users should see it once and know how to fix it.

- Show blockers (billing, permissions, missing inputs) **once**, near the primary workflow.
- Pair every blocker with a direct resolution CTA.

**Do**

- Use a banner/alert with a clear action: “Activate billing”, “Grant access”, “Upload a file”.

**Don’t**

- Repeat blockers or show “inactive”/“error” without a path forward.

---

### 4) Turn history into a workspace

**Goal:** “Recent items” should help users accomplish work, not just record it.

- Treat tables/lists as tools, not logs.
- Treat tables/lists as tools with search, filters, sorting, and status-specific actions.
- Prefer human-readable summaries over raw identifiers.

**Do**

- Use friendly timestamps and show meaningful status with contextual actions.

**Don’t**

- Force scanning unstructured rows or show raw ISO timestamps in user-facing views.

---

### 5) Strong hierarchy, fewer containers

**Goal:** Reduce visual noise and increase clarity.

- Use whitespace, alignment, and typography before adding more boxes; prefer fewer, consistent surfaces over many competing cards.

**Do**

- Maintain a clear grid/padding and use borders/elevation sparingly.

**Don’t**

- Wrap every element in its own card or create a “flat wall of panels.”

---

### 6) Consistent components and tokens

**Goal:** Build predictable interfaces and move faster.

- Compose UI from standardized components (e.g., Button, Badge, Alert, Table, Input, Dropzone).
- Use design tokens for spacing, type scale, radii, elevation, and semantic colors (success/warn/error/info).

**Do**

- Keep variants small and intentional.

**Don’t**

- Introduce arbitrary spacing/font sizes/radii or new component styles without clear need.

---

### 7) Accessibility is baseline, not polish

**Goal:** Everyone can use the product; quality is consistent.

- Maintain readable contrast.
- Provide visible focus states.
- Ensure inputs have proper labels.
- Make all interactions keyboard-usable.
- Never rely on color alone to convey meaning.

**Do**

- Use semantic HTML (ARIA only when needed) and include labels/tooltips for status meaning.

**Don’t**

- Hide focus rings or use “light gray on beige” for important text.

---

### 8) Copy is part of the interface

**Goal:** Labels and messages should guide action.

- Use action-oriented labels (“Generate report”) rather than vague ones (“Submit”).
- Error messages must answer:
  - What happened
  - What it means
  - What to do next (in one step)

**Do**

- Keep microcopy concise, specific, and consistent.

**Don’t**

- Use generic language or show technical errors without interpretation.

---

## Checklist (use before shipping UI)

- [ ] Principles 1-8 are satisfied (primary action, state, blockers, workspace, hierarchy, components/tokens, accessibility, copy).
