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
import re
from urllib.parse import unquote, urlsplit
from threading import Thread
from http.server import ThreadingHTTPServer

from playwright.sync_api import sync_playwright
from test_ui import Handler, ROOT

PAGES = ['index.html', 'general.html', 'articles.html', 'tutorials/installation.html',
         'tutorials/input_output.html', 'tasks/opt/optimization.html',
         'tasks/opt/opt_rfo.html', 'tasks/scan/scan.html', 'setup/calculators.html']
WIDTHS = [320, 390, 800, 1248, 1249, 1280, 1350, 1366, 1440, 1920]
COLOR_TARGETS = {
    'index.html': ['.news-grid', '.feature-grid'],
    'general.html': ['.card-grid'],
    'tutorials/installation.html': ['.admonition.tip', '.admonition.note', '.admonition.warning'],
    'tutorials/input_output.html': ['.admonition.important', 'pre.maple-code'],
    'setup/calculators.html': ['.capability-badges'],
}
EXPECTED_COLORS = {
    'brand': 'rgb(211, 32, 33)',
    'text': 'rgb(29, 31, 37)',
    'inline': 'rgb(243, 242, 239)',
    'inline-border': 'rgb(232, 230, 225)',
    'meta': 'rgb(108, 112, 122)',
    'note': 'rgb(61, 90, 128)',
    'note-soft': 'rgba(61, 90, 128, 0.08)',
    'tip': 'rgb(46, 125, 79)',
    'tip-soft': 'rgba(46, 125, 79, 0.08)',
    'warning': 'rgb(161, 92, 7)',
    'warning-soft': 'rgba(161, 92, 7, 0.08)',
    'important': 'rgb(211, 32, 33)',
    'important-soft': 'rgba(211, 32, 33, 0.08)',
    'danger': 'rgb(180, 35, 24)',
    'danger-soft': 'rgba(180, 35, 24, 0.08)',
    'line': 'rgb(229, 230, 234)',
    'white': 'rgb(255, 255, 255)',
    'transparent': 'rgba(0, 0, 0, 0)',
    'hover-border': 'rgba(211, 32, 33, 0.14)',
}


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
  const inlineCode = [...document.querySelectorAll('article code')].find(el => !el.closest('pre'));
  const paint = el => el ? {
    color: getComputedStyle(el).color,
    background: getComputedStyle(el).backgroundColor,
    backgroundImage: getComputedStyle(el).backgroundImage,
    border: getComputedStyle(el).borderTopColor,
    borderWidth: getComputedStyle(el).borderTopWidth,
    borderLeft: getComputedStyle(el).borderLeftColor,
    borderLeftWidth: getComputedStyle(el).borderLeftWidth,
  } : null;
  const admonitions = Object.fromEntries(['note', 'tip', 'warning', 'important', 'danger'].map(kind => {
    const box = document.querySelector('.admonition.' + kind);
    return [kind, box ? {border: getComputedStyle(box).borderLeftColor, title: paint(box.querySelector('.admonition-title'))} : null];
  }));
  const svgStyles = selector => [...document.querySelectorAll(selector)].map(el => ({
    fill: getComputedStyle(el).fill,
    stroke: getComputedStyle(el).stroke,
    stopColor: getComputedStyle(el).stopColor,
    stopOpacity: getComputedStyle(el).stopOpacity,
  }));
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
    colors: {
      inlineCode: paint(inlineCode),
      mapleDirective: paint(document.querySelector('pre.maple-code .directive')),
      mapleValue: paint(document.querySelector('pre.maple-code .value')),
      mapleBlock: paint(document.querySelector('pre.maple-code')),
      admonitions,
      cardTag: paint(document.querySelector('.card .card-tag')),
      newsDate: paint(document.querySelector('.news-card .date')),
      chipIcon: paint(document.querySelector('.chip .chip-ico')),
      pillIcon: paint(document.querySelector('.feat-pill .pill-ico')),
      featureIcon: paint(document.querySelector('.feature-icon')),
      heroStroke: svgStyles('.science-bg [stroke="#e23a2e"], .science-bg [stroke="#d32021"]'),
      heroFill: svgStyles('.science-bg [fill="#e23a2e"], .science-bg [fill="#d32021"]'),
      heroStop: svgStyles('.science-bg [stop-color="#e23a2e"], .science-bg [stop-color="#d32021"]'),
      badgeYes: paint(document.querySelector('.badge-yes')),
      badgeNo: paint(document.querySelector('.badge-no')),
      badgePartial: paint(document.querySelector('.badge-partial')),
    },
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
    failed = [label for label, ok in checks.items() if not ok]
    colors = m['colors']
    if colors['inlineCode'] and not (
        colors['inlineCode']['color'] == EXPECTED_COLORS['text'] and
        colors['inlineCode']['background'] == EXPECTED_COLORS['inline'] and
        colors['inlineCode']['border'] == EXPECTED_COLORS['inline-border'] and
        colors['inlineCode']['borderWidth'] == '1px'
    ):
        failed.append('inline code is not neutral')
    if colors['mapleDirective'] and colors['mapleDirective']['color'] != EXPECTED_COLORS['brand']:
        failed.append('MAPLE directive lost brand signal')
    if colors['mapleValue'] and not (
        colors['mapleValue']['color'] == EXPECTED_COLORS['text'] and
        colors['mapleValue']['background'] == EXPECTED_COLORS['transparent']
    ):
        failed.append('MAPLE value still competes with directive')
    if colors['mapleBlock'] and not (
        colors['mapleBlock']['borderLeft'] == EXPECTED_COLORS['brand'] and
        colors['mapleBlock']['borderLeftWidth'] == '3px'
    ):
        failed.append('MAPLE block lacks restrained directive rail')
    for kind, expected in [('note', 'note'), ('tip', 'tip'), ('warning', 'warning'),
                           ('important', 'important'), ('danger', 'danger')]:
        state = colors['admonitions'][kind]
        if state and not (state['border'] == EXPECTED_COLORS[expected] and
                          state['title']['color'] == EXPECTED_COLORS[expected] and
                          state['title']['background'] == EXPECTED_COLORS[expected + '-soft']):
            failed.append(kind + ' admonition lacks semantic color')
    for name in ('cardTag', 'newsDate'):
        if colors[name] and colors[name]['color'] != EXPECTED_COLORS['meta']:
            failed.append(name + ' metadata is not neutral')
    for name in ('chipIcon', 'pillIcon', 'featureIcon'):
        if colors[name] and not (
            colors[name]['background'] == EXPECTED_COLORS['white'] and
            colors[name]['backgroundImage'] == 'none' and
            colors[name]['border'] == EXPECTED_COLORS['line']
        ):
            failed.append(name + ' uses a tinted container')
    if m.get('page') == 'index.html':
        for name, prop, count in (('heroStroke', 'stroke', 1), ('heroFill', 'fill', 2),
                                  ('heroStop', 'stopColor', 3)):
            if len(colors[name]) != count or any(state[prop] != EXPECTED_COLORS['brand']
                                                 for state in colors[name]):
                failed.append(name + ' does not fully normalize the hero artwork')
        if [state['stopOpacity'] for state in colors['heroStop']] != ['0.08', '0.05', '0']:
            failed.append('hero glow bypasses the three permitted tint strengths')
    badge_expectations = {
        'badgeYes': (EXPECTED_COLORS['tip'], EXPECTED_COLORS['tip-soft']),
        'badgeNo': (EXPECTED_COLORS['meta'], EXPECTED_COLORS['inline']),
        'badgePartial': (EXPECTED_COLORS['warning'], EXPECTED_COLORS['warning-soft']),
    }
    for name, (foreground, background) in badge_expectations.items():
        state = colors[name]
        if state and not (state['color'] == foreground and state['background'] == background and
                          state['border'] == EXPECTED_COLORS['line']):
            failed.append(name + ' lacks restrained capability semantics')
    return failed


def palette_failures(read_text):
    files = {name: read_text(name) for name in
             ('assets/css/home.css', 'assets/css/styles.css', 'assets/css/search.css')}
    failed = []
    expected_tokens = {
        '--brand-red': '#d32021',
        '--brand-red-tint-1': 'rgba(211,32,33,.05)',
        '--brand-red-tint-2': 'rgba(211,32,33,.08)',
        '--brand-red-tint-3': 'rgba(211,32,33,.14)',
        '--semantic-meta': '#6c707a',
    }
    for token, expected in expected_tokens.items():
        values = []
        for name in ('assets/css/home.css', 'assets/css/styles.css'):
            match = re.search(rf'{re.escape(token)}\s*:\s*([^;]+)', files[name])
            values.append(match.group(1).strip() if match else None)
        if values != [expected, expected]:
            failed.append(f'{token} differs across entry stylesheets: {values}')
    styles_tokens = {
        '--color-code-inline': '#1d1f25',
        '--color-code-inline-bg': '#f3f2ef',
        '--color-code-inline-border': '#e8e6e1',
        '--color-note': '#3d5a80',
        '--color-note-soft': 'rgba(61,90,128,.08)',
        '--color-tip': '#2e7d4f',
        '--color-tip-soft': 'rgba(46,125,79,.08)',
        '--color-warning': '#a15c07',
        '--color-warning-soft': 'rgba(161,92,7,.08)',
        '--color-danger': '#b42318',
        '--color-danger-soft': 'rgba(180,35,24,.08)',
        '--color-important': 'var(--brand-red)',
    }
    for token, expected in styles_tokens.items():
        match = re.search(rf'{re.escape(token)}\s*:\s*([^;]+)', files['assets/css/styles.css'])
        actual = match.group(1).strip() if match else None
        if actual != expected:
            failed.append(f'{token} is {actual}, expected {expected}')
    banned = ('#e23a2e', '#f15a4f', '#fde8e6', '#fff7f6', '#7a1712',
              '#00c852', '#ff9100', '#00b0ff', '#00bfa5', '#1e4fd6',
              'rgba(226,58,46', 'rgba(226, 58, 46', 'rgba(37,99,235',
              'rgba(41,98,255', 'rgba(42, 90, 223')
    for name, text in files.items():
        lowered = text.lower()
        for value in banned:
            matching_lines = [line for line in lowered.splitlines() if value in line]
            if value == '#e23a2e' and name == 'assets/css/home.css':
                matching_lines = [line for line in matching_lines
                                  if not ('[stop-color="#e23a2e"]' in line or
                                          '[stroke="#e23a2e"]' in line or
                                          '[fill="#e23a2e"]' in line)]
            if matching_lines:
                failed.append(f'{name} retains {value}')
        for line_no, line in enumerate(text.splitlines(), 1):
            if ('rgba(211,32,33' in line.replace(' ', '') and
                    '--brand-red-tint-' not in line):
                failed.append(f'{name}:{line_no} bypasses brand tint tokens')
    radial_count = sum(text.count('radial-gradient') for text in files.values())
    index_html = read_text('index.html')
    hero_match = re.search(r'<div class="science-bg".*?</div>', index_html, re.S)
    hero_html = hero_match.group(0) if hero_match else ''
    hero_radial_count = hero_html.count('<radialGradient')
    if radial_count or hero_radial_count != 1:
        failed.append(f'expected only the SVG hero radial glow; found {radial_count} CSS and {hero_radial_count} SVG')
    for attribute, count in (('stop-color', 3), ('stroke', 1), ('fill', 2)):
        total = sum(hero_html.count(f'{attribute}="{color}"')
                    for color in ('#e23a2e', '#d32021'))
        if total != count:
            failed.append(f'hero accent contract changed for {attribute}')
    return failed


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
    def read_text(path):
        return (subprocess.check_output(['git', 'show', baseline + ':' + path], cwd=ROOT, text=True)
                if baseline else (ROOT / path).read_text())
    palette = palette_failures(read_text)
    print('Palette: ' + (', '.join(palette) if palette else 'PASS'), flush=True)
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
                source.feed(read_text(name))
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
                        if width == 1440:
                            for index, selector in enumerate(COLOR_TARGETS.get(name, []), 1):
                                target = page.locator(selector).first
                                if target.count():
                                    target.scroll_into_view_if_needed()
                                    screenshot(page, args.output / f'{name.replace("/", "-")}-color-{index}.png')
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
                    if name == 'index.html' and width == 1440:
                        for selector in ('.chip', '.news-card', '.feature-card:not(.primary)'):
                            target = page.locator(selector).first
                            target.hover()
                            page.wait_for_timeout(300)
                            border = target.evaluate('(el) => getComputedStyle(el).borderTopColor')
                            if border != EXPECTED_COLORS['hover-border']:
                                m['failures'].append(selector + ' hover border is too strong')
                        search = page.locator('#site-search-input')
                        search.fill('optimization')
                        meta = page.locator('.site-search-result-meta').first
                        meta.wait_for(state='visible')
                        if meta.evaluate('(el) => getComputedStyle(el).color') != EXPECTED_COLORS['meta']:
                            m['failures'].append('search metadata is not neutral')
                        if args.output:
                            screenshot(page, args.output / 'index.html-1440-search.png')
                        page.keyboard.press('Escape')
                    if name == 'general.html' and width == 1440:
                        target = page.locator('.card').first
                        target.hover()
                        page.wait_for_timeout(300)
                        border = target.evaluate('(el) => getComputedStyle(el).borderTopColor')
                        if border != EXPECTED_COLORS['hover-border']:
                            m['failures'].append('.card hover border is too strong')
                    if name == 'tutorials/installation.html' and width == 1440:
                        danger = page.evaluate("""() => {
                          const box = document.createElement('div');
                          box.className = 'admonition danger';
                          box.innerHTML = '<div class="admonition-title">Danger</div>';
                          document.body.appendChild(box);
                          const title = box.querySelector('.admonition-title');
                          const result = {
                            border: getComputedStyle(box).borderLeftColor,
                            color: getComputedStyle(title).color,
                            background: getComputedStyle(title).backgroundColor,
                          };
                          box.remove();
                          return result;
                        }""")
                        if danger != {
                            'border': EXPECTED_COLORS['danger'],
                            'color': EXPECTED_COLORS['danger'],
                            'background': EXPECTED_COLORS['danger-soft'],
                        }:
                            m['failures'].append('danger admonition lacks rendered semantic color')
                    print(f'{name} {width}: {", ".join(m["failures"]) or "PASS"}', flush=True)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    if args.output:
        (args.output / 'metrics.json').write_text(json.dumps(results, indent=2) + '\n')
    count = sum(bool(m['failures']) for m in results) + bool(palette)
    print(f'{len(results)} page/viewport checks; {count} failing gates')
    return 0 if args.record_only or not count else 1


if __name__ == '__main__':
    raise SystemExit(main())
