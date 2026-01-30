# Design system (miscite)

This design system powers the FastAPI/Jinja templates and lives in `server/miscite/static/styles.css`.
It is a calm, typography-led system with subtle surfaces, consistent rounding, and clear focus states.

## Tokens

### Colors (light + dark)
Defined on `:root` with automatic `prefers-color-scheme` and optional manual override.
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
