# Shared UI regression checks

The website keeps its static HTML/CSS/JavaScript runtime. Tests require Node.js
and, for browser checks only, Python with Playwright. No test hooks, dependencies,
or additional globals are shipped to visitors.

## Search equivalence

```sh
node tools/test_search.js --baseline-ref 078752ae95f72237ae2297bd0b4c8e36ab6724d5
node tools/test_search.js --fixture --baseline-ref 078752ae95f72237ae2297bd0b4c8e36ab6724d5
```

The default corpus is the repository's committed search index. `--fixture` is a
separate, deterministic 480-record synthetic corpus, not a substitute for it.
The harness samples actual vocabulary, prefixes, multi-word combinations, Unicode
and scientific tokens. It compares complete serialized rankings, including scores
and order, against the selected Git revision. It also checks result/page limits,
index immutability and query-time normalization counts. Fetch the baseline commit
first when using a shallow clone.

Preparation and mean ranking timings are diagnostic, not portable pass/fail
thresholds. They exclude network and browser rendering; they are not INP scores
or measurements on mobile hardware. To intentionally change relevance, review
and update the baseline separately rather than silently accepting new rankings.

## Shared browser interactions

```sh
python3 -m venv .venv
.venv/bin/pip install playwright==1.57.0
.venv/bin/python -m playwright install chromium
.venv/bin/python tools/test_ui.py
```

An existing Chromium can be selected with `--chromium /path/to/chromium`.
The harness serves the unchanged production scripts/styles under a non-root URL,
with small deterministic HTML fixtures and controlled search-index responses.
Coverage includes pending-load cancellation, debouncing, composition events,
keyboard navigation, safe highlighting, fallback/retry, modal focus and inert
restoration, breakpoints, TOC layout invalidation, skip links and plain-text copy.
The viewport checks cover these fixtures, not every documentation page.

The PR workflow additionally checks the generated index on a complete checkout.
It has read-only permissions and does not publish, deploy, merge or rewrite commits.
Real Safari/Android keyboard behavior, full-page screenshots and resource loading
still require device/site-level testing; synthetic composition events do not
certify every native input method.
