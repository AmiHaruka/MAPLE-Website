# CLAUDE.md

Repository guidance for the MAPLE documentation website.

## Project

MAPLE means MAchine-learning Potential for Landscape Exploration. This repository is the static HTML/CSS/JavaScript website at `ClickFF/MAPLE-Website`; it is separate from the MAPLE software repository and its license.

## Local development

```bash
python3 -m http.server 8000
```

Serve the repository rather than relying on `file://`, because clipboard and search behavior require an HTTP context for representative testing.

## Shared surfaces

- Homepage: `index.html`, `assets/css/home.css`, `assets/js/home.js`.
- Documentation: `assets/css/styles.css`, `assets/js/main.js`.
- Search: `assets/css/search.css`, `assets/js/search.js`, generated `assets/search-index.json` and `assets/search-index.js`.
- Content: `tutorials/`, `setup/`, `tasks/`, `functions/`.
- Search generator: `tools/build_search_index.py`.

All page paths are relative. Root pages use `assets/...`, one-level pages use `../assets/...`, and two-level pages use `../../assets/...`.

## Required checks

After changing searchable content, regenerate and check the index:

```bash
python3 tools/build_search_index.py
python3 tools/build_search_index.py --check
```

Before completing a site-wide change:

```bash
node --check assets/js/main.js
node --check assets/js/home.js
node --check assets/js/search.js
git diff --check
```

Prefer shared CSS/JS and deterministic generated artifacts over page-local duplication. Preserve the distinction between published-release documentation and explicitly marked development behavior.
