# MkDocs landing page: animated isometric hero + tiles

## Overview

**Goal**: make the first page ([`docs/index.md`](docs/index.md)) of the MkDocs site more visual: an animated, pseudo-3D (isometric) hero showing the data flow, followed by a grid of tiles with screenshots that present the application capabilities. The existing narrative content stays below the new landing section.

**Approach** (decided with the user):
- Animated **isometric SVG + CSS** hero, no JavaScript library, no CDN. The site is static (GitHub Pages), so this works offline and with `navigation.instant`.
- Hero flow: *Transaction app (PostgreSQL)* -> *Debezium CDC* -> *Kafka cluster with topic lanes* -> *Flink processing* -> *Data lake (Iceberg / Tableflow)*, with glowing "record" bubbles travelling along the pipes. Serving side (Lightning / snapshot queries) shown as a small branch.
- Tiles built with Material "grid cards" (`attr_list` + `md_in_html` are already enabled in [`mkdocs.yml`](mkdocs.yml)) using existing screenshots in `docs/images/app/`.
- A Three.js version is a possible later evolution, intended for the real frontend app (`apps/frontend`), not for the docs. Out of scope here.

**Non-goals**: no change to the content of the other pages, no new Python/JS dependency, no change of theme, no rewrite of existing sections of `index.md`.

**Constraints noted from the repo**:
- Theme is `material` with `attr_list`, `md_in_html`, `pymdownx.emoji` (Material icons usable as `:material-...:`) already on; no `extra_css` / `extra_javascript` yet; no `docs/**/*.css|js` exist.
- `minify` plugin (`minify_html: true`) is active: keep inline SVG valid and avoid relying on whitespace.
- No GitHub Pages deploy workflow found in the repo (only `.github/workflows/build-and-push.yaml`), so the site is presumably published with `mkdocs gh-deploy`; static assets under `docs/` are published automatically, which is all this plan needs.
- Existing visuals to reuse for tiles: `docs/images/app/home_page.png`, `statement_graph.png`, `cep_fraud.png`, `querying_with_chat_rtce.png`, `crm_billing_graph.png`, `customers.png`, `docs/images/notebook_and_LT.png`, `docs/images/dbt_lineage_graph.png`.

---

## Sub-task 1 - Styling and asset scaffolding

**Intent**: provide the CSS foundation (hero container, animations, tile styling) that works in both light and dark Material palettes.

**Expected Outcomes**
- `docs/stylesheets/landing.css` exists and is registered through `extra_css` in `mkdocs.yml`.
- Dark gradient hero banner, CSS keyframes for bubble motion along pipes, subtle glow/pulse on nodes, hover lift on tiles.
- `prefers-reduced-motion` disables animation.

**Todo List**
1. Create `docs/stylesheets/landing.css`.
2. Add `extra_css: [stylesheets/landing.css]` to `mkdocs.yml`.
3. Define CSS variables for colors (Kafka, Flink, lake accents) and use Material variables where possible for text.
4. Add `@media (prefers-reduced-motion: reduce)` rule.
5. Hide the default page title on the landing page if it duplicates the hero (check how the page renders).

**Relevant Context**: [`mkdocs.yml`](mkdocs.yml) (theme/palette/extensions), Material grid cards need `attr_list` and `md_in_html` (already present).

**Status**: [x] done

---

## Sub-task 2 - Animated isometric SVG hero

**Intent**: the "wow" element: a pseudo-3D scene of the pipeline with records flowing.

**Expected Outcomes**
- `docs/images/hero_streamhouse.svg` (hand-written SVG, isometric projection using skewed/rotated shapes) displaying, left to right:
  1. Transaction app + PostgreSQL (cube/cylinder).
  2. Debezium CDC pipe.
  3. Kafka cluster: three brokers (blocks) with topic lanes `cdc.public.customers`, `accounts`, `transactions`.
  4. Flink block (src -> dim -> fact stages) producing golden-record topics.
  5. Data lake: Iceberg tables / object storage (stacked layers) via Tableflow.
  6. Small branch to "Lightning / snapshot queries" and "AI agent".
- Animated bubbles (SVG `<animateMotion>` or CSS offset-path) travel along the pipes, change color after Flink (raw -> enriched), and land in the lake.
- Labels legible, readable on small screens (scales with `viewBox`).

**Todo List**
1. Design the layout on an isometric grid (30-degree axes), define reusable `<symbol>` / `<defs>` for cube, cylinder, pipe segment, bubble gradient and glow filter.
2. Draw the static scene (nodes, pipes, labels).
3. Add bubble animations (staggered `begin` offsets, looping, different speeds per lane).
4. Add node pulse animation on Kafka and Flink.
5. Decide how to embed: inline in `index.md` (needed for CSS-variable theming and animation reliability) versus `<img>` (SMIL animations work in `<img>` but CSS from the page does not). Prefer inline via a snippet include (`pymdownx.snippets` is enabled) to keep `index.md` readable.
6. Verify minify plugin does not break the SVG.

**Relevant Context**: `docs/diagrams/stream-cc-arch.drawio.png` and `docs/diagrams/raw-to-sink.drawio.png` (existing content to stay consistent with: Capture, Transport, Transform, Serve, Governance); `AGENTS.md` sections 3 and 6 (topics `cdc.public.*`, Debezium, Tableflow).

**Status**: [x] done

---

## Sub-task 3 - Landing section and tiles in `index.md`

**Intent**: replace the plain opening of `docs/index.md` with a hero + tagline + tiles, keeping the rest of the page.

**Expected Outcomes**
- Top of `index.md`: hero banner (title "Streamhouse Customer 360", one-line tagline from the existing user story), embedded SVG, call-to-action buttons (Demo script, Deployments, GitHub repo).
- Grid of tiles (screenshot + short title + one sentence + link to the matching existing section/page), covering: Hybrid CDC ingestion, dbt + Flink pipelines, Snapshot and lateral joins, Lightning queries / Jupyter, Fraud CEP, Chat with RTCE, Statement lineage graph, Billing.
- Existing "Purpose" text and below remain, reachable by scrolling; anchors referenced by other pages (e.g. `#create-debezium-cdc-v2-kafka-connector` in `sre_ccloud.md`, `#data-science-and-ad-hoc-analytics-with-jupyter-notebook` in `demo_script.md`) not broken.

**Todo List**
1. Check which anchors in `index.md` are linked from other docs (grep `index.md#`) before editing headings.
2. Insert hero block (HTML with `md_in_html`) above `## Purpose`.
3. Add `<div class="grid cards" markdown>` tiles with images (`{ loading=lazy }`) and links.
4. Add a short "Capture - Transport - Transform - Serve - Govern" chip row linking to the architecture sections.
5. Verify image paths resolve relative to `docs/`.

**Relevant Context**: [`docs/index.md`](docs/index.md) (lines 1-27 hold the current intro), screenshots listed in the Overview.

**Status**: [x] done

---

## Sub-task 4 - Validation and polish

**Intent**: confirm the page renders correctly locally and the site still builds.

**Expected Outcomes**
- `mkdocs build --strict` (or at least `mkdocs build`) succeeds with no new warnings (broken links/images).
- Visual check with `mkdocs serve` in light and dark palette, desktop and narrow width; animation respects reduced motion.
- No external network requests added by the hero.

**Todo List**
1. Run `mkdocs build` and fix any warnings related to the new files.
2. Run `mkdocs serve`, review the page in the browser, adjust spacing/colors.
3. Check navigation (`navigation.instant`) still animates correctly when coming back to the landing page.
4. Update this plan status to done.

**Relevant Context**: [`mkdocs.yml`](mkdocs.yml); the mkdocs tool/plugins installation is not captured in a repo dependency file I found, so confirm how the docs environment is run locally before validating.

**Status**: [x] done
