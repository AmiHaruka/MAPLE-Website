(function () {
  'use strict';

  var script = document.currentScript;
  if (!script) return;
  var siteRoot = new URL('../../', script.src);
  var indexUrl = new URL('assets/search-index.json', siteRoot);
  var scriptIndexUrl = new URL('assets/search-index.js', siteRoot);
  var indexPromise = null;

  function documentsFromPayload(payload) {
    if (!payload || payload.version !== 2 || !Array.isArray(payload.documents)) {
      throw new Error('Unsupported search index schema');
    }
    return payload.documents;
  }

  function loadScriptIndex() {
    return new Promise(function (resolve, reject) {
      var indexScript = document.createElement('script');
      indexScript.src = scriptIndexUrl.href;
      indexScript.async = true;
      indexScript.onload = function () {
        indexScript.remove();
        try {
          resolve(documentsFromPayload(window.MAPLE_SEARCH_INDEX));
        } catch (error) {
          reject(error);
        }
      };
      indexScript.onerror = function () {
        indexScript.remove();
        reject(new Error('Script search index request failed'));
      };
      document.head.appendChild(indexScript);
    });
  }

  function loadIndex() {
    // One promise owns loading AND preparation, including file:// and retries.
    if (!indexPromise) {
      var primary;
      if (window.MAPLE_SEARCH_INDEX) {
        primary = Promise.resolve().then(function () {
          return documentsFromPayload(window.MAPLE_SEARCH_INDEX);
        });
      } else if (window.location.protocol === 'file:') {
        primary = loadScriptIndex();
      } else {
        primary = fetch(indexUrl).then(function (response) {
          if (!response.ok) throw new Error('Search index request failed');
          return response.json();
        }).then(documentsFromPayload).catch(loadScriptIndex);
      }
      indexPromise = primary.then(prepareIndex).catch(function (error) {
        indexPromise = null;
        throw error;
      });
    }
    return indexPromise;
  }

  function normalize(value) {
    return String(value || '').normalize('NFKD').toLowerCase();
  }

  var MATCH_TIER = Object.freeze({
    NONE: 0,
    CROSS_FIELD: 1,
    BODY: 2,
    TRAIL: 3,
    STEM: 4,
    TITLE: 5,
    HEADING: 6,
    PHRASE: 7,
    EXACT: 8,
  });
  var RESULT_LIMIT = 8;
  var PER_PAGE_LIMIT = 4;
  var MIN_PREFIX_LENGTH = 3;
  var MIN_STEM_LENGTH = 4;

  function queryTerms(query) {
    return normalize(query).match(/[a-z0-9]+(?:[._/+:-][a-z0-9]+)*/g) || [];
  }

  function stemToken(token) {
    var suffixes = ['ation', 'ment', 'ing', 'ent', 'ers', 'er', 'ed', 'es', 's'];
    for (var i = 0; i < suffixes.length; i += 1) {
      var suffix = suffixes[i];
      if (token.endsWith(suffix) && token.length - suffix.length >= 4) {
        token = token.slice(0, -suffix.length);
        break;
      }
    }
    if (token.endsWith('e') && token.length > 5) token = token.slice(0, -1);
    return token;
  }

  function fieldTokens(value) {
    var compounds = queryTerms(value);
    var tokens = new Set();
    compounds.forEach(function (compound) {
      tokens.add(compound);
      compound.split(/[._/+:-]+/).forEach(function (part) {
        if (part) tokens.add(part);
      });
    });
    return Array.from(tokens);
  }

  function prepareField(value) {
    var text = normalize(value);
    var tokens = fieldTokens(text);
    return {
      text: text,
      tokens: tokens,
      exact: new Set(tokens),
      stems: new Set(tokens.map(stemToken)),
    };
  }

  function prepareIndex(documents) {
    var pageEntries = new Map();
    var fields = new Map();
    var prepared = [];
    var next = 0;

    function cachedField(value) {
      var text = String(value || '');
      if (!fields.has(text)) fields.set(text, prepareField(text));
      return fields.get(text);
    }

    function prepareDocument(document) {
      var page = document.page || document.url.split('#')[0];
      if (document.page_entry && !pageEntries.has(page)) pageEntries.set(page, document);
      var title = cachedField(document.title);
      var heading = cachedField(document.heading);
      var text = cachedField(document.text);
      var trail = cachedField((document.trail || []).join(' '));
      var pageLabel = cachedField((document.trail || []).slice(-1)[0] || document.title);
      var tokens = new Set();
      var stems = new Set();
      [title, heading, text, trail, pageLabel].forEach(function (field) {
        field.tokens.forEach(function (token) { tokens.add(token); });
        field.stems.forEach(function (stem) { stems.add(stem); });
      });
      return {
        document: document, title: title, heading: heading, text: text,
        trail: trail, pageLabel: pageLabel,
        all: { tokens: Array.from(tokens), exact: tokens, stems: stems },
      };
    }

    // Cold preparation yields too: do not move a typing stall onto first focus.
    return new Promise(function (resolve, reject) {
      function prepareBatch() {
        var started = performance.now();
        try {
          while (next < documents.length) {
            prepared.push(prepareDocument(documents[next++]));
            if (performance.now() - started >= 8) break;
          }
          if (next < documents.length) window.setTimeout(prepareBatch, 0);
          else resolve({ documents: prepared, pageEntries: pageEntries });
        } catch (error) {
          reject(error);
        }
      }
      prepareBatch();
    });
  }

  function prepareQuery(value) {
    var text = normalize(value).trim();
    var terms = queryTerms(text);
    var escapePattern = function (value) { return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
    var boundaryPattern = function (term) {
      return new RegExp('(^|[^a-z0-9])' + escapePattern(term) + '(?=$|[^a-z0-9])');
    };
    return {
      text: text, terms: terms, stems: terms.map(stemToken), quality: new Map(),
      phrasePattern: boundaryPattern(text),
      termPatterns: terms.map(function (term) {
        return {
          exact: boundaryPattern(term),
          prefix: term.length >= MIN_PREFIX_LENGTH
            ? new RegExp('(^|[^a-z0-9])' + escapePattern(term) + '[a-z0-9]*') : null,
        };
      }),
    };
  }

  function coversTerms(field, query) {
    return query.terms.every(function (term, index) {
      return field.exact.has(term) ||
        (term.length >= MIN_STEM_LENGTH && field.stems.has(query.stems[index])) ||
        (term.length >= MIN_PREFIX_LENGTH && field.tokens.some(function (candidate) {
          return candidate.startsWith(term);
        }));
    });
  }

  function matchQuality(field, query) {
    if (query.quality.has(field)) return query.quality.get(field);
    var quality = MATCH_TIER.NONE;
    if (coversTerms(field, query)) {
      if (field.text === query.text) quality = MATCH_TIER.EXACT;
      else if ((query.terms.length > 1 && field.text.includes(query.text)) ||
          query.terms.every(function (term) { return field.exact.has(term); })) quality = MATCH_TIER.PHRASE;
      else quality = MATCH_TIER.STEM;
    }
    query.quality.set(field, quality);
    return quality;
  }

  function firstQueryPosition(text, query) {
    var match = query.phrasePattern.exec(text);
    if (match) return match.index + match[1].length;
    var position = Number.POSITIVE_INFINITY;
    query.termPatterns.forEach(function (patterns) {
      var hit = patterns.exact.exec(text) || (patterns.prefix && patterns.prefix.exec(text));
      if (hit) position = Math.min(position, hit.index + hit[1].length);
    });
    return position;
  }

  function analyzeDocument(prepared, query) {
    if (!coversTerms(prepared.all, query)) return null;

    var pageLabelQuality = matchQuality(prepared.pageLabel, query);
    var titleQuality = matchQuality(prepared.title, query);
    var trailQuality = matchQuality(prepared.trail, query);
    var headingQuality = matchQuality(prepared.heading, query);
    var textQuality = matchQuality(prepared.text, query);
    var pageTier = Math.max(
      pageLabelQuality,
      titleQuality > MATCH_TIER.NONE ? Math.min(titleQuality, MATCH_TIER.TITLE) : MATCH_TIER.NONE,
      trailQuality > MATCH_TIER.NONE ? Math.min(trailQuality, MATCH_TIER.TRAIL) : MATCH_TIER.NONE
    );
    var sectionTier = Math.max(
      headingQuality > MATCH_TIER.NONE ? Math.max(headingQuality, MATCH_TIER.HEADING) : MATCH_TIER.NONE,
      textQuality > MATCH_TIER.NONE ? Math.min(textQuality, MATCH_TIER.BODY) : MATCH_TIER.NONE,
      MATCH_TIER.CROSS_FIELD
    );
    return {
      document: prepared.document,
      pageTier: pageTier,
      sectionTier: sectionTier,
      tier: Math.max(pageTier, sectionTier),
      position: firstQueryPosition(prepared.text.text, query),
    };
  }

  function compareRanked(a, b) {
    return b.tier - a.tier ||
      b.pageTier - a.pageTier ||
      Number(Boolean(b.isPageCandidate)) - Number(Boolean(a.isPageCandidate)) ||
      Number(Boolean(b.roleMatch)) - Number(Boolean(a.roleMatch)) ||
      b.sectionTier - a.sectionTier ||
      Number(b.pageEvidence || 0) - Number(a.pageEvidence || 0) ||
      a.position - b.position ||
      Number(a.document.section_order || 0) - Number(b.document.section_order || 0) ||
      a.document.title.localeCompare(b.document.title);
  }

  function rankDocuments(index, rawQuery) {
    var query = prepareQuery(rawQuery);
    if (!query.terms.length) return [];
    var matches = index.documents.map(function (prepared) {
      return analyzeDocument(prepared, query);
    }).filter(Boolean);
    if (!matches.length) return [];

    var itemsByPage = new Map();
    var pageEntries = index.pageEntries;
    matches.forEach(function (item) {
      var page = item.document.page || item.document.url.split('#')[0];
      if (!itemsByPage.has(page)) itemsByPage.set(page, []);
      itemsByPage.get(page).push(item);
    });

    var candidates = [];
    itemsByPage.forEach(function (items) {
      items.sort(compareRanked);
      var bestSection = items[0];
      var pageTier = Math.max.apply(null, items.map(function (item) { return item.pageTier; }));
      var pageEntryDocument = pageEntries.get(bestSection.document.page || bestSection.document.url.split('#')[0]);
      var matchedPageEntry = items.find(function (item) { return item.document.url === (pageEntryDocument && pageEntryDocument.url); });
      var multiSectionBodyIntent = items.length >= 2 &&
        (bestSection.sectionTier <= MATCH_TIER.BODY || pageTier >= MATCH_TIER.STEM);
      var usePageEntry = Boolean(pageEntryDocument) &&
        (pageTier >= bestSection.sectionTier || multiSectionBodyIntent);
      var representative = usePageEntry
        ? (matchedPageEntry || {
          document: pageEntryDocument,
          pageTier: pageTier,
          sectionTier: MATCH_TIER.NONE,
          position: bestSection.position,
        })
        : bestSection;
      var candidateTier = Math.max(pageTier, bestSection.sectionTier);
      if (pageEntryDocument && pageEntryDocument.page_role === 'landing' && pageTier > MATCH_TIER.NONE) {
        candidateTier = Math.min(MATCH_TIER.EXACT, candidateTier + 1);
      }
      var pageCandidate = {
        document: representative.document,
        pageTier: pageTier,
        sectionTier: bestSection.sectionTier,
        tier: candidateTier,
        position: bestSection.position,
        pageEvidence: Math.min(items.length, 3),
        isPageCandidate: true,
        roleMatch: pageEntryDocument && pageEntryDocument.page_role === 'landing' && pageTier > MATCH_TIER.NONE,
      };
      candidates.push(pageCandidate);
      items.forEach(function (item) {
        if (item.document.url === representative.document.url) return;
        candidates.push({
          document: item.document,
          pageTier: item.pageTier,
          sectionTier: item.sectionTier,
          tier: Math.max(item.sectionTier, item.pageTier > MATCH_TIER.NONE ? item.pageTier - 1 : MATCH_TIER.NONE),
          position: item.position,
          pageEvidence: Math.min(items.length, 3),
          isPageCandidate: false,
          roleMatch: false,
        });
      });
    });
    candidates.sort(compareRanked);
    var selectedUrls = new Set();
    var pageCounts = new Map();
    return candidates.filter(function (item) {
      if (selectedUrls.has(item.document.url)) return false;
      var page = item.document.page || item.document.url.split('#')[0];
      if ((pageCounts.get(page) || 0) >= PER_PAGE_LIMIT) return false;
      selectedUrls.add(item.document.url);
      pageCounts.set(page, (pageCounts.get(page) || 0) + 1);
      return true;
    }).slice(0, RESULT_LIMIT);
  }

  function snippetFor(document, query) {
    var text = String(document.text || '').replace(/\s+/g, ' ').trim();
    if (!text) return '';
    var lower = normalize(text);
    var terms = query.split(/\s+/).filter(Boolean);
    var position = lower.indexOf(query);
    if (position < 0) {
      for (var i = 0; i < terms.length && position < 0; i += 1) {
        position = lower.indexOf(terms[i]);
      }
    }
    if (position < 0) position = 0;
    var start = Math.max(0, position - 70);
    var end = Math.min(text.length, start + 210);
    return (start > 0 ? '…' : '') + text.slice(start, end).trim() + (end < text.length ? '…' : '');
  }

  function appendHighlighted(element, text, query) {
    // Match normalized tokens, but keep the original Unicode and markup as text.
    var pattern = /[\p{L}\p{N}]+(?:[._/+:-][\p{L}\p{N}]+)*/gu;
    var end = 0;
    var match;
    while ((match = pattern.exec(text)) !== null) {
      var field = prepareField(match[0]);
      var hit = query.terms.some(function (term, index) {
        return coversTerms(field, { terms: [term], stems: [query.stems[index]] });
      });
      if (!hit) continue;
      element.appendChild(document.createTextNode(text.slice(end, match.index)));
      var mark = document.createElement('mark');
      mark.textContent = match[0];
      element.appendChild(mark);
      end = match.index + match[0].length;
    }
    element.appendChild(document.createTextNode(text.slice(end)));
  }

  function isTypingTarget(target) {
    if (!target) return false;
    var tag = target.tagName;
    return target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  function ensureHeadingIds() {
    var content = document.querySelector('article') || document.querySelector('main');
    if (!content) return;
    var usedIds = new Set();
    document.querySelectorAll('[id]').forEach(function (element) {
      usedIds.add(element.id);
    });
    content.querySelectorAll('h1, h2, h3').forEach(function (heading) {
      if (heading.id) return;
      var baseId = heading.textContent.trim().toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '') || 'section';
      var uniqueId = baseId;
      var suffix = 2;
      while (usedIds.has(uniqueId)) {
        uniqueId = baseId + '-' + suffix;
        suffix += 1;
      }
      heading.id = uniqueId;
      usedIds.add(uniqueId);
    });
  }

  function alignCurrentHash() {
    if (!window.location.hash || window.location.hash.length < 2) return;
    var id;
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch (error) {
      return;
    }
    var target = document.getElementById(id);
    if (!target) return;
    var cancelled = false;
    var cancelDelayedAlignment = function () { cancelled = true; };
    window.addEventListener('wheel', cancelDelayedAlignment, { once: true, passive: true });
    window.addEventListener('touchstart', cancelDelayedAlignment, { once: true, passive: true });
    window.addEventListener('pointerdown', cancelDelayedAlignment, { once: true, passive: true });
    window.addEventListener('keydown', cancelDelayedAlignment, { once: true });
    var align = function () {
      if (cancelled) return;
      var previousScrollBehavior = document.documentElement.style.scrollBehavior;
      document.documentElement.style.scrollBehavior = 'auto';
      target.scrollIntoView({ behavior: 'auto', block: 'start' });
      document.documentElement.style.scrollBehavior = previousScrollBehavior;
    };
    window.requestAnimationFrame(align);
    window.setTimeout(align, 150);
  }

  function initSearch() {
    ensureHeadingIds();
    alignCurrentHash();
    var header = document.querySelector('.top-nav .container, .site-header .header-inner, .navigation-section');
    if (!header || header.querySelector('.site-search')) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'site-search';
    wrapper.innerHTML =
      '<label class="site-search-label" for="site-search-input">Search MAPLE documentation</label>' +
      '<div class="site-search-field">' +
        '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>' +
        '<input class="site-search-input" id="site-search-input" type="search" placeholder="Search docs" autocomplete="off" spellcheck="false" role="combobox" aria-autocomplete="list" aria-controls="site-search-results" aria-expanded="false">' +
        '<kbd class="site-search-shortcut" aria-hidden="true">/</kbd>' +
      '</div>' +
      '<div class="site-search-results" hidden>' +
        '<p class="site-search-summary" role="status" aria-live="polite" aria-atomic="true"></p>' +
        '<div id="site-search-results" role="listbox" aria-label="Search results"></div>' +
      '</div>';

    var navTools = header.querySelector('.nav-tools');
    if (navTools) header.insertBefore(wrapper, navTools);
    else header.appendChild(wrapper);

    var input = wrapper.querySelector('.site-search-input');
    var panel = wrapper.querySelector('.site-search-results');
    var list = panel.querySelector('[role="listbox"]');
    var status = panel.querySelector('[role="status"]');
    var requestId = 0;
    var activeIndex = -1;
    var searchTimer = null;
    var composing = false;
    var INPUT_DELAY = 120;

    function resultLinks() {
      return Array.from(panel.querySelectorAll('.site-search-result'));
    }

    function setOpen(open) {
      panel.hidden = !open;
      input.setAttribute('aria-expanded', String(open));
      if (!open) {
        activeIndex = -1;
        input.removeAttribute('aria-activedescendant');
        resultLinks().forEach(function (link) {
          link.classList.remove('active');
          link.setAttribute('aria-selected', 'false');
        });
      }
    }

    function setActive(index) {
      var links = resultLinks();
      if (!links.length) return;
      activeIndex = (index + links.length) % links.length;
      links.forEach(function (link, itemIndex) {
        var active = itemIndex === activeIndex;
        link.classList.toggle('active', active);
        link.setAttribute('aria-selected', String(active));
      });
      input.setAttribute('aria-activedescendant', links[activeIndex].id);
      links[activeIndex].scrollIntoView({ block: 'nearest' });
    }

    function dismissSearch() {
      // Invalidate at the user action, not when a debounced search eventually runs.
      requestId += 1;
      window.clearTimeout(searchTimer);
      searchTimer = null;
      setOpen(false);
      list.replaceChildren();
      status.textContent = '';
      list.removeAttribute('aria-busy');
    }

    function showStatus(message, error) {
      status.textContent = message;
      status.className = 'site-search-summary' + (error ? ' error' : '');
      setOpen(true);
    }

    function renderResults(index, rawQuery) {
      var query = prepareQuery(rawQuery);
      var ranked = rankDocuments(index, rawQuery);
      list.replaceChildren();
      list.removeAttribute('aria-busy');
      activeIndex = -1;
      input.removeAttribute('aria-activedescendant');
      showStatus(ranked.length
        ? ranked.length + (ranked.length === 1 ? ' result' : ' results')
        : 'No matching documentation found.');

      ranked.forEach(function (item, index) {
        var record = item.document;
        var link = document.createElement('a');
        link.className = 'site-search-result';
        link.id = 'site-search-option-' + index;
        link.setAttribute('role', 'option');
        link.setAttribute('aria-selected', 'false');
        link.tabIndex = -1;
        link.href = new URL(record.url, siteRoot).href;

        var meta = document.createElement('span');
        meta.className = 'site-search-result-meta';
        meta.textContent = record.trail && record.trail.length
          ? record.trail.join(' › ')
          : record.type + ' · ' + record.title;
        var heading = document.createElement('strong');
        appendHighlighted(heading, String(record.heading || ''), query);
        var snippet = document.createElement('span');
        snippet.className = 'site-search-result-snippet';
        appendHighlighted(snippet, snippetFor(record, query.text), query);
        link.append(meta, heading, snippet);
        list.appendChild(link);
      });
    }

    function search(query, currentRequest) {
      searchTimer = null;
      list.setAttribute('aria-busy', 'true');
      showStatus('Searching…');
      loadIndex().then(function (index) {
        if (currentRequest === requestId) renderResults(index, query);
      }).catch(function () {
        if (currentRequest !== requestId) return;
        list.removeAttribute('aria-busy');
        showStatus('Search is temporarily unavailable. Try again.', true);
      });
    }

    function scheduleSearch() {
      dismissSearch();
      var query = input.value.trim();
      if (composing || query.length < 2) return;
      var currentRequest = requestId;
      searchTimer = window.setTimeout(function () {
        search(query, currentRequest);
      }, INPUT_DELAY);
    }

    function warmIndex() {
      // A failed speculative request must not become an unhandled rejection.
      loadIndex().catch(function () {});
    }

    input.addEventListener('input', function (event) {
      if (event.isComposing || composing) dismissSearch();
      else scheduleSearch();
    });
    input.addEventListener('compositionstart', function () {
      composing = true;
      dismissSearch();
    });
    input.addEventListener('compositionend', function () {
      composing = false;
      scheduleSearch();
    });
    input.addEventListener('pointerenter', warmIndex, { once: true });
    input.addEventListener('focus', function () {
      warmIndex();
      if (input.value.trim().length >= 2) scheduleSearch();
    });
    input.addEventListener('keydown', function (event) {
      if (composing || event.isComposing) return;
      var links = resultLinks();
      if (event.key === 'ArrowDown' && links.length) {
        event.preventDefault();
        setActive(activeIndex + 1);
      } else if (event.key === 'ArrowUp' && links.length) {
        event.preventDefault();
        setActive(activeIndex < 0 ? links.length - 1 : activeIndex - 1);
      } else if (event.key === 'Enter' && activeIndex >= 0 && links[activeIndex]) {
        event.preventDefault();
        links[activeIndex].click();
      } else if (event.key === 'Escape' && (!panel.hidden || searchTimer !== null)) {
        event.preventDefault();
        event.stopPropagation();
        dismissSearch();
      }
    });
    wrapper.addEventListener('focusout', function (event) {
      if (event.relatedTarget) {
        if (!wrapper.contains(event.relatedTarget)) dismissSearch();
        return;
      }
      // Let a pointer activation of a result finish before removing its link.
      window.setTimeout(function () {
        if (!wrapper.contains(document.activeElement)) dismissSearch();
      }, 0);
    });

    document.addEventListener('keydown', function (event) {
      if (event.isComposing) return;
      if ((event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey) ||
          ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k')) {
        if (isTypingTarget(event.target)) return;
        event.preventDefault();
        input.focus();
        input.select();
      }
    });
    document.addEventListener('pointerdown', function (event) {
      if (!wrapper.contains(event.target)) dismissSearch();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSearch);
  } else {
    initSearch();
  }
})();
