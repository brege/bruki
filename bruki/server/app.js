// state
let allItems = [],
  items = [],
  idx = 0,
  allTags = [],
  tagify;
let saving = false,
  filterMode = false,
  forceSingleView = false;
let galleryExpanded = true,
  galleryModifierHeld = false;
let galleryIndex = -1,
  galleryMatches = [];
let selectedCluster = '',
  tagScope = '__any__';
let selectedPaths = new Set(),
  selectionAnchorIndex = -1;
let lastMlStage = '',
  lastMlStatusKey = '';
let mlPollDelayMs = 3000,
  mlPollTimer = null;
let thumbMinPx = 180;

const sampleMode = window.TAGGER_SAMPLE_MODE === true;
const THUMB_MIN_PX = 120,
  THUMB_MAX_PX = 420,
  THUMB_STEP_PX = 20;

// DOM refs
const shot = document.getElementById('shot');
const progress = document.getElementById('progress');
const filepathPath = document.getElementById('filepath-path');
const filepathLabels = document.getElementById('filepath-labels');
const tagbar = document.getElementById('tagbar');
const jump = document.getElementById('jump');
const total = document.getElementById('total');
const filterToggle = document.getElementById('filter-toggle');
const tagsScopeDropdown = document.getElementById('tags-scope');
const clustersDropdown = document.getElementById('clusters');
const gallery = document.getElementById('gallery');
const mlStatus = document.getElementById('ml-status');
const mlSources = document.getElementById('ml-sources');
const bulkCount = document.getElementById('bulk-count');
const bulkSelectToggle = document.getElementById('bulk-select-toggle');
const bulkExpand = document.getElementById('bulk-expand');
const applyTagsButton = document.getElementById('apply-tags');
const thumbSizeDown = document.getElementById('thumb-size-down');
const thumbSizeUp = document.getElementById('thumb-size-up');

// helpers
const esc = (v) =>
  String(v)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

async function fetchJson(url, opts) {
  return (await fetch(url, opts)).json();
}

const taggedCount = () =>
  allItems.filter((it) => (it.categories || []).length).length;
const isGalleryEnabled = () =>
  (filterMode || !!selectedCluster) && !forceSingleView;

function go(delta) {
  idx = Math.max(0, Math.min(items.length - 1, idx + delta));
  render();
}

function onTagChange() {
  if (!saving && filterMode) renderGallery();
}

// selection
function clearSelection() {
  selectedPaths.clear();
  selectionAnchorIndex = -1;
}

function setThumbSelected(thumb, sel) {
  thumb.classList.toggle('selected', sel);
  const check = thumb.querySelector('.check');
  if (check) check.textContent = sel ? '✓' : '';
}

// filepath bar
function setFilepath(pathText, categories = []) {
  filepathPath.textContent = pathText || '';
  filepathLabels.replaceChildren();
  if (!categories.length) return;
  const frag = document.createDocumentFragment();
  for (const cat of categories) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'filepath-tag';
    btn.dataset.tag = cat;
    btn.textContent = cat;
    frag.appendChild(btn);
  }
  filepathLabels.appendChild(frag);
}

// bulk bar
function updateGalleryCheckVisibility() {
  gallery.classList.toggle('has-selection', selectedPaths.size > 0);
  gallery.classList.toggle('modifier-held', galleryModifierHeld);
}

function updateBulkBar(galleryEnabled) {
  updateGalleryCheckVisibility();
  thumbSizeDown.disabled = !galleryEnabled || thumbMinPx <= THUMB_MIN_PX;
  thumbSizeUp.disabled = !galleryEnabled || thumbMinPx >= THUMB_MAX_PX;
  bulkCount.textContent = `${selectedPaths.size} selected`;
  applyTagsButton.disabled = filterMode;
  const visCount = galleryMatches.length;
  const allSel =
    visCount > 0 &&
    galleryMatches.every((it) => selectedPaths.has(it.input_path));
  bulkSelectToggle.textContent = allSel ? 'select none' : 'select all';
  bulkSelectToggle.disabled = visCount === 0 || !galleryEnabled;
  if (!galleryEnabled) {
    bulkExpand.textContent = 'expand';
    bulkExpand.disabled = visCount === 0;
  } else {
    bulkExpand.textContent = galleryExpanded ? 'collapse' : 'expand';
    bulkExpand.disabled = false;
  }
}

// tag operations
async function applyTagsToCurrentImage() {
  if (saving || filterMode) return;
  const item = items[idx];
  if (!item) return;
  saving = true;
  try {
    const tags = tagify.value.map((e) => e.value);
    item.categories = tags;
    const rowIdx = item._idx;
    if (Number.isInteger(rowIdx) && allItems[rowIdx])
      allItems[rowIdx].categories = tags;
    tags.forEach((tag) => {
      if (!allTags.includes(tag)) allTags.push(tag);
    });
    tagify.settings.whitelist = [...allTags];
    tagbar.className = tags.length ? 'labeled' : 'unlabeled';
    progress.textContent = `${taggedCount()} tagged`;
    const res = await fetch(`/api/item/${rowIdx}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories: tags }),
    });
    if (!res.ok) throw new Error('single tag apply failed');
    applyClusterFilter(true);
  } finally {
    saving = false;
  }
}

async function applyTagsToSelected() {
  if (saving || !selectedPaths.size) return;
  const tags = tagify.value.map((e) => e.value);
  const targets = allItems.filter((it) => selectedPaths.has(it.input_path));
  if (!targets.length) return;
  saving = true;
  try {
    tags.forEach((tag) => {
      if (!allTags.includes(tag)) allTags.push(tag);
    });
    tagify.settings.whitelist = [...allTags];
    // items shares object refs with allItems one pass suffices
    allItems
      .filter((it) => selectedPaths.has(it.input_path))
      .forEach((it) => {
        it.categories = [...tags];
      });
    const responses = await Promise.all(
      targets.map((it) =>
        fetch(`/api/item/${it._idx}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ categories: tags }),
        }),
      ),
    );
    if (responses.some((r) => !r.ok)) throw new Error('bulk tag apply failed');
    progress.textContent = `${taggedCount()} tagged`;
    renderTagsScopeDropdown();
    clearSelection();
    applyClusterFilter(true);
  } finally {
    saving = false;
  }
}

async function applyTags() {
  if (filterMode) return;
  if (selectedPaths.size) await applyTagsToSelected();
  else await applyTagsToCurrentImage();
}

// filter / cluster state
function applyClusterFilter(preservePath = true) {
  const currentPath = preservePath ? items[idx]?.input_path : '';
  clearSelection();
  forceSingleView = false;
  let scoped = [...allItems];
  if (tagScope === '__none__') {
    scoped = scoped.filter((it) => !(it.categories || []).length);
  } else if (tagScope !== '__any__') {
    scoped = scoped.filter((it) => (it.categories || []).includes(tagScope));
  }
  if (selectedCluster) {
    scoped = scoped.filter(
      (it) => String(it.cluster ?? '') === selectedCluster,
    );
  }
  items = scoped;
  if (!items.length) {
    idx = 0;
    render();
    return;
  }
  if (currentPath) {
    const next = items.findIndex((it) => it.input_path === currentPath);
    idx = next >= 0 ? next : Math.min(idx, items.length - 1);
  } else {
    idx = Math.min(idx, items.length - 1);
  }
  render();
}

async function reloadItems() {
  allItems = await fetchJson('/api/items');
  applyClusterFilter(true);
}

// ML
function formatMlStatus(status) {
  const stage = status.stage || 'idle';
  if (stage === 'embedding' || stage === 'ocr') {
    const done = status.processed_images || 0;
    const count = status.total_images || 0;
    const rate = (status.rate_images_per_second || 0).toFixed(2);
    const eta = status.eta_seconds || 0;
    return `ml: ${stage} ${done}/${count} · ${rate} img/s · eta ${eta}s`;
  }
  if (stage === 'clustering')
    return `ml: clustering k=${status.cluster_count || '—'}`;
  if (stage === 'done')
    return `ml: done ${status.total_images || 0} images · k=${status.cluster_count || '—'}`;
  if (stage === 'error') return `ml: error ${status.error || ''}`.trim();
  if (stage === 'scanning')
    return `ml: scanning sources (${status.total_images || 0} images)`;
  return `ml: ${stage}`;
}

function formatSourceStats(status) {
  const stats = status.source_stats || [];
  if (!stats.length) return (status.source_roots || []).join(' | ');
  return stats.map((r) => `${r.series}/${r.source}: ${r.count}`).join(' | ');
}

async function refreshMlStatus() {
  const status = await fetchJson('/api/ml/status');
  const stage = status.stage || 'idle';
  const statusKey = [
    stage,
    status.processed_images || 0,
    status.total_images || 0,
    status.cluster_count || 0,
    status.eta_seconds || 0,
    status.error || '',
  ].join(':');
  const changed = statusKey !== lastMlStatusKey;
  mlStatus.textContent = formatMlStatus(status);
  mlSources.textContent = formatSourceStats(status);
  if (stage === 'done' && lastMlStage !== 'done') {
    await Promise.all([reloadItems(), refreshClusters()]);
  }
  lastMlStage = stage;
  lastMlStatusKey = statusKey;
  if (
    stage === 'embedding' ||
    stage === 'clustering' ||
    stage === 'scanning' ||
    stage === 'ocr'
  ) {
    mlPollDelayMs = changed
      ? 3000
      : Math.min(Math.round(mlPollDelayMs * 1.5), 15000);
  } else if (stage === 'done' || stage === 'error') {
    mlPollDelayMs = changed
      ? 10000
      : Math.min(Math.round(mlPollDelayMs * 2), 120000);
  } else {
    mlPollDelayMs = changed
      ? 5000
      : Math.min(Math.round(mlPollDelayMs * 1.5), 60000);
  }
}

async function pollMlStatus() {
  await refreshMlStatus();
  mlPollTimer = setTimeout(pollMlStatus, mlPollDelayMs);
}

async function initMl() {
  await fetchJson('/api/ml/start', { method: 'POST' });
  await Promise.all([refreshMlStatus(), refreshClusters()]);
  if (mlPollTimer !== null) clearTimeout(mlPollTimer);
  mlPollTimer = setTimeout(pollMlStatus, mlPollDelayMs);
}

// render
function render() {
  total.textContent = String(items.length);
  progress.textContent = `${taggedCount()} tagged`;
  const item = items[idx];
  if (!item) {
    shot.src = '';
    setFilepath(
      selectedCluster
        ? `no images in cluster c${selectedCluster}`
        : 'no images',
      [],
    );
    jump.textContent = '0';
    tagbar.className = 'unlabeled';
    tagify.removeAllTags();
    renderTagsScopeDropdown();
    renderGallery();
    return;
  }
  shot.src = `/image?path=${encodeURIComponent(item.input_path)}`;
  setFilepath(item.input_path, item.categories || []);
  jump.textContent = filterMode ? '' : String(idx + 1);
  localStorage.setItem('tagger-index', String(idx));
  const tagged = (item.categories || []).length > 0;
  tagbar.className = tagged ? 'labeled' : 'unlabeled';
  if (!filterMode) {
    tagify.off('add', onTagChange);
    tagify.off('remove', onTagChange);
    tagify.removeAllTags();
    if (tagged) tagify.addTags(item.categories);
    tagify.on('add', onTagChange);
    tagify.on('remove', onTagChange);
  }
  tagify.settings.whitelist = [
    ...new Set([...allTags, ...(item.categories || [])]),
  ];
  renderTagsScopeDropdown();
  renderGallery();
}

function renderTagsScopeDropdown() {
  const counts = {};
  allItems.forEach((it) => {
    (it.categories || []).forEach((cat) => {
      counts[cat] = (counts[cat] || 0) + 1;
    });
  });
  const tags = Object.keys(counts).sort((a, b) => {
    const d = (counts[b] || 0) - (counts[a] || 0);
    return d !== 0 ? d : a.localeCompare(b);
  });
  tagsScopeDropdown.innerHTML = [
    '<option value="__any__">any tags</option>',
    '<option value="__none__">no tags</option>',
    '<option value="__sep__" disabled>---------</option>',
    ...tags.map(
      (t) => `<option value="${esc(t)}">${esc(t)} (${counts[t]})</option>`,
    ),
  ].join('');
  if (
    !['__any__', '__none__'].includes(tagScope) &&
    !Object.hasOwn(counts, tagScope)
  )
    tagScope = '__any__';
  tagsScopeDropdown.value = tagScope;
}

function renderClusterDropdown(clusters) {
  const cur = selectedCluster;
  clustersDropdown.innerHTML = ['<option value="">all clusters</option>']
    .concat(
      (clusters || []).map(
        (c) => `<option value="${c.id}">c${c.id} (${c.count})</option>`,
      ),
    )
    .join('');
  clustersDropdown.value = cur;
}

async function refreshClusters() {
  renderClusterDropdown(await fetchJson('/api/ml/clusters'));
}

function renderGallery() {
  document.getElementById('tag-input').placeholder = filterMode
    ? 'filter tags…'
    : 'add tags…';
  const enabled = isGalleryEnabled();
  if (!enabled) {
    gallery.classList.add('hidden');
    gallery.innerHTML = '';
    shot.classList.remove('hidden');
    galleryIndex = -1;
    galleryMatches = [];
    updateBulkBar(false);
    return;
  }
  const filterTags = filterMode ? tagify.value.map((e) => e.value) : [];
  const matches = filterTags.length
    ? items.filter((it) =>
        filterTags.every((t) => (it.categories || []).includes(t)),
      )
    : [...items];
  galleryMatches = matches;
  const visPaths = new Set(matches.map((it) => it.input_path));
  selectedPaths = new Set([...selectedPaths].filter((p) => visPaths.has(p)));

  shot.classList.add('hidden');
  gallery.classList.remove('hidden');
  gallery.classList.toggle('expanded', galleryExpanded);
  gallery.style.setProperty('--thumb-min', `${thumbMinPx}px`);
  gallery.innerHTML = matches
    .map((item, i) => {
      const sel = selectedPaths.has(item.input_path);
      const tags = (item.categories || [])
        .map((t) => `<span class="tag">${esc(t)}</span>`)
        .join('');
      return `<div class="thumb${sel ? ' selected' : ''}" data-path="${esc(item.input_path)}" data-idx="${i}">
      <button class="check" type="button">${sel ? '✓' : ''}</button>
      <img src="/image?path=${encodeURIComponent(item.input_path)}" alt="">
      <div class="caption">${tags}</div>
    </div>`;
    })
    .join('');

  const thumbs = gallery.querySelectorAll('.thumb');
  galleryIndex = thumbs.length
    ? Math.min(Math.max(galleryIndex, 0), thumbs.length - 1)
    : -1;
  if (galleryIndex >= 0) thumbs[galleryIndex].classList.add('active');
  updateBulkBar(true);
}

// gallery event delegation (set up once in init)
function initGalleryEvents() {
  // clear fixed aspect-ratio after image loads
  gallery.addEventListener(
    'load',
    (e) => {
      if (e.target.tagName === 'IMG')
        e.target.closest('.thumb')?.style.removeProperty('aspect-ratio');
    },
    true,
  );

  // hover / focus both via delegation (mouseover bubbles; use focusin for focus)
  const onThumbActivate = (e) => {
    const thumb = e.target.closest('.thumb');
    if (!thumb || !gallery.contains(thumb)) return;
    const i = +thumb.dataset.idx;
    if (galleryIndex === i) return;
    galleryIndex = i;
    gallery.querySelectorAll('.thumb.active').forEach((t) => {
      t.classList.remove('active');
    });
    thumb.classList.add('active');
    const item = galleryMatches[i];
    if (!item) return;
    setFilepath(item.input_path, item.categories || []);
    jump.textContent = String(
      items.findIndex((it) => it.input_path === item.input_path) + 1,
    );
  };
  gallery.addEventListener('mouseover', onThumbActivate);
  gallery.addEventListener('focusin', onThumbActivate);

  // click selection or single-view navigation
  gallery.addEventListener('click', (e) => {
    const thumb = e.target.closest('.thumb');
    if (!thumb || !gallery.contains(thumb)) return;
    const i = +thumb.dataset.idx;
    const item = galleryMatches[i];
    if (!item) return;
    const path = item.input_path;
    const dotClick = !!e.target.closest('.check');
    const additive = e.ctrlKey || e.metaKey || dotClick;
    const ranged = e.shiftKey;
    const thumbs = gallery.querySelectorAll('.thumb');

    if (ranged && selectionAnchorIndex >= 0) {
      const lo = Math.min(selectionAnchorIndex, i);
      const hi = Math.max(selectionAnchorIndex, i);
      for (let j = lo; j <= hi; j++) {
        selectedPaths.add(galleryMatches[j].input_path);
        setThumbSelected(thumbs[j], true);
      }
    } else if (additive || !selectedCluster) {
      if (selectedPaths.has(path)) {
        selectedPaths.delete(path);
        setThumbSelected(thumb, false);
      } else {
        if (!additive && !ranged) {
          selectedPaths.clear();
          thumbs.forEach((t) => {
            setThumbSelected(t, false);
          });
        }
        selectedPaths.add(path);
        setThumbSelected(thumb, true);
      }
      selectionAnchorIndex = i;
    } else {
      // cluster mode, plain click → single-view
      const nextIdx = items.findIndex((it) => it.input_path === path);
      if (nextIdx >= 0) {
        idx = nextIdx;
        forceSingleView = true;
        render();
      }
      return;
    }
    updateBulkBar(true);
  });

  // dblclick exit gallery, open single view
  gallery.addEventListener('dblclick', (e) => {
    const thumb = e.target.closest('.thumb');
    if (!thumb || !gallery.contains(thumb)) return;
    const path = galleryMatches[+thumb.dataset.idx]?.input_path;
    const nextIdx = items.findIndex((it) => it.input_path === path);
    if (nextIdx < 0) return;
    idx = nextIdx;
    clearSelection();
    filterMode = false;
    filterToggle.classList.remove('active');
    render();
  });
}

// keyboard
document.addEventListener('keydown', (e) => {
  // modifier state sync (drives check-circle visibility)
  const held = e.shiftKey || e.ctrlKey || e.metaKey;
  if (galleryModifierHeld !== held) {
    galleryModifierHeld = held;
    updateGalleryCheckVisibility();
  }

  const inInput = tagify && document.activeElement === tagify.DOM.input;
  if (document.activeElement === jump) return;

  if (inInput) {
    if (e.key === 'Escape') {
      tagify.DOM.input.blur();
      e.preventDefault();
    }
    if (e.key === 'Enter' && tagify.state.inputText === '') {
      tagify.DOM.input.blur();
      go(1);
      e.preventDefault();
    }
    return;
  }

  if (
    !gallery.classList.contains('hidden') &&
    (e.key === 'j' || e.key === 'k')
  ) {
    const thumbs = Array.from(gallery.querySelectorAll('.thumb'));
    if (thumbs.length) {
      galleryIndex =
        e.key === 'j'
          ? Math.min(thumbs.length - 1, galleryIndex + 1)
          : Math.max(0, galleryIndex - 1);
      thumbs.forEach((t) => {
        t.classList.remove('active');
      });
      const target = thumbs[galleryIndex];
      target.classList.add('active');
      target.scrollIntoView({ block: 'nearest' });
      const activeItem = galleryMatches[galleryIndex];
      if (activeItem) {
        setFilepath(activeItem.input_path, activeItem.categories || []);
        jump.textContent = String(
          items.findIndex((it) => it.input_path === activeItem.input_path) + 1,
        );
      }
      e.preventDefault();
      return;
    }
  }

  if (e.key === 'Escape' && forceSingleView) {
    forceSingleView = false;
    render();
    return;
  }
  if (e.key === 'j') go(1);
  if (e.key === 'k') go(-1);
  if (e.key === 'Enter' || e.key === '/') {
    tagify.DOM.input.focus();
    e.preventDefault();
  }
});

document.addEventListener('keyup', (e) => {
  const held = e.shiftKey || e.ctrlKey || e.metaKey;
  if (galleryModifierHeld !== held) {
    galleryModifierHeld = held;
    updateGalleryCheckVisibility();
  }
});

window.addEventListener('blur', () => {
  if (!galleryModifierHeld) return;
  galleryModifierHeld = false;
  updateGalleryCheckVisibility();
});

// init
async function init() {
  const [all, tags] = await Promise.all([
    fetchJson('/api/items'),
    fetchJson('/api/tags'),
  ]);
  allItems = all;
  allTags = tags;
  items = [...allItems];
  renderTagsScopeDropdown();

  tagify = new Tagify(document.getElementById('tag-input'), {
    whitelist: [...allTags],
    dropdown: { enabled: 2, closeOnSelect: false, maxItems: 30 },
  });
  tagify.on('add', onTagChange);
  tagify.on('remove', onTagChange);

  initGalleryEvents();

  jump.addEventListener('click', () => {
    jump.contentEditable = 'true';
    jump.classList.add('editing');
    jump.focus();
    document.execCommand('selectAll', false, null);
  });
  jump.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const target = Number.parseInt(jump.textContent, 10);
      if (!Number.isNaN(target)) {
        idx = Math.max(0, Math.min(items.length - 1, target - 1));
        render();
      }
      jump.blur();
      e.preventDefault();
    }
    if (e.key === 'Escape') {
      jump.textContent = String(idx + 1);
      jump.blur();
      e.preventDefault();
    }
  });
  jump.addEventListener('blur', () => {
    jump.contentEditable = 'false';
    jump.classList.remove('editing');
  });

  filterToggle.addEventListener('click', () => {
    filterMode = !filterMode;
    filterToggle.classList.toggle('active', filterMode);
    if (!filterMode && !selectedCluster) clearSelection();
    forceSingleView = false;
    render();
  });

  tagsScopeDropdown.addEventListener('change', () => {
    tagScope = tagsScopeDropdown.value || '__any__';
    applyClusterFilter(true);
  });

  filepathLabels.addEventListener('click', (e) => {
    const btn = e.target.closest('.filepath-tag');
    if (!btn) return;
    tagScope = btn.dataset.tag || '__any__';
    applyClusterFilter(true);
  });

  clustersDropdown.addEventListener('change', () => {
    selectedCluster = clustersDropdown.value;
    applyClusterFilter(true);
  });

  bulkSelectToggle.addEventListener('click', () => {
    const paths = galleryMatches.map((it) => it.input_path);
    const allSel = paths.length > 0 && paths.every((p) => selectedPaths.has(p));
    if (allSel)
      paths.forEach((p) => {
        selectedPaths.delete(p);
      });
    else
      paths.forEach((p) => {
        selectedPaths.add(p);
      });
    renderGallery();
  });

  applyTagsButton.addEventListener('click', () =>
    applyTags().catch(console.error),
  );

  bulkExpand.addEventListener('click', () => {
    if (forceSingleView) {
      forceSingleView = false;
      render();
      return;
    }
    galleryExpanded = !galleryExpanded;
    renderGallery();
  });

  thumbSizeDown.addEventListener('click', () => {
    if (thumbSizeDown.disabled) return;
    thumbMinPx = Math.max(THUMB_MIN_PX, thumbMinPx - THUMB_STEP_PX);
    renderGallery();
  });
  thumbSizeUp.addEventListener('click', () => {
    if (thumbSizeUp.disabled) return;
    thumbMinPx = Math.min(THUMB_MAX_PX, thumbMinPx + THUMB_STEP_PX);
    renderGallery();
  });

  const saved = Number.parseInt(localStorage.getItem('tagger-index') || '', 10);
  idx = Number.isNaN(saved)
    ? 0
    : Math.max(0, Math.min(items.length - 1, saved));
  render();

  if (sampleMode) {
    mlStatus.textContent = 'ml: disabled (sample mode)';
    mlSources.textContent = '';
    clustersDropdown.disabled = true;
    return;
  }
  await initMl();
}

init();
