#!/usr/bin/env node
'use strict';

// Node-only regression harness. Production scripts expose no testing globals.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const { performance } = require('node:perf_hooks');
const root = path.resolve(__dirname, '..');
const args = process.argv.slice(2);
const fixtureMode = args.includes('--fixture');
const basePosition = args.indexOf('--baseline-ref');
const baselineRef = basePosition >= 0 ? args[basePosition + 1] : null;
if (basePosition >= 0 && (!baselineRef || baselineRef.startsWith('-'))) {
  throw new Error('--baseline-ref requires a Git revision');
}

function loadSearch(source) {
  const marker = "  if (document.readyState === 'loading') {";
  assert.ok(source.includes(marker), 'Search initialization marker changed; update the test adapter.');
  const context = vm.createContext({
    URL, console, performance,
    document: { currentScript: { src: 'https://example.test/MAPLE-Website/assets/js/search.js' }, readyState: 'loading', addEventListener() {} },
    window: { setTimeout },
  });
  vm.runInContext(source.replace(marker,
    '  window.testSearch = { rankDocuments: rankDocuments, prepareIndex: typeof prepareIndex === "function" ? prepareIndex : null };\n' + marker), context);
  return { api: context.window.testSearch, context };
}

function fixtureDocuments() {
  const words = ['optimization', 'optimizer', 'optimize', 'frequency', 'forces', 'gradient', 'transition', 'state',
    'RFO', 'L-BFGS', 'COSMO-RS', 'ddPCM', 'GB/ALPB', 'CN-', 'CH3Br', 'CO₂', 'H₂O', 'Ångström', 'ﬁeld',
    'B3LYP/6-31G', '0.15', 'ilowfreq=2', 'mace_polar', 'GPU', 'CPU', 'energy', 'charge', 'spin', 'singlet'];
  let seed = 0x4d41504c;
  function next() {
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    return (seed >>> 0) % words.length;
  }
  const documents = [];
  for (let page = 0; page < 60; page += 1) {
    const label = words[next()] + ' ' + words[next()];
    for (let section = 0; section < 8; section += 1) {
      documents.push({
        page: 'tasks/page-' + page + '.html', url: 'tasks/page-' + page + '.html#section-' + section,
        title: label + ' — MAPLE', heading: section ? words[next()] + ' ' + words[next()] : label,
        text: section === 0 ? '' : Array.from({ length: 65 }, () => words[next()]).join(' '),
        trail: ['Tasks', label], type: 'Task', level: section ? 2 : 1,
        section_order: section, page_entry: section === 0, page_role: page % 3 ? 'content' : 'landing',
      });
    }
  }
  return documents;
}

function queriesFor(documents) {
  const queries = new Set(['', ' ', '!', '/', 'opt', 'optimization', 'OPTIMIZATION', 'optimization forces',
    'CN-', 'CH3Br', 'GB/ALPB', 'COSMO-RS', 'CO₂', 'H₂O', 'ilowfreq=2', '#opt', 'Ｂ３ＬＹＰ',
    'B3LYP/6-31G', 'ﬁeld', 'field', 'Ångström', '<script>', '[.*+?]', 'no-such-document-zzzz']);
  const vocabulary = new Set();
  documents.forEach((document) => {
    const text = [document.title, document.heading, document.text].join(' ').normalize('NFKD').toLowerCase();
    (text.match(/[a-z0-9]+(?:[._/+:-][a-z0-9]+)*/g) || []).forEach((word) => vocabulary.add(word));
  });
  // Evenly sample the sorted vocabulary; not just common or hand-picked queries.
  const words = Array.from(vocabulary).sort();
  const stride = Math.max(1, Math.floor(words.length / 350));
  for (let i = 0; i < words.length; i += stride) {
    const word = words[i];
    queries.add(word);
    if (word.length >= 3) queries.add(word.slice(0, 3));
    if (word.length >= 5) queries.add(word.slice(0, -1));
    queries.add(word + ' ' + words[(i + 7) % words.length]);
  }
  for (let i = 0; i < Math.min(words.length, 24); i += 1) {
    for (let j = 0; j < Math.min(words.length, 24); j += 1) {
      if (i !== j) queries.add(words[i] + ' ' + words[j]);
    }
  }
  return Array.from(queries);
}

async function main() {
  const source = fs.readFileSync(path.join(root, 'assets/js/search.js'), 'utf8');
  const current = loadSearch(source);
  const documents = fixtureMode
    ? fixtureDocuments()
    : JSON.parse(fs.readFileSync(path.join(root, 'assets/search-index.json'), 'utf8')).documents;
  assert.ok(documents.length, 'The corpus must not be empty.');
  const original = JSON.stringify(documents);
  const prepareStart = performance.now();
  const prepared = await current.api.prepareIndex(documents);
  const prepareMs = performance.now() - prepareStart;
  assert.equal(JSON.stringify(documents), original, 'Preparation mutated the search index.');
  const queries = queriesFor(documents);
  const baseline = baselineRef ? loadSearch(execFileSync('git', ['show', baselineRef + ':assets/js/search.js'], { cwd: root, encoding: 'utf8' })) : null;
  const baselineIndex = baseline && baseline.api.prepareIndex ? await baseline.api.prepareIndex(documents) : documents;
  let currentMs = 0;
  let baselineMs = 0;
  for (const query of queries) {
    let started = performance.now();
    const ranked = current.api.rankDocuments(prepared, query);
    currentMs += performance.now() - started;
    assert.ok(ranked.length <= 8);
    assert.equal(new Set(ranked.map((item) => item.document.url)).size, ranked.length);
    const pages = new Map();
    ranked.forEach((item) => {
      const page = item.document.page || item.document.url.split('#')[0];
      pages.set(page, (pages.get(page) || 0) + 1);
    });
    assert.ok(Array.from(pages.values()).every((count) => count <= 4));
    if (baseline) {
      started = performance.now();
      const expected = baseline.api.rankDocuments(baselineIndex, query);
      baselineMs += performance.now() - started;
      assert.equal(JSON.stringify(ranked), JSON.stringify(expected), 'Ranking changed for ' + JSON.stringify(query));
    }
  }
  assert.equal(JSON.stringify(documents), original, 'Ranking mutated the search index.');
  // Query-time normalization must be independent of corpus size.
  vm.runInContext('var normalizationCalls = 0; var originalNormalize = String.prototype.normalize; String.prototype.normalize = function (form) { normalizationCalls += 1; return originalNormalize.call(this, form); };', current.context);
  current.api.rankDocuments(prepared, 'optimization forces');
  assert.ok(current.context.normalizationCalls <= 4, 'Document normalization returned to the query path.');
  console.log(JSON.stringify({
    corpus: fixtureMode ? 'deterministic synthetic fixture' : 'repository search index',
    documents: documents.length, queries: queries.length,
    baseline: baselineRef, identicalRankings: baseline ? queries.length : null,
    prepareMs: +prepareMs.toFixed(2), meanRankingMs: +(currentMs / queries.length).toFixed(3),
    baselineMeanRankingMs: baseline ? +(baselineMs / queries.length).toFixed(3) : null,
    queryNormalizations: current.context.normalizationCalls,
  }, null, 2));

}
main().catch((error) => { console.error(error); process.exitCode = 1; });
