# Contributing to the MAPLE Website

Thank you for improving the MAPLE documentation website.

## Architecture

The deployed output remains static HTML. Shared behavior and presentation belong in these files rather than page-local copies:

- `assets/css/home.css`, `assets/js/home.js` — homepage.
- `assets/css/styles.css`, `assets/js/main.js` — documentation pages.
- `assets/css/search.css`, `assets/js/search.js` — site search UI and behavior.
- `assets/search-index.json`, `assets/search-index.js` — generated searchable sections and direct-file fallback.
- `tools/build_search_index.py` — search-index generator.

Documentation is organized under `tutorials/`, `setup/`, `tasks/`, and `functions/`.

## Adding or editing a page

1. Copy a maintained page at the same directory depth.
2. Keep stylesheet, script, image, navigation, and favicon paths relative to that depth.
3. Use lowercase filenames with underscores.
4. Give durable IDs to important headings that are linked externally.
5. Update all affected static navigation copies until navigation generation is centralized.
6. Rebuild the search index.

```bash
python3 tools/build_search_index.py
```

Do not add page-local CSS or duplicate interaction scripts when a shared component can express the behavior.

Search hierarchy is derived centrally by `navigation_trail()` in the index generator. Do not add keyword-specific ranking exceptions for individual queries; improve the shared taxonomy, headings, or generic ranking rules instead.

## Validation

Run the available static checks before submitting:

```bash
python3 tools/build_search_index.py --check
node --check assets/js/main.js
node --check assets/js/home.js
node --check assets/js/search.js
git diff --check
```

## Content boundaries

- Bind capability and parameter claims to an identified MAPLE release or development source.
- Do not turn “callable” or “energy available” into a claim that an entire optimization, frequency, solvent, or MD workflow is supported.
- Mark unverified combinations as unverified.
- Keep website-source licensing separate from MAPLE software and model/checkpoint terms.
