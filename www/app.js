let items = [], idx = 0, allTags = [], tagify, saving = false;
let filterMode = false;
let galleryIndex = -1;

const shot     = document.getElementById('shot');
const counter  = document.getElementById('counter');
const progress = document.getElementById('progress');
const filepath = document.getElementById('filepath');
const tagbar   = document.getElementById('tagbar');
const jump     = document.getElementById('jump');
const total    = document.getElementById('total');
const filterToggle = document.getElementById('filter-toggle');
const labelsDropdown = document.getElementById('labels');
const gallery = document.getElementById('gallery');

async function init() {
  const [its, tags] = await Promise.all([
    fetch('/api/items').then(r => r.json()),
    fetch('/api/tags').then(r => r.json()),
  ]);
  items = its;
  allTags = tags;

  tagify = new Tagify(document.getElementById('tag-input'), {
    whitelist: [...allTags],
    dropdown: { enabled: 2, closeOnSelect: false, maxItems: 30 },
  });
  tagify.on('add', onTagChange);
  tagify.on('remove', onTagChange);

  jump.addEventListener('click', () => {
    jump.contentEditable = 'true';
    jump.classList.add('editing');
    jump.focus();
    document.execCommand('selectAll', false, null);
  });
  jump.addEventListener('keydown', e => {
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
    render();
  });

  labelsDropdown.addEventListener('change', () => {
    const selected = labelsDropdown.value;
    if (!selected) return;
    tagify.addTags([selected]);
    labelsDropdown.value = '';
  });

  const saved = Number.parseInt(localStorage.getItem('tagger-index') || '', 10);
  idx = Number.isNaN(saved) ? 0 : Math.max(0, Math.min(items.length - 1, saved));
  render();
}

function render() {
  const item = items[idx];
  if (!item) return;

  shot.src = `/image?path=${encodeURIComponent(item.input_path)}`;
  filepath.textContent = item.input_path;
  jump.textContent = filterMode ? '' : String(idx + 1);
  total.textContent = String(items.length);
  localStorage.setItem('tagger-index', String(idx));

  const n = items.filter(i => i.categories?.length).length;
  progress.textContent = `${n} labeled`;

  const tagged = item.categories?.length > 0;
  tagbar.className = tagged ? 'labeled' : 'unlabeled';

  tagify.off('add', onTagChange);
  tagify.off('remove', onTagChange);
  tagify.removeAllTags();
  if (tagged) tagify.addTags(item.categories);
  tagify.on('add', onTagChange);
  tagify.on('remove', onTagChange);

  tagify.settings.whitelist = [...new Set([...allTags, ...(item.categories || [])])];
  renderLabelsDropdown();
  renderGallery();
}

async function onTagChange() {
  if (saving) return;
  if (filterMode) {
    renderGallery();
    return;
  }
  saving = true;
  const tags = tagify.value.map(t => t.value);
  items[idx].categories = tags;
  tags.forEach(t => { if (!allTags.includes(t)) allTags.push(t); });
  tagify.settings.whitelist = [...allTags];
  tagbar.className = tags.length ? 'labeled' : 'unlabeled';
  const n = items.filter(i => i.categories?.length).length;
  progress.textContent = `${n} labeled`;
  await fetch(`/api/item/${idx}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ categories: tags }),
  });
  await fetch('/api/purge', { method: 'POST' });
  saving = false;
}

function go(dir) {
  idx = Math.max(0, Math.min(items.length - 1, idx + dir));
  render();
}

function renderLabelsDropdown() {
  const counts = {};
  items.forEach(item => {
    (item.categories || []).forEach(category => {
      counts[category] = (counts[category] || 0) + 1;
    });
  });
  const labels = Object.keys(counts).sort((left, right) => {
    const diff = (counts[right] || 0) - (counts[left] || 0);
    if (diff !== 0) return diff;
    return left.localeCompare(right);
  });
  labelsDropdown.innerHTML = ['<option value="">labels</option>']
    .concat(labels.map(label => `<option value="${label}">${label} (${counts[label]})</option>`))
    .join('');
}

function renderGallery() {
  const inputElement = document.getElementById('tag-input');
  inputElement.placeholder = filterMode ? 'filter tags…' : 'add tags…';
  if (!filterMode) {
    gallery.classList.add('hidden');
    gallery.innerHTML = '';
    shot.classList.remove('hidden');
    galleryIndex = -1;
    return;
  }
  const selected = tagify.value.map(t => t.value);
  if (!selected.length) {
    gallery.classList.add('hidden');
    gallery.innerHTML = '';
    shot.classList.remove('hidden');
    galleryIndex = -1;
    return;
  }
  shot.classList.add('hidden');
  const matches = items.filter(item => selected.every(tag => (item.categories || []).includes(tag)));
  gallery.classList.remove('hidden');
  gallery.innerHTML = matches
    .map(item => `<div class="thumb" data-path="${item.input_path}">
        <img src="/image?path=${encodeURIComponent(item.input_path)}" alt="">
      </div>`)
    .join('');
  const thumbs = Array.from(gallery.querySelectorAll('.thumb'));
  thumbs.forEach((thumb, index) => {
    const image = thumb.querySelector('img');
    image.addEventListener('load', () => {
      const width = image.naturalWidth || 1;
      const height = image.naturalHeight || 1;
      const ratio = width / height;
      const clamped = Math.max(0.5, Math.min(2.0, ratio));
      thumb.style.aspectRatio = `${clamped}`;
    });
    const onHover = () => {
      galleryIndex = index;
      thumbs.forEach(t => t.classList.remove('active'));
      thumb.classList.add('active');
      const path = matches[index].input_path;
      filepath.textContent = path;
      jump.textContent = String(items.findIndex(item => item.input_path === path) + 1);
    };
    thumb.addEventListener('mouseenter', onHover);
    thumb.addEventListener('focus', onHover);
    thumb.addEventListener('click', () => {
      const path = matches[index].input_path;
      const nextIndex = items.findIndex(item => item.input_path === path);
      if (nextIndex >= 0) {
        idx = nextIndex;
        filterMode = false;
        filterToggle.classList.remove('active');
        render();
      }
    });
  });
  if (thumbs.length) {
    galleryIndex = Math.min(Math.max(galleryIndex, 0), thumbs.length - 1);
    thumbs[galleryIndex].classList.add('active');
  }
}

document.addEventListener('keydown', e => {
  const inInput = document.activeElement === tagify.DOM.input;
  const inJump = document.activeElement === jump;
  if (inJump) return;
  if (inInput) {
    if (e.key === 'Escape') { tagify.DOM.input.blur(); e.preventDefault(); }
    if (e.key === 'Enter' && tagify.state.inputText === '') {
      tagify.DOM.input.blur();
      go(1);
      e.preventDefault();
    }
    return;
  }
  if (filterMode && gallery.classList.contains('hidden') === false) {
    if (e.key === 'j' || e.key === 'k') {
      const thumbs = Array.from(gallery.querySelectorAll('.thumb'));
      if (thumbs.length) {
        if (e.key === 'j') galleryIndex = Math.min(thumbs.length - 1, galleryIndex + 1);
        if (e.key === 'k') galleryIndex = Math.max(0, galleryIndex - 1);
        thumbs.forEach(t => t.classList.remove('active'));
        const target = thumbs[galleryIndex];
        target.classList.add('active');
        const path = target.getAttribute('data-path');
        filepath.textContent = path;
        jump.textContent = String(items.findIndex(item => item.input_path === path) + 1);
        e.preventDefault();
        return;
      }
    }
  }
  if (e.key === 'j') go(1);
  if (e.key === 'k') go(-1);
  if (e.key === 'Enter' || e.key === '/') {
    tagify.DOM.input.focus();
    e.preventDefault();
  }
});

const nativeInput = document.getElementById('tag-input');
nativeInput.style.color = '#e8e8e8';
nativeInput.style.setProperty('--placeholder-color', '#909090');

init();
