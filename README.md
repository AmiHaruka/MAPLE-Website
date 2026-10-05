# MAPLE Website

Static documentation website for MAPLE (MAchine-learning Potential for Landscape Exploration). The site is built with HTML, CSS, and vanilla JavaScript and can be served by any static web server.

## Local preview

```bash
python3 -m http.server 8000
```

Open <http://localhost:8000/>. Serving the files over HTTP is recommended because clipboard and search behavior cannot be validated reliably from `file://` URLs.

## Search index

The visible site-wide search bar reads the committed static indexes at `assets/search-index.json` and `assets/search-index.js`. The script form is a lazy-loaded fallback for direct `file://` previews. Rebuild both whenever page headings or searchable content change:

```bash
python3 tools/build_search_index.py
python3 tools/build_search_index.py --check
```

The generator uses only the Python standard library. Search stays entirely client-side and does not send queries to a server.

Ranking is query-agnostic: exact page and heading matches come first, followed by complete scientific-token matches, navigation hierarchy, and body-only matches. Page candidates precede subsections within the same relevance tier, and at most four results from one page are retained so one document cannot monopolize the candidate list. There are no per-query ranking patches.

## Validation

```bash
python3 tools/build_search_index.py --check
node --check assets/js/main.js
node --check assets/js/home.js
node --check assets/js/search.js
git diff --check
```

## Main files

- `index.html`, `assets/css/home.css`, `assets/js/home.js` — homepage.
- `assets/css/styles.css`, `assets/js/main.js` — shared documentation presentation and interactions.
- `assets/css/search.css`, `assets/js/search.js`, `assets/search-index.json` — client-side site search.
- `tutorials/`, `setup/`, `tasks/`, `functions/` — documentation content.
- `tools/build_search_index.py` — deterministic search-index generator.

The website source is MIT-licensed. MAPLE software has separate terms; see the website Downloads page and the MAPLE software repository LICENSE.
