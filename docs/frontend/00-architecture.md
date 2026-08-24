# Frontend — architecture

> Serves [RULE 1 — separation of concerns](../rules/01-separation-of-concerns.md).
> Status: **executed.** The tree below is the current state of `frontend/`.

## Root layout

Everything is a sibling. `app/` holds routing and nothing else.

```
frontend/
├── api/              HTTP layer — the only thing that knows the Brain exists  → 01-api-layer.md
├── app/              Next.js ROUTING ONLY: page.tsx, layout.tsx, globals.css
├── components/
│   ├── global/       zero-domain-coupling primitives, reusable anywhere
│   └── views/        one folder per view
├── constants/        app-wide constants (poll intervals, limits)
├── hooks/            app-wide React hooks
├── stores/           client state (zustand when there is a reason — empty for now)
├── scripts/          build/dev scripts (empty for now)
├── types/            app-wide types
└── utils/            app-wide pure functions
```

`stores/` and `scripts/` are deliberate placeholders: the architecture says where they go, so
nobody has to invent a location the day they are needed.

## What is a view

> *A view is a screen or page level thing. It can also be a large modal. The test is
> attention: a view is **not** the ten different things on the page — it is the thing that is
> **holding** those ten things.*

So `/` is **one** view (the dashboard) that holds six panels. Each panel is a `_component` of
that view, not a view of its own. A big modal that takes over the screen is a view; a panel
sitting inside a page is not.

## View anatomy

Every view has the same four parts. `_components` are recursively identical.

```
components/views/printer-detail/
├── index.ts                          ← THE DOOR. Nobody imports past this.
├── PrinterDetail.tsx                 ← export default. Rendering only.
├── _helpers/
│   ├── index.ts                      ← the door again
│   ├── printer-detail.functions.ts
│   ├── printer-detail.const.ts
│   ├── printer-detail.types.ts
│   ├── printer-detail.hooks.ts       (view-local React hooks)
│   └── printer-detail.styles.css
└── _components/
    └── detail-header/
        ├── index.ts
        ├── DetailHeader.tsx
        ├── _helpers/                 ← same shape
        └── _components/              ← same shape (only if genuinely needed)
```

**Only create the helper files a view actually needs.** An empty `printer-detail.styles.css`
is exactly the "code for the sake of code" this architecture exists to prevent.

### Styles are `.css`, not `.ts`

Next.js only accepts plain-CSS imports from `app/layout.tsx`; component-level CSS must be a
`.module.css`. A `.styles.ts` would need a CSS-in-JS dependency, so view styles are
**`<view>.styles.css`, colocated with the view and imported from `app/layout.tsx`**. Class
names stay global — the win is organisation (one view's styles are one file, next to it), not
scoping. Moving to CSS Modules for real scoping is a clean follow-up; it would mean rewriting
every `className="card"` as `className={styles.card}`.

**Import order in `layout.tsx` is load-bearing:** globals (tokens) → view styles →
`responsive.css` LAST. The media queries override classes from four different views at equal
specificity, so source order is the only thing that makes them win.

### View-local hooks

A hook used by exactly one view is `<view>.hooks.ts` in that view's `_helpers`. Only hooks
used across views go in the root `hooks/`.

## The rules

**1. `index.ts` is the door.** Nothing outside a folder may import past its `index.ts`. A
consumer writes `import PrinterDetail from "@/components/views/printer-detail"` and learns
nothing about what is inside. That is the whole point of an index file.

**2. `_` marks internals.** `_helpers` and `_components` belong to their parent and are
invisible to everyone else. If two views need the same `_component`, it was never a
`_component` — promote it to `components/global/`.

**3. Naming.** Folders are `kebab-case`. Component files are `PascalCase.tsx` and match their
folder. Helper files are prefixed with the folder name: `printer-detail.functions.ts`. A view
is **not** suffixed `View` — it is already inside `views/`.

**4. Depth.** A view may hold `_components`, and a `_component` may hold `_components`. That
is the limit. A third level means the view was drawn wrong — stop and re-cut it rather than
nesting further.

**5. Length.** Target **80–100 lines** per `.tsx`. Past that, readers skim instead of read.
Opening a view file should show *rendering* — constants, types, helpers, and styles are all
behind contracts elsewhere.

## Where things live

| Thing | Home | Test |
|---|---|---|
| Used by 2+ views, no domain knowledge | `components/global/` | Would it work in a different app? |
| Used by one view | that view's `_components/` | — |
| Pure function, app-wide | `utils/` | No React, no domain state |
| Pure function, one view only | that view's `_helpers/*.functions.ts` | — |
| React hook | `hooks/` | Stateful → not a util |
| Constant used across views | `constants/` | — |
| Constant used in one view | that view's `_helpers/*.const.ts` | — |
| Type from the server | `api/types.ts` (generated) | Never hand-write it |
| Type used across views | `types/` | — |
| Type used in one view | that view's `_helpers/*.types.ts` | — |
| Hook used in one view | that view's `_helpers/*.hooks.ts` | — |
| Styles for one view | that view's `_helpers/*.styles.css` | Imported from `app/layout.tsx` | — |

`components/global/` is gated on **zero domain coupling**, not on call-site count. `JsonTree`
qualifies — it renders arbitrary JSON and knows nothing about printers. `HealthPill` does not
— it calls `API.health` and belongs to the dashboard.

## Routing

`app/` contains route files only. A route file resolves params and renders exactly one view.

| Route | View |
|---|---|
| `/` | `components/views/dashboard` |
| `/printers/[id]` | `components/views/printer-detail` |

```tsx
// app/printers/[id]/page.tsx — this is the whole file
import PrinterDetail from "@/components/views/printer-detail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PrinterDetail id={decodeURIComponent(id)} />;
}
```

`app/layout.tsx` (fonts, metadata) and `app/globals.css` (resets + design tokens) stay in
`app/` — they are framework contracts, not views. This section splits into its own
`02-routing.md` when the route count earns it; with two routes a separate file would be
ceremony.

## Target tree

```
components/
├── global/
│   └── json-tree/
└── views/
    ├── dashboard/                        the "/" screen
    │   ├── index.ts · Dashboard.tsx · _helpers/
    │   └── _components/
    │       ├── health-pill/
    │       ├── prompt-panel/             └ _components/prompt-card/
    │       ├── swap-strip/               └ _components/{state-pill,orch-strip}/
    │       ├── printer-cards/            └ _components/printer-card/
    │       ├── job-flow/                 └ _components/{job-upload,filament-mapping}/
    │       ├── spool-inventory/          └ _components/{spool-row,add-spool-form}/
    │       └── loadout-panel/            └ _components/printer-loadout/
    └── printer-detail/                   the "/printers/[id]" screen
        ├── index.ts · PrinterDetail.tsx · _helpers/
        └── _components/{detail-header,field}/
```

Deepest path is two `_components` levels — inside the limit, no re-cut needed.

## Migration map

| Today | Target |
|---|---|
| `app/components/*.tsx` (11 files) | `components/views/**` — out of `app/` entirely |
| `app/page.tsx` composition | `views/dashboard/Dashboard.tsx` |
| `lib/usePolling.ts` | `hooks/usePolling/` — then `lib/` is deleted |
| `swatchColor` ×3 identical copies | `utils/color.ts` — one copy |
| `gramsLabel`, `grams` | `utils/format.ts` |
| `POLL_MS` ×6, five different values | `constants/polling.ts`, named per surface |
| `JsonValue` (in `api/types.ts`) | `types/json.ts` — it is not an API type |
| `num`, `str`, `temp`, `hmsMessages` | `views/printer-detail/_helpers/*.functions.ts` |
| `globals.css` (1,691 lines) | 305 lines of tokens/resets/shared; 1,347 moved to 9 `*.styles.css`; media queries split to `app/responsive.css` |

Worst offenders before the split: `SpoolInventory` 471, `PrinterDetailView` 257,
`FilamentMapping` 211 — each held several components plus helpers in one file. After it, the
largest `.tsx` in the app is 121 lines and the median is 26.

`components/global/` starts nearly empty, and that is honest — today nothing except
`JsonTree` is genuinely shared. It fills as real reuse appears, not before.
