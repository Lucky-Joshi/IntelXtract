# IntelXtract Brand Guide

Visual and verbal identity for the IntelXtract platform. All UI themes,
reports, docs, and marketing assets derive their tokens from this document.

## Brand summary

- **One-liner:** AI-powered OSINT automation and intelligence platform.
- **Positioning:** "The VS Code of OSINT" — a workspace, not a lookup tool.
- **Personality:** precise, calm, professional, investigative, trustworthy.
- **Audience:** security researchers, SOC analysts, investigators, students,
  journalists, IT administrators.

## Logo

| Asset | Path | Use |
|-------|------|-----|
| Horizontal lockup | `assets/logo.svg` | README, docs, title bars, reports |
| App icon | `assets/icon.svg` | Window/taskbar icon, favicon, app tile |

Mark: a shield (defense, trust) containing a magnifying glass (investigation,
search) filled with the primary→accent gradient.

### Usage rules

- Keep clear space equal to the shield's width (≈ 25% of icon height) on all
  sides of the lockup.
- Minimum sizes: lockup 120 px wide; icon 16 px (simplified legibility holds
  because the mark has no fine detail).
- On dark backgrounds use the standard lockup (light wordmark). On light
  backgrounds, set the "Intel" tspan to `#0F172A`.
- Do **not**: recolor the gradient, stretch, rotate, add drop shadows or
  outlines, place the mark on busy imagery, or recreate the wordmark in a
  different typeface.

## Color palette

Dark theme is the default. Light theme (post-1.0) reuses accents with
inverted neutrals.

### Core

| Token | Hex | Role |
|-------|-----|------|
| `ix-bg` | `#0B1220` | App background |
| `ix-surface` | `#111A2C` | Cards, panels, sidebar |
| `ix-surface-2` | `#1A2438` | Hover / elevated rows |
| `ix-border` | `#1E293B` | Dividers, outlines |
| `ix-primary` | `#3B82F6` | Primary actions, links, selection |
| `ix-accent` | `#22D3EE` | Highlights, active state, wordmark |
| `ix-primary-hover` | `#2563EB` | Hover state of primary actions |

### Text

| Token | Hex | Role |
|-------|-----|------|
| `ix-text` | `#E2E8F0` | Primary text |
| `ix-text-secondary` | `#94A3B8` | Labels, captions |
| `ix-text-muted` | `#64748B` | Placeholders, disabled |

### Semantic status

| Token | Hex | Role |
|-------|-----|------|
| `ix-success` | `#22C55E` | Passed checks, healthy plugins |
| `ix-warning` | `#F59E0B` | Degraded, skipped, deprecation |
| `ix-danger` | `#EF4444` | Errors, failed scans |

### Risk severity (used by risk engine, reports, charts)

| Level | Hex | Score band |
|-------|-----|------------|
| Low | `#22C55E` | 0–24 |
| Medium | `#F59E0B` | 25–49 |
| High | `#F97316` | 50–74 |
| Critical | `#EF4444` | 75–100 |

## Typography

| Role | Stack | Notes |
|------|-------|-------|
| UI / headings | `Inter, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif` | Weights 400/500/600/700 |
| Monospace (code, hashes, domains, CLI) | `"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` | Weight 400/500 |
| Reports (HTML/PDF) | Same as UI; embed Inter + JetBrains Mono when licensing permits, otherwise rely on the fallback stack | — |

Scale (px at 100% zoom):

| Token | Size / line-height | Use |
|-------|--------------------|-----|
| `title-lg` | 28 / 36 | Page titles |
| `title-md` | 20 / 28 | Section headers |
| `title-sm` | 16 / 24 | Card headers |
| `body` | 14 / 22 | Default text |
| `caption` | 12 / 16 | Labels, table meta |
| `mono` | 13 / 20 | Data display |

## Spacing & shape

- **Grid:** 4 px base unit; use multiples (4, 8, 12, 16, 24, 32, 48).
- **Radius:** small 6 px (inputs, buttons) · medium 10 px (cards) · large
  16 px (modals, dialogs).
- **Elevation:** borders (`ix-border`) preferred over shadows; when a shadow
  is needed use `0 4px 16px rgba(0,0,0,0.45)`.
- **Density:** data tables use compact rows (32 px) with 12 px cell padding.

## Iconography

- 20 px stroke icons, 1.75 px stroke weight, rounded caps, single color
  (`ix-text-secondary`, accent when active).
- Never mix filled and outline styles in one view.

## Voice & tone

- **Precise:** state facts and evidence; never overstate confidence.
- **Neutral:** findings are reported, not judged; severity comes from the
  risk engine, not adjectives.
- **Actionable:** errors say what happened and what to do next.
- **Ethical:** language reinforces authorized, public-data-only use.
- AI-generated content (Phase 23) must be labeled and must never read as
  collected evidence.
