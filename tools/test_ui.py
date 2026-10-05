#!/usr/bin/env python3
"""Exercise the real shared scripts/styles over HTTP, with deterministic test content.

Development dependency: playwright. No test globals or hooks are shipped to visitors.
Run: python tools/test_ui.py [--chromium /path/to/chromium]
"""
from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    dict(page='optimization.html', url='optimization.html#optimization', title='Optimization — MAPLE',
         heading='Optimization', text='Optimize geometry with RFO, L-BFGS and CO₂. <img src=x onerror=alert(1)>',
         trail=['Tasks', 'Optimization'], type='Task', level=1, section_order=0, page_entry=True, page_role='landing'),
    dict(page='frequency.html', url='frequency.html#frequency', title='Frequency — MAPLE',
         heading='Frequency', text='Vibrational frequency analysis.', trail=['Tasks', 'Frequency'],
         type='Task', level=1, section_order=0, page_entry=True, page_role='content'),
]
PAYLOAD = dict(version=2, source_pages=2, documents=DOCUMENTS)
DOC_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/preview/assets/css/styles.css">
<link rel="stylesheet" href="/preview/assets/css/search.css"></head><body>
<header class="top-nav"><div class="container"><div class="brand"><a href="#first">MAPLE</a></div>
<button class="mobile-toggle" aria-label="Toggle navigation">Menu</button><nav><ul>
<li><a href="#first">Documentation</a></li><li><a href="#second">Downloads</a></li></ul></nav></div></header>
<div class="page-layout"><aside class="sidebar" aria-label="Documentation"><nav class="sidebar-nav">
<div class="sidebar-brand"><span>MAPLE</span></div><div class="sidebar-tree"><ul><li class="open">
<div class="tree-section"><span class="chevron"></span>Tutorials</div><ul class="children">
<li><a class="active" href="#first">Optimization</a></li><li><a href="#second">Frequency</a></li></ul></li>
<li><div class="tree-section"><span class="chevron"></span>Hidden group</div><ul class="children">
<li><a href="#third">Hidden link</a></li></ul></li></ul></div></nav></aside>
<main class="content"><article style="position: relative"><h1>Optimization</h1>
<h2 id="first">First calculation</h2><p>Small documentation fixture; production scripts and styles are unmodified by the harness.</p>
<pre><code>#model = ani2x\n#device = cpu\n#opt\n\nO  0.000000  0.000000  0.117300</code></pre>
<button id="outside">Outside search</button><div id="spacer" style="height: 700px"></div>
<h2 id="second">Frequency</h2><div style="height: 700px"></div><h3 id="third">Output</h3>
<div style="height: 900px"></div></article></main>
<aside class="toc"><div class="toc-sticky"><h3>On this page</h3><ul></ul></div></aside></div>
<div id="already-inert" inert>Preserve existing inert state</div><div class="sidebar-overlay"></div><footer>MAPLE</footer>
<script src="/preview/assets/js/main.js"></script><script src="/preview/assets/js/search.js"></script></body></html>'''
HOME_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="/preview/assets/css/search.css"><style>
* {box-sizing:border-box} .header-inner {display:flex;flex-wrap:wrap;gap:16px}
.main-nav {display:none} .nav-open .main-nav {display:block} .reveal {min-height:40px}
</style></head><body><header class="site-header"><div class="header-inner">
<a href="#content">MAPLE</a><button class="mobile-toggle" aria-expanded="false">Menu</button>
<nav class="main-nav"><a href="#content">Documentation</a></nav></div></header>
<main id="content"><h1>MAPLE</h1><div class="reveal">Content</div><button id="outside">Outside</button></main>
<script src="/preview/assets/js/home.js"></script><script src="/preview/assets/js/search.js"></script></body></html>'''


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/preview/fixture/docs', '/preview/fixture/home'):
            text = HOME_HTML if self.path.endswith('/home') else DOC_HTML
            body = text.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.endswith('/favicon.ico'):
            self.send_response(204)
            self.end_headers()
        else:
            self.path = self.path.removeprefix('/preview')
            super().do_GET()

    def log_message(self, *args):
        pass


class SharedUI(unittest.TestCase):
    def setUp(self):
        self.context = self.browser.new_context(viewport=dict(width=1365, height=800), reduced_motion='reduce',
                                               permissions=['clipboard-read', 'clipboard-write'])
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.pending = []
        self.hold_index = False
        self.requests = []
        self.payload = json.loads(json.dumps(PAYLOAD))
        self.page.route('**/assets/search-index.json', self.index_route)
        self.page.goto(self.base_url + '/preview/fixture/docs')
        self.input = self.page.locator('#site-search-input')
        self.panel = self.page.locator('.site-search-results')

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def index_route(self, route):
        self.requests.append(route.request.url)
        if self.hold_index:
            self.pending.append(route)
        else:
            route.fulfill(json=self.payload)

    def release_index(self):
        self.page.wait_for_function('document.querySelector("#site-search-input") !== null')
        self.assertTrue(self.pending, 'Expected a held index request')
        for route in self.pending:
            route.fulfill(json=self.payload)
        self.pending.clear()

    def wait_result(self, text='Optimization'):
        self.page.wait_for_function('text => document.querySelector(".site-search-result strong")?.textContent === text', arg=text)

    def start_pending_search(self):
        self.hold_index = True
        self.input.fill('optimization')
        self.page.wait_for_function('document.querySelector("[role=status]").textContent === "Searching…"')

    def test_no_index_download_before_intent(self):
        self.page.wait_for_timeout(180)
        self.assertEqual(self.requests, [])
        self.input.focus()
        self.page.wait_for_timeout(180)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(self.panel.is_hidden())
        self.input.fill('optimization')
        self.wait_result()
        self.assertEqual(len(self.requests), 1)

    def test_escape_cancels_in_flight_result(self):
        self.start_pending_search()
        self.input.press('Escape')
        self.release_index()
        self.page.wait_for_timeout(180)
        self.assertTrue(self.panel.is_hidden())
        self.input.fill('frequency')
        self.wait_result('Frequency')
        self.assertEqual(len(self.requests), 1)

    def test_outside_click_cancels_in_flight_result(self):
        self.start_pending_search()
        self.page.locator('#outside').click()
        self.release_index()
        self.page.wait_for_timeout(180)
        self.assertTrue(self.panel.is_hidden())

    def test_blur_cancels_in_flight_result(self):
        self.start_pending_search()
        self.page.locator('#outside').focus()
        self.release_index()
        self.page.wait_for_timeout(180)
        self.assertTrue(self.panel.is_hidden())

    def test_new_input_invalidates_before_debounce(self):
        self.start_pending_search()
        self.input.fill('frequency')
        self.release_index()
        self.assertEqual(self.page.locator('.site-search-result').count(), 0)
        self.wait_result('Frequency')

    def test_clear_and_escape_cancel_pending_timer(self):
        self.input.fill('optimization')
        self.input.press('Escape')
        self.page.wait_for_timeout(180)
        self.assertTrue(self.panel.is_hidden())
        self.input.fill('optimization')
        self.input.fill('')
        self.page.wait_for_timeout(180)
        self.assertTrue(self.panel.is_hidden())

    def test_composition_does_not_search_or_steal_keys(self):
        self.input.fill('optimization')
        self.wait_result()
        for key in ['ArrowDown', 'ArrowUp', 'Enter', 'Escape']:
            cancelled = self.input.evaluate('''(element, key) => {
              const event = new KeyboardEvent('keydown', { key, isComposing: true, bubbles: true, cancelable: true });
              element.dispatchEvent(event); return event.defaultPrevented;
            }''', key)
            self.assertFalse(cancelled)
        self.input.dispatch_event('compositionstart')
        self.input.fill('frequency')
        self.page.wait_for_timeout(180)
        self.assertTrue(self.panel.is_hidden())
        self.input.dispatch_event('compositionend')
        self.wait_result('Frequency')

    def test_keyboard_navigation_and_safe_unicode_highlight(self):
        self.payload['documents'][0]['heading'] = 'Ｏｐｔｉｍｉｚａｔｉｏｎ CO₂ <img src=x>'
        self.input.fill('opt')
        self.wait_result(self.payload['documents'][0]['heading'])
        self.assertEqual(self.page.locator('.site-search-result img').count(), 0)
        self.assertEqual(self.page.locator('.site-search-result strong mark').first.text_content(), 'Ｏｐｔｉｍｉｚａｔｉｏｎ')
        self.input.press('ArrowDown')
        selected = self.input.get_attribute('aria-activedescendant')
        self.assertEqual(self.page.locator('#' + selected).get_attribute('aria-selected'), 'true')
        self.input.press('Escape')
        self.assertIsNone(self.input.get_attribute('aria-activedescendant'))
        self.assertTrue(self.panel.is_hidden())

    def test_json_failure_uses_one_script_fallback(self):
        counts = []
        self.page.route('**/assets/search-index.json', lambda route: route.fulfill(status=503, body='Unavailable'))
        def fallback(route):
            counts.append(1)
            route.fulfill(content_type='text/javascript', body='window.MAPLE_SEARCH_INDEX=' + json.dumps(self.payload) + ';')
        self.page.route('**/assets/search-index.js', fallback)
        self.input.fill('optimization')
        self.wait_result()
        self.input.fill('frequency')
        self.wait_result('Frequency')
        self.assertEqual(len(counts), 1)

    def test_failed_load_can_retry(self):
        self.page.route('**/assets/search-index.json', lambda route: route.fulfill(status=503, body='Unavailable'))
        self.page.route('**/assets/search-index.js', lambda route: route.abort())
        self.input.fill('optimization')
        self.page.wait_for_function('document.querySelector("[role=status]").textContent.includes("unavailable")')
        self.page.unroute('**/assets/search-index.json')
        self.page.unroute('**/assets/search-index.js')
        self.page.route('**/assets/search-index.json', self.index_route)
        self.input.fill('frequency')
        self.wait_result('Frequency')

    def test_drawer_focus_cycle_and_state_restoration(self):
        self.page.set_viewport_size(dict(width=390, height=800))
        fab = self.page.locator('.sidebar-fab')
        fab.click()
        self.assertEqual(self.page.locator('.sidebar').get_attribute('aria-modal'), 'true')
        self.assertTrue(self.page.evaluate('document.querySelector(".sidebar").contains(document.activeElement)'))
        self.assertTrue(self.page.locator('main').evaluate('el => el.inert'))
        self.page.locator('.sidebar-close').focus()
        self.page.keyboard.press('Shift+Tab')
        self.assertEqual(self.page.evaluate('document.activeElement.textContent.trim()'), 'Hidden group')
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.evaluate('document.activeElement.className'), 'sidebar-close')
        self.page.keyboard.press('Escape')
        self.assertEqual(self.page.evaluate('document.activeElement.className'), 'sidebar-fab')
        self.assertFalse(self.page.locator('main').evaluate('el => el.inert'))
        self.assertTrue(self.page.locator('#already-inert').evaluate('el => el.inert'))
        self.assertEqual(self.page.evaluate('document.documentElement.style.overflow'), '')
        self.assertIsNone(self.page.locator('.sidebar').get_attribute('aria-modal'))

    def test_drawer_breakpoint_restores_desktop_navigation(self):
        self.page.set_viewport_size(dict(width=390, height=800))
        self.page.locator('.sidebar-fab').click()
        self.page.set_viewport_size(dict(width=1365, height=800))
        self.page.wait_for_timeout(100)
        self.assertIsNone(self.page.locator('.sidebar').get_attribute('aria-modal'))
        self.assertFalse(self.page.locator('main').evaluate('el => el.inert'))
        self.assertFalse(self.page.locator('.sidebar').evaluate('el => el.inert'))
        self.assertNotEqual(self.page.evaluate('document.activeElement.className'), 'sidebar-close')
        self.page.set_viewport_size(dict(width=390, height=800))
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate('document.activeElement.className'), 'sidebar-fab')

    def test_toc_cache_invalidates_after_layout_change(self):
        self.page.wait_for_timeout(100)
        self.page.evaluate('''() => {
          const target = document.querySelector('#second');
          window.scrollTo(0, target.getBoundingClientRect().top + scrollY - document.querySelector('.top-nav').getBoundingClientRect().height - 14);
        }''')
        self.page.wait_for_function('document.querySelector(".toc a.active")?.getAttribute("href") === "#second"')
        self.page.locator('#spacer').evaluate('el => el.style.height = "1200px"')
        self.page.wait_for_function('document.querySelector(".toc a.active")?.getAttribute("href") === "#first"')
        self.page.evaluate('''() => {
          window.tocMutations = 0;
          new MutationObserver(records => window.tocMutations += records.length)
            .observe(document.querySelector('.toc ul'), {attributes: true, subtree: true, attributeFilter:['class']});
          window.scrollBy(0, 5);
        }''')
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate('window.tocMutations'), 0)

    def test_mobile_toc_and_skip_link(self):
        self.page.set_viewport_size(dict(width=390, height=800))
        details = self.page.locator('.mobile-toc')
        self.assertTrue(details.is_visible())
        details.locator('summary').click()
        details.locator('a[href="#second"]').click()
        self.assertFalse(details.evaluate('el => el.open'))
        self.assertTrue(self.page.url.endswith('#second'))
        self.page.locator('.skip-link').focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('document.activeElement.tagName'), 'MAIN')

    def test_copy_preserves_input_text(self):
        code = self.page.locator('pre code').text_content()
        self.assertTrue(self.page.locator('pre').evaluate('el => el.classList.contains("maple-code")'))
        self.page.locator('.copy-btn').focus()
        self.page.wait_for_function('getComputedStyle(document.querySelector(".copy-btn")).opacity === "1"')
        self.page.keyboard.press('Enter')
        self.page.wait_for_function('document.querySelector(".copy-btn").classList.contains("copied")')
        self.assertEqual(self.page.evaluate('navigator.clipboard.readText()'), code)

    def test_responsive_fixture_has_no_horizontal_overflow(self):
        for width in (1365, 800, 390, 320):
            self.page.set_viewport_size(dict(width=width, height=800))
            self.page.wait_for_timeout(80)
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)

    def test_home_menu_escape_and_breakpoint(self):
        self.page.goto(self.base_url + '/preview/fixture/home')
        self.page.set_viewport_size(dict(width=390, height=800))
        toggle = self.page.locator('.mobile-toggle')
        toggle.click()
        self.assertEqual(toggle.get_attribute('aria-expanded'), 'true')
        self.page.keyboard.press('Escape')
        self.assertEqual(toggle.get_attribute('aria-expanded'), 'false')
        self.assertEqual(self.page.evaluate('document.activeElement.className'), 'mobile-toggle')
        toggle.click()
        self.page.set_viewport_size(dict(width=1365, height=800))
        self.page.wait_for_timeout(100)
        self.assertEqual(toggle.get_attribute('aria-expanded'), 'false')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', help='Optional system Chromium executable')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium)
            SharedUI.browser = browser
            SharedUI.base_url = f'http://127.0.0.1:{server.server_port}'
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SharedUI))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
