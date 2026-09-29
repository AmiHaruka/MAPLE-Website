# MAPLE Website Aesthetic Maintenance Rules

This document records the design intent, implementation framework, and safe-maintenance rules for the MAPLE website aesthetic branch. It is meant for future maintainers who need to extend or repair the polished homepage/documentation experience without turning the site into a pile of one-off patches.

> Aesthetic direction: Jiahao Xie. Preserve content; tune only the shared visual system.

## 1. Core intent

MAPLE should feel like a serious scientific computing tool, not a generic template site.

The visual language is built around four ideas:

1. **Scientific precision** — clean grids, readable code/input blocks, restrained motion, clear documentation hierarchy.
2. **Maple identity** — red accent, leaf mark, warm paper background, and black editorial typography.
3. **Research-tool trust** — white cards, subtle borders, generous spacing, no decorative clutter that interferes with formulas, tables, or examples.
4. **One shared system** — homepage, docs, task pages, tutorials, and reference pages should look related even when their HTML structure differs.

The homepage is the visual source of truth. Documentation pages should inherit its mood without becoming marketing pages.

## 2. Non-negotiable rules

### Preserve content

- Do **not** rewrite scientific text during visual work.
- Do **not** reorder examples, units, parameters, or task descriptions for aesthetic reasons.
- Do **not** edit every HTML page to solve a presentation issue unless the HTML is semantically wrong.
- Prefer shared CSS and shared JS over page-local patches.

### Preserve maintainability

- No new dependencies for styling unless explicitly requested.
- No duplicated per-page CSS blocks.
- No hand-inserted syntax-highlight spans in HTML examples; use the shared highlighter.
- No generated visual assets unless they are intentionally committed and named clearly.

### Preserve mobile usability

- Every page must remain usable at 390px and 320px wide.
- Horizontal scrolling is a bug unless it is inside an intentional code/table scroll container.
- Mobile navigation and docs sidebar must never permanently cover the reading area.

## 3. File map and ownership

### Homepage surface

- `index.html` — homepage structure/content.
- `assets/css/home.css` — homepage design system and layout.
- `assets/css/home-fonts.css` — font imports shared by homepage/docs.
- `assets/js/home.js` — homepage-only interaction and reveal behavior.
- `assets/images/home/` — homepage logos, molecules, overview, generated icons.

The homepage sets the canonical mood: red/black/warm-white palette, editorial title type, precise scientific visual motifs, and elevated cards.

### Documentation/content surface

- `assets/css/styles.css` — shared docs/content design system.
- `assets/js/main.js` — shared documentation interactions: sidebar, copy buttons, generated TOC, mobile sidebar handle, MAPLE input highlighting.
- `assets/css/search.css`, `assets/js/search.js` — shared site-search presentation, keyboard behavior, and results UI.
- `assets/search-index.json`, `assets/search-index.js` — generated search data for HTTP and direct-file previews; rebuild with `tools/build_search_index.py` after searchable content changes.
- `tutorials/`, `setup/`, `tasks/`, `functions/` — content pages. Treat these primarily as scientific documentation, not style entry points.

Search results preserve the information hierarchy (`category › family › page`) and use one generic ranking pipeline. Prefer exact headings, complete scientific-token matches, and page candidates within the same relevance tier. Cap repeated results from one page rather than adding query-specific ranking overrides.

If visual consistency breaks on several pages, fix `styles.css` or `main.js`, not the individual HTML pages.

## 4. Design tokens

Keep homepage and docs tokens aligned. If fonts or palette change, update both `home.css` and `styles.css` together.

### Color vocabulary

Use variables rather than hard-coded colors where possible.

- Primary red: `#d32021`
- Active/secondary red: `#e23a2e`, `#f15a4f`
- Soft red background: `#fde8e6`, `#fff7f6`
- Ink: `#0c0c10`, `#1d1f25`, `#3b3e47`
- Muted text: `#6c707a`, `#9aa0aa`
- Lines: `#e5e6ea`, `#eef0f3`
- Paper: `#ffffff`, `#fafaf8`, `#f7f4ee`

The red is not a background paint bucket. It is a signal: active nav, small rule accents, code directives, icon accents, and rare hover states.

### Typography vocabulary

Current direction:

- Display: `Source Serif 4`, `IBM Plex Serif`, Georgia fallback. Source Serif 4 ships true 200–900 weight; IBM Plex Serif tops at 700 and serves only as a fallback. All display weights ≥ 800 must resolve to Source Serif 4 — synthetic bold on Plex Serif is not acceptable.
- Body: `IBM Plex Sans`, system sans fallback.
- Code: `IBM Plex Mono`, system mono fallback.
- Single escape hatch: hero floating equations (`.float-eq` in `home.css`) keep `Fraunces italic` for typeset-formula feel. Do not propagate Fraunces anywhere else.

Sizing strategy (post-migration off Inter/Fraunces):

- Display headlines are sized ~×1.15 relative to the previous Fraunces values to compensate for Source Serif 4 / Plex Serif rendering ~13–17% narrower at the same `font-size`.
- Body and UI sizes are +1px relative to the Inter era to compensate for Plex Sans's lower x-height.
- The desktop base is calibrated; the mobile `@media` font-size overrides in `home.css` and `styles.css` are intentionally preserved so narrow viewports keep their own tuning. Do not blindly scale mobile by the same ×1.15.

Rules:

- Use display serif for major headings and brand moments.
- Use sans for paragraphs, navigation, tables, cards.
- Use mono for code, command examples, parameter tags, and code-like labels.
- Do not shrink body text just to fit layout. Fix the layout instead.
- The font-family loaded in `home-fonts.css` is the asset budget. Adding a new family means removing an old one in the same change.

## 5. Page architecture

### Homepage

The homepage has a marketing/research identity:

- `site-header` + `main-nav` uses a high, airy navbar with a leaf mark.
- Hero combines molecular/scientific imagery with the MAPLE identity.
- “What is MAPLE?” and feature sections use cards, soft shadows, and red details.
- The platform overview image should be treated as a fixed asset. Do not redraw or modify it just to change layout; adjust CSS layout instead.

### ML potentials catalogue (three-level navigation)

The same set of ML potentials is surfaced at three depths. All three must stay in sync.

1. **Homepage tri-info first column** (`index.html` → `.tri-col` → `.ml-family-group`). One row per family: a clickable `<a class="ml-family-label">` plus a row of chips. The label and every chip in the row point at the same About-page anchor.
2. **About page** (`general.html` → `<section class="ml-family-section" id="<family>-family">`). One section per family. Each card inside is a wholly-clickable `<a class="card">` linking to the documentation page for that family. All cards within the same section share the same `href`.
3. **Documentation models pages** (`setup/model_<family>.html`). The deep technical reference.

Current taxonomy:

| Family | Members | About anchor | Docs page |
| --- | --- | --- | --- |
| UMA | UMA | `#uma-family` | `setup/model_uma.html` |
| ANI | ANI-2x, ANI-1x, ANI-1ccx, ANI-1xnr | `#ani-family` | `setup/model_ani.html` |
| AIMNet | AIMNet2, AIMNet2-NSE | `#aimnet-family` | `setup/model_aimnet.html` |
| FeNNol | FeNNix-Bio1 | `#fennol-family` | `setup/model_fennol.html` |
| MACE | MACE-OFF23, MACE-OMol, EGRET | `#mace-family` | `setup/model_mace.html` |

UMA is presented first as the broadest universal potential. EGRET sits inside MACE because its architecture derives from MACE.

Invariants when editing the catalogue:

- Same family ⇒ same `href`. A model can only appear in one family.
- A new model must be added in all three layers at once. Skipping any layer is a leak.
- Homepage chips always link to the About anchor, never directly to docs. The About card is what links to docs.
- Do not nest links inside an `<a class="card">`. The card is a single click target.
- Do not introduce per-model anchors on the homepage; chips share the family anchor by design.

### Docs/content pages

Docs should feel like a lab notebook wrapped in the homepage design system:

- `top-nav` mirrors the homepage header proportions and active red underline.
- `page-layout` provides a docs shell: left sidebar, center article, optional right TOC.
- `.content article`, `.page-body article`, and `.main-content` are elevated reading cards.
- `article h1/h2` use display typography and a small red gradient rule.
- Tables, admonitions, and code blocks must be readable before decorative.

## 6. Component rules

### Header/navigation

- Desktop nav should remain single-line until the mobile breakpoint.
- At tablet/mobile widths, switch to the hamburger menu early enough to avoid clipping.
- The active nav underline is red on desktop and hidden in stacked mobile nav.
- Keep the brand mark large enough to match homepage identity, but avoid pushing nav off-screen.

### Sidebar and mobile docs handle

- Desktop docs sidebar is persistent.
- Tablet/mobile docs sidebar is a drawer.
- The floating sidebar handle should be subtle and low-contrast when idle.
- Do not let sidebar overlays block reading after navigation or resize.

### Cards

Cards should look elevated but not flashy:

- White or warm-white background.
- Thin neutral border.
- Soft shadow.
- Red border/hover only as a hint.
- Slight upward hover is acceptable on desktop; keep mobile calm.

Cards may be wholly clickable as `<a class="card" href="...">`. In that case:

- Do not nest additional `<a>` tags inside; nested links break the click target and ship invalid HTML.
- Encode the destination once in the `href`. Trailing "→" or "Learn more" links inside the card body are redundant when the card itself is the link — remove them.
- Keep keyboard focus visible. The default link focus ring on `.card` must not be hidden.

### Admonitions

Admonitions appear in multiple HTML shapes:

```html
<div class="admonition tip">
  <div class="admonition-title">Tip</div>
  <div class="admonition-body">...</div>
</div>
```

and also:

```html
<div class="admonition tip">
  <p class="admonition-title">Tip</p>
  <p>...</p>
</div>
```

Therefore spacing rules must cover both `.admonition-body` and direct child paragraphs/lists.

Critical rule: **text must never sit close to the colored left stripe.** Maintain generous left padding for title and body content.

### Code blocks and MAPLE input examples

Generic shell/code blocks should remain clean and neutral.

MAPLE input blocks should be recognized automatically in `assets/js/main.js` and styled through `pre.maple-code` in `assets/css/styles.css`.

The shared highlighter currently recognizes:

- MAPLE directives such as `#model`, `#device`, `#charge`, `#mult`, `#sp`, `#opt`, `#ts`, `#scan`, `#irc`, `#freq`, `#md`, `#solv`, `#constraint`, `#constraints`.
- Direct values, e.g. `#model=uma`.
- Parenthesized parameters, e.g. `#opt(method=rfo)`.
- Coordinate rows: an atom label followed by **three or more decimal floats** (each token must contain a `.`). Integer-only rows do not qualify and are passed through as plain text — this disambiguates coordinates from SCAN commands.
- SCAN `S ...` command lines: `S` is rendered as a directive; the trailing numbers are split into three groups based on token count (4 = distance, 5 = angle, 6 = dihedral):
  - atom indices → `.atom-idx` (brown)
  - step size → `.step-size` (teal)
  - n_steps → `.n-steps` (gray)
- File references like `XYZ methane.xyz`.

Rules:

- Do not manually wrap example text with spans in HTML.
- If a new MAPLE directive is added, update the detector/highlighter in `main.js` and styling in `styles.css`.
- Do not make shell install commands look like MAPLE input. Installation commands should remain neutral code blocks.
- Copy buttons must copy original text, not the visual markup. The current implementation uses `textContent`, so keep that behavior.

### Tables

- Tables should be card-like and readable.
- Parameter values may use inline code with soft red background.
- On mobile, tables may scroll horizontally if necessary; the page itself must not.

### Icons and generated images

- Icons should use the red/ink/paper palette.
- Avoid emoji-like or toy-like icons on serious scientific cards.
- If generated raster icons are used, keep them in a clear asset folder and commit the source intent in the commit message.
- Prefer CSS/SVG/vector when the icon is structural; use generated bitmap only for genuinely illustrative assets.

## 7. SCAN tutorial and scientific-documentation rule

SCAN docs are scientific content first. Visual changes must not alter example semantics.

Known guardrails:

- Keep real, runnable examples rather than placeholder XYZ snippets.
- Preserve the expected ordering and syntax that runtime parsing requires.
- SCAN coordinate lines may be highlighted visually, but the highlighter must not change copied text.
- The `S` line highlighter is position-aware: it infers `atom_count = total_numbers - 2` and colors atom indices, step_size, and n_steps differently. Do not reorder tokens within an `S` line for cosmetic reasons — it inverts the coloring and misleads readers.
- If content changes are made, validate against the relevant MAPLE runtime branch rather than guessing from the website alone.

## 8. Responsive rules

Minimum checks:

- Desktop: 1365x900.
- Tablet-ish: around 800px wide.
- Mobile: 390x844.
- Narrow phone: 320px wide when layout changes touch nav, cards, pills, or tables.

A page passes only if:

- `document.documentElement.scrollWidth <= document.documentElement.clientWidth`, except for intentional internal table/code scroll areas.
- Header does not clip.
- Mobile nav opens/closes.
- Docs sidebar handle is available but not visually dominant.
- Code examples remain readable and copyable.

## 9. Maintenance workflow

Before editing:

```bash
git status --short --branch
```

If the user has uncommitted changes, do not overwrite them. Keep your changes narrow and explain what you touched.

For style work:

1. Identify whether the problem belongs to homepage (`home.css`) or shared docs/content (`styles.css`, `main.js`).
2. Fix the shared system first.
3. Avoid changing HTML unless the structure is semantically wrong.
4. Preview at desktop and mobile widths.
5. Verify no accidental content changes.

Recommended local preview:

```bash
python3 -m http.server 8023 --bind 127.0.0.1
```

Recommended browser probes:

```js
({
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
  title: document.title
})
```

Recommended validation:

```bash
node --check assets/js/main.js
python3 - <<'PY'
from pathlib import Path
s = Path('assets/css/styles.css').read_text()
stack = []
line = 1
for ch in s:
    if ch == '\n':
        line += 1
    elif ch == '{':
        stack.append(line)
    elif ch == '}':
        if not stack:
            raise SystemExit(f'unmatched closing brace at line {line}')
        stack.pop()
if stack:
    raise SystemExit(f'unclosed opening brace at lines {stack[-10:]}')
print('CSS brace balance OK')
PY
git diff --check
```

Representative pages to preview:

- `index.html` — homepage identity and mobile hero.
- `general.html` — top-level cards and content page style.
- `tutorials/installation.html` — shell code blocks and admonitions.
- `tutorials/input_output.html` — MAPLE input examples and docs flow.
- `tasks/opt/optimization.html` — task overview input examples.
- `tasks/opt/opt_rfo.html` — method-specific task input examples.
- `tasks/scan/scan.html` and SCAN subpages — SCAN examples and `S` line behavior.

## 10. Adding or modifying pages

When adding a new content page:

- Reuse the existing header/sidebar/footer skeleton.
- Use `page-hero`, `page-body`, `article`, `card-grid`, `card`, `admonition`, and `page-nav` classes where possible.
- Put code examples in plain `<pre><code>` blocks. Let the shared highlighter decide whether they are MAPLE input.
- Do not create a new page-specific stylesheet unless there is no shared alternative.

When adding a new homepage section:

- Use the homepage token names from `home.css`.
- Keep red accents sparse.
- Keep the section visually quieter than the hero unless it is the main conversion target.
- Validate mobile first; homepage art is the easiest place to create overflow.

## 11. Commit discipline

Use small commits with decision context. Follow the Lore-style trailer pattern already used in this branch:

```text
<why this change was made>

Constraint: <external constraint>
Rejected: <alternative> | <reason>
Confidence: <low|medium|high>
Scope-risk: <narrow|moderate|broad>
Directive: <future maintainer warning>
Tested: <checks performed>
Not-tested: <known gaps>
```

For aesthetic commits, include whether content was preserved and which representative pages were previewed.

## 12. What not to do

- Do not make docs look like a product landing page everywhere.
- Do not replace scientific clarity with decorative illustrations.
- Do not solve one spacing bug by editing one HTML page if other pages share the component.
- Do not change the platform overview image asset when the issue is layout.
- Do not remove the subtle source-level aesthetic direction comment unless the project intentionally changes ownership/style direction.
- Do not assume docs are runtime-correct just because they look polished.
- Do not add a fifth font family without removing one. Do not propagate the `Fraunces` escape hatch outside `.float-eq`.
- Do not let homepage chip groups and About `.ml-family-section` drift apart. They are one catalogue with two presentations.

## 13. Stop condition for future visual passes

A visual pass is complete only when:

- The homepage and docs feel like one system.
- No visible content has changed unless explicitly requested.
- Desktop and mobile representative pages pass visual inspection.
- No unexpected horizontal page scroll exists.
- Shared code blocks, admonitions, cards, sidebars, and nav remain usable.
- The diff is explainable as shared-system maintenance rather than scattered styling hacks.
