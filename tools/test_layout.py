#!/usr/bin/env python3
"""Check real pages, not fixtures; optionally retain metrics and screenshots.

Uses the same development-only Playwright dependency as test_ui.py.
--font-cache fetches the declared Google font bytes with curl for environments
where Chromium cannot reach the font host. Fetch failures remain fatal.
"""
from __future__ import annotations

import argparse
from functools import partial
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit
from threading import Thread
from http.server import ThreadingHTTPServer

from playwright.sync_api import sync_playwright
from test_ui import Handler, ROOT

PAGES = ['index.html', 'general.html', 'articles.html', 'tutorials/installation.html',
         'tutorials/input_output.html', 'tasks/opt/optimization.html',
         'tasks/opt/opt_rfo.html', 'tasks/scan/scan.html']
WIDTHS = [320, 390, 800, 1248, 1249, 1280, 1350, 1366, 1440, 1920]


class CodeText(HTMLParser):
    """Original text of preformatted examples before runtime highlighting."""
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.inside = False

    def handle_starttag(self, tag, attrs):
        if tag == 'pre':
            self.inside = True
            self.blocks.append('')

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.blocks[-1] += data

MEASURE = """() => {
  const rect = el => el.getBoundingClientRect();
  const header = document.querySelector('.site-header, .top-nav');
  const brand = header.querySelector('.brand');
  const nav = header.querySelector('nav');
  const visible = el => el && el.getClientRects().length && rect(el).width > 0;
  const brandRight = Math.max(...[brand, ...brand.children].map(el => rect(el).right));
  const links = [...nav.querySelectorAll('a')].filter(visible);
  const docs = !!document.querySelector('.page-layout .sidebar');
  const docLink = [...nav.querySelectorAll('a')].find(el => el.textContent.trim() === 'Documentation');
  const heading = document.querySelector('.page-body article > h2:first-child');
  const p = document.querySelector('.page-body article > p');
  const lbfgs = document.querySelector('article td a[href="opt_lbfgs.html"]');
  const chip = document.querySelector('.ml-family-group .chip');
  const controls = [brand, nav, header.querySelector('.site-search'), header.querySelector('.nav-tools'), header.querySelector('.mobile-toggle')].filter(visible);
  const headerCollisions = controls.flatMap((a, i) => controls.slice(i + 1).filter(b => {
    const x = rect(a), y = rect(b);
    return Math.min(x.right, y.right) - Math.max(x.left, y.left) > 1 &&
      Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > 1;
  }).map(b => a.className + ' / ' + b.className));
  return {
    width: innerWidth, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    headerHeight: rect(header).height,
    headerCollisions,
    navOverlap: links.some(el => rect(el).top < rect(brand).bottom && rect(el).bottom > rect(brand).top && rect(el).left < brandRight),
    navOutside: links.some(el => rect(el).right > innerWidth),
    docs, docsActive: !docs || (docLink.classList.contains('active') && docLink.getAttribute('aria-current') === 'location'),
    breadcrumbInside: !!document.querySelector('.content > article > .breadcrumb'),
    narrowCodeBlocks: [...document.querySelectorAll('article .code-wrapper')].filter(el => rect(el).width < el.parentElement.clientWidth - parseFloat(getComputedStyle(el.parentElement).paddingLeft) - parseFloat(getComputedStyle(el.parentElement).paddingRight) - 2).length,
    headingMargin: heading ? parseFloat(getComputedStyle(heading).marginTop) : null,
    proseWidth: p ? rect(p).width : null,
    methodLines: lbfgs ? lbfgs.getClientRects().length : null,
    chipFillsRow: chip ? rect(chip).width / rect(chip.parentElement).width : null,
    sidebarVisible: docs && rect(document.querySelector('.sidebar')).left >= 0,
    fontFaces: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ':' + f.weight)
  };
}"""


def failures(m):
    checks = {
        'horizontal page overflow': m['overflow'] <= 1,
        'brand/navigation overlap': not m['navOverlap'],
        'header controls overlap': not m['headerCollisions'],
        'navigation outside viewport': not m['navOutside'],
        'documentation section not active': m['docsActive'],
        'desktop sidebar missing': not m['docs'] or m['width'] <= 1072 or m['sidebarVisible'],
        'closed mobile sidebar covers content': not m['docs'] or m['width'] > 1072 or not m['sidebarVisible'],
        'breadcrumb inside reading card': not m['breadcrumbInside'],
        'code blocks not full width': m['narrowCodeBlocks'] == 0,
        'mobile header too tall': m['width'] > 390 or m['headerHeight'] <= 112,
        'first heading has extra top margin': m['headingMargin'] is None or m['headingMargin'] == 0,
        'prose exceeds reading measure': m['proseWidth'] is None or m['proseWidth'] <= 720,
        'method name wraps': m['methodLines'] is None or m['methodLines'] == 1,
        'single mobile model chip wastes row': m['width'] > 390 or m['chipFillsRow'] is None or m['chipFillsRow'] >= .98,
    }
    return [label for label, ok in checks.items() if not ok]


def screenshot(page, path):
    # Scrolling may have just triggered native lazy-loading; do not capture
    # empty icon placeholders and mistake them for the production appearance.
    page.evaluate("""async () => {
      await Promise.all([...document.images].filter(img => {
        const r = img.getBoundingClientRect();
        return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
      }).map(img => img.decode()));
      await document.fonts.ready;
    }""")
    page.screenshot(path=str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--font-cache', type=Path)
    parser.add_argument('--record-only', action='store_true', help='Record failing baseline without a nonzero exit')
    parser.add_argument('--all-pages', action='store_true', help='Check every indexed content page')
    parser.add_argument('--baseline-ref', help='Serve HTML/CSS/JS from a Git commit without changing the worktree')
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    if args.font_cache:
        args.font_cache.mkdir(parents=True, exist_ok=True)
    baseline = subprocess.check_output(['git', 'rev-parse', '--verify', args.baseline_ref + '^{commit}'], cwd=ROOT, text=True).strip() if args.baseline_ref else None
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium)
            context = browser.new_context(reduced_motion='reduce', permissions=['clipboard-read', 'clipboard-write'])
            if baseline:
                assets = {}
                def baseline_route(route):
                    path = unquote(urlsplit(route.request.url).path).removeprefix('/preview/')
                    mime = {'.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript', '.json': 'application/json'}.get(Path(path).suffix)
                    if mime is None:
                        route.continue_()
                        return
                    if path not in assets:
                        assets[path] = subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT)
                    route.fulfill(body=assets[path], content_type=mime + '; charset=utf-8')
                context.route('**/preview/**', baseline_route)
            if args.font_cache:
                def font_route(route):
                    path = args.font_cache / (hashlib.sha256(route.request.url.encode()).hexdigest() + '.woff2')
                    if not path.exists():
                        body = subprocess.check_output(['curl', '--fail', '--silent', '--show-error',
                                                        '--max-time', '30', route.request.url])
                        path.write_bytes(body)
                    route.fulfill(body=path.read_bytes(), content_type='font/woff2',
                                  headers={'Access-Control-Allow-Origin': '*'})
                context.route('https://fonts.gstatic.com/**', font_route)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            pages = sorted({doc['page'] for doc in json.loads((ROOT / 'assets/search-index.json').read_text())['documents']}) if args.all_pages else PAGES
            for name in pages:
                source = CodeText()
                source.feed(subprocess.check_output(['git', 'show', baseline + ':' + name], cwd=ROOT, text=True) if baseline else (ROOT / name).read_text())
                for width in WIDTHS:
                    page.set_viewport_size(dict(width=width, height=900 if width > 800 else 844))
                    page.goto(f'http://127.0.0.1:{server.server_port}/preview/{name}')
                    page.evaluate('document.fonts.ready')
                    page.wait_for_timeout(100)
                    m = page.evaluate(MEASURE)
                    m['page'] = name
                    m['failures'] = failures(m)
                    if page.locator('pre').all_text_contents() != source.blocks:
                        m['failures'].append('preformatted example text changed')
                    if errors:
                        m['failures'].extend(errors)
                        errors.clear()
                    # Font failures must never masquerade as a visual pass.
                    if not any('IBM Plex Sans' in font for font in m['fontFaces']):
                        m['failures'].append('body font not loaded')
                    if not any('Source Serif 4:900' in font for font in m['fontFaces']):
                        m['failures'].append('display font not loaded')
                    results.append(m)
                    if args.output and name in PAGES and width in (390, 1280, 1440):
                        screenshot(page, args.output / f'{name.replace("/", "-")}-{width}.png')
                        target = page.locator('.ml-family-group' if name == 'index.html' else 'article .code-wrapper').first
                        if target.count():
                            target.scroll_into_view_if_needed()
                            screenshot(page, args.output / f'{name.replace("/", "-")}-{width}-detail.png')
                    if width == 390:
                        toggle = page.locator('.mobile-toggle')
                        toggle.click()
                        if toggle.get_attribute('aria-expanded') != 'true':
                            m['failures'].append('mobile navigation did not open')
                        page.keyboard.press('Escape')
                        if toggle.get_attribute('aria-expanded') != 'false':
                            m['failures'].append('mobile navigation did not close')
                        if m['docs']:
                            page.locator('.sidebar-fab').click()
                            if page.locator('.sidebar').get_attribute('aria-modal') != 'true':
                                m['failures'].append('sidebar drawer did not open')
                            page.keyboard.press('Escape')
                            if page.locator('.sidebar').get_attribute('aria-modal') == 'true':
                                m['failures'].append('sidebar drawer did not close')
                    print(f'{name} {width}: {", ".join(m["failures"]) or "PASS"}', flush=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    if args.output:
        (args.output / 'metrics.json').write_text(json.dumps(results, indent=2) + '\n')
    count = sum(bool(m['failures']) for m in results)
    print(f'{len(results)} page/viewport checks; {count} failing')
    return 0 if args.record_only or not count else 1


if __name__ == '__main__':
    raise SystemExit(main())
