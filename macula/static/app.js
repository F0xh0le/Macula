// file: macula/static/app.js

(function () {
  const tree = document.getElementById('tree');
  const searchInput = document.getElementById('search');
  const searchHint = document.getElementById('searchHint');
  const regexToggle = document.getElementById('regexToggle');

  const UPLOAD_TARGET = window.MACULA_UPLOAD_TARGET || '';
  const UPLOADS_ENABLED = UPLOAD_TARGET.length > 0;

  // ---- Search mode ----
  // 'substring' (default) or 'regex'.
  let searchMode = 'substring';
  try {
    const saved = localStorage.getItem('macula_search_mode');
    if (saved === 'regex') searchMode = 'regex';
  } catch (e) {}
  if (regexToggle && searchMode === 'regex') {
    regexToggle.classList.add('active');
  }

  function encodePath(p) { return p.split('/').map(encodeURIComponent).join('/'); }
  function setSearchHint(msg, isError) {
    if (!searchHint) return;
    searchHint.textContent = msg || '';
    searchHint.classList.toggle('hidden', !msg);
    searchHint.classList.toggle('error', !!isError);
  }
  function debounce(fn, ms) {
    let t;
    return function () {
      const ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  // ---- Search: compile / match / highlight ----
  function compileSearch(q) {
    if (!q) return null;
    if (searchMode === 'regex') {
      try {
        return { re: new RegExp(q, 'i') };
      } catch (e) {
        return { error: e.message };
      }
    }
    return { needle: q.toLowerCase() };
  }

  function matchName(name, compiled) {
    if (!compiled) return true;
    if (compiled.error) return false;
    if (compiled.needle !== undefined) {
      return name.toLowerCase().includes(compiled.needle);
    }
    return compiled.re.test(name);
  }

  function highlightSubstring(el, text, needle) {
    const frag = document.createDocumentFragment();
    const lower = text.toLowerCase();
    let i = 0;
    while (i < text.length) {
      const idx = lower.indexOf(needle, i);
      if (idx === -1) {
        frag.appendChild(document.createTextNode(text.slice(i)));
        break;
      }
      if (idx > i) frag.appendChild(document.createTextNode(text.slice(i, idx)));
      const mark = document.createElement('mark');
      mark.textContent = text.slice(idx, idx + needle.length);
      frag.appendChild(mark);
      i = idx + needle.length;
    }
    el.replaceChildren(frag);
  }

  function highlightRegex(el, text, re) {
    const frag = document.createDocumentFragment();
    const gre = new RegExp(re.source, 'gi');
    let last = 0;
    let m;
    let guard = 0;
    while ((m = gre.exec(text)) !== null && guard++ < 10000) {
      if (m.index > last) {
        frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      }
      const mark = document.createElement('mark');
      mark.textContent = m[0];
      frag.appendChild(mark);
      last = m.index + m[0].length;
      if (m[0].length === 0) gre.lastIndex++;
    }
    if (last < text.length) {
      frag.appendChild(document.createTextNode(text.slice(last)));
    }
    el.replaceChildren(frag);
  }

  function highlightName(el, text, compiled) {
    if (!compiled || compiled.error) {
      el.textContent = text;
      return;
    }
    if (compiled.needle !== undefined) {
      highlightSubstring(el, text, compiled.needle);
    } else {
      highlightRegex(el, text, compiled.re);
    }
  }

  function makeIcon(pathData, cls) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', cls);
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    const p = document.createElementNS(ns, 'path');
    p.setAttribute('d', pathData);
    svg.appendChild(p);
    return svg;
  }
  const P = {
    folder:   'M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z',
    file:     'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z M14 2v5h5',
    chevron:  'm9 18 6-6-6-6',
    zip:      'M21 8v13H3V8 M1 3h22v5H1z M10 12h4',
    tgz:      'M21 8v13H3V8 M1 3h22v5H1z M9 12h6 M9 16h6',
    open:     'M15 3h6v6 M10 14 21 3 M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6',
    download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3'
  };

  function buildDirNode(item, parentPath) {
    const fullPath = parentPath + (item.path || (item.name + '/'));
    const el = document.createElement('div');
    el.className = 'node dir';
    if (item.mount) el.classList.add('mount');
    if (item.upload) el.classList.add('upload');
    el.dataset.name = item.name;
    el.dataset.path = fullPath;

    const row = document.createElement('div');
    row.className = 'row';

    const toggle = document.createElement('span');
    toggle.className = 'toggle';
    toggle.appendChild(makeIcon(P.chevron, 'icon'));
    row.appendChild(toggle);

    row.appendChild(makeIcon(P.folder, 'icon icon-folder'));

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = item.name;
    row.appendChild(name);

    if (item.upload) {
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = 'upload';
      row.appendChild(badge);
    } else if (item.mount) {
      const badge = document.createElement('span');
      badge.className = 'badge mount';
      badge.textContent = 'mount';
      row.appendChild(badge);
    }

    const actions = document.createElement('div');
    actions.className = 'row-actions';
    const enc = encodePath(fullPath);
    const zipA = document.createElement('a');
    zipA.className = 'mini'; zipA.title = 'Download as ZIP';
    zipA.href = enc + '?download=zip';
    zipA.appendChild(makeIcon(P.zip, 'icon'));
    actions.appendChild(zipA);
    const tgzA = document.createElement('a');
    tgzA.className = 'mini'; tgzA.title = 'Download as TAR.GZ';
    tgzA.href = enc + '?download=tgz';
    tgzA.appendChild(makeIcon(P.tgz, 'icon'));
    actions.appendChild(tgzA);
    const openA = document.createElement('a');
    openA.className = 'mini'; openA.title = 'Open folder page';
    openA.href = enc;
    openA.appendChild(makeIcon(P.open, 'icon'));
    actions.appendChild(openA);
    row.appendChild(actions);

    const children = document.createElement('div');
    children.className = 'children';
    el.appendChild(row);
    el.appendChild(children);
    return el;
  }

  function buildFileNode(item, parentPath) {
    const fullPath = parentPath + (item.path || item.name);
    const el = document.createElement('div');
    el.className = 'node file';
    el.dataset.name = item.name;
    el.dataset.path = fullPath;

    const row = document.createElement('div');
    row.className = 'row';

    const toggle = document.createElement('span');
    toggle.className = 'toggle leaf';
    row.appendChild(toggle);

    row.appendChild(makeIcon(P.file, 'icon icon-file'));

    const enc = encodePath(fullPath);

    const name = document.createElement('a');
    name.className = 'name';
    name.href = enc + '?mode=view';
    name.textContent = item.name;
    row.appendChild(name);

    const size = document.createElement('span');
    size.className = 'size';
    size.textContent = item.size_human || '';
    row.appendChild(size);

    const actions = document.createElement('div');
    actions.className = 'row-actions';
    const dl = document.createElement('a');
    dl.className = 'mini'; dl.title = 'Download';
    dl.href = enc + '?mode=download';
    dl.appendChild(makeIcon(P.download, 'icon'));
    actions.appendChild(dl);
    row.appendChild(actions);

    el.appendChild(row);
    return el;
  }

  async function loadChildren(node) {
    if (node.dataset.loaded === '1' || node.dataset.loading === '1') return;
    node.dataset.loading = '1';
    const children = node.querySelector(':scope > .children');
    const loader = document.createElement('div');
    loader.className = 'loading-indicator';
    loader.textContent = 'loading…';
    children.appendChild(loader);

    const path = node.dataset.path;
    try {
      const resp = await fetch(encodePath(path) + '?format=json&depth=0');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      loader.remove();
      const t = data.tree || {};
      const before = children.children.length;
      for (const d of (t.dirs || [])) children.appendChild(buildDirNode(d, path));
      for (const f of (t.files || [])) children.appendChild(buildFileNode(f, path));
      if (children.children.length === before) {
        const empty = document.createElement('div');
        empty.className = 'empty-leaf';
        empty.textContent = '(empty)';
        children.appendChild(empty);
      }
      node.dataset.loaded = '1';
    } catch (e) {
      loader.textContent = '[!] ' + e.message;
      loader.style.color = 'var(--danger)';
    } finally {
      node.dataset.loading = '0';
    }
  }

  function toggleNode(node) {
    if (!node.classList.contains('dir')) return;
    const willExpand = !node.classList.contains('expanded');
    node.classList.toggle('expanded', willExpand);
    if (willExpand && node.dataset.loaded !== '1') loadChildren(node);
  }

  async function expandAll(node) {
    if (!node.classList.contains('dir')) return;
    node.classList.add('expanded');
    if (node.dataset.loaded !== '1') await loadChildren(node);
    for (const k of node.querySelectorAll(':scope > .children > .node.dir')) {
      await expandAll(k);
    }
  }
  function collapseAll(node) {
    if (node.classList.contains('dir')) node.classList.remove('expanded');
    for (const k of node.querySelectorAll(':scope > .children > .node')) collapseAll(k);
  }

  tree.addEventListener('click', function (e) {
    if (e.target.closest('a')) return;
    const node = e.target.closest('.node.dir');
    if (!node) return;
    toggleNode(node);
  });

  function filterNode(node, compiled) {
    const name = node.dataset.name || '';
    const nameEl = node.querySelector(':scope > .row > .name');
    let childMatch = false;
    for (const c of node.querySelectorAll(':scope > .children > .node')) {
      if (filterNode(c, compiled)) childMatch = true;
    }
    const selfMatch = matchName(name, compiled);
    const show = selfMatch || childMatch;
    node.classList.toggle('hidden', !show);
    if (compiled && childMatch && node.classList.contains('dir')
        && node.dataset.loaded === '1') {
      node.classList.add('expanded');
    }
    if (nameEl) {
      if (compiled && selfMatch) highlightName(nameEl, name, compiled);
      else nameEl.textContent = name;
    }
    return show;
  }

  function applySearch() {
    const q = searchInput.value.trim();
    const compiled = compileSearch(q);

    if (regexToggle) {
      regexToggle.classList.toggle('error', !!(compiled && compiled.error));
    }
    if (compiled && compiled.error) {
      setSearchHint('invalid regex', true);
    } else {
      setSearchHint('');
    }

    for (const n of tree.querySelectorAll(':scope > .node')) filterNode(n, compiled);
  }

  let treeFullyLoaded = false;
  let loadingPromise = null;

  async function ensureLoadedRecursive(node) {
    if (!node.classList.contains('dir')) return;
    if (node.dataset.loaded !== '1') await loadChildren(node);
    const subs = node.querySelectorAll(':scope > .children > .node.dir');
    for (const s of subs) await ensureLoadedRecursive(s);
  }

  function ensureFullTreeLoaded() {
    if (treeFullyLoaded) return Promise.resolve();
    if (loadingPromise) return loadingPromise;
    loadingPromise = (async function () {
      setSearchHint('loading…');
      try {
        const roots = tree.querySelectorAll(':scope > .node.dir');
        for (const r of roots) await ensureLoadedRecursive(r);
        treeFullyLoaded = true;
      } catch (e) {
        setSearchHint('error', true);
      } finally {
        loadingPromise = null;
      }
    })();
    return loadingPromise;
  }

  const onSearchInput = debounce(async function () {
    const q = searchInput.value.trim();
    if (q) await ensureFullTreeLoaded();
    applySearch();
  }, 180);
  searchInput.addEventListener('input', onSearchInput);
  searchInput.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      searchInput.value = '';
      searchInput.dispatchEvent(new Event('input'));
    }
  });

  // ---- Regex toggle ----
  function setSearchMode(mode) {
    searchMode = mode;
    if (regexToggle) {
      regexToggle.classList.toggle('active', mode === 'regex');
      regexToggle.classList.remove('error');
    }
    try { localStorage.setItem('macula_search_mode', mode); } catch (e) {}
    searchInput.dispatchEvent(new Event('input'));
  }

  if (regexToggle) {
    regexToggle.addEventListener('click', function (e) {
      e.preventDefault();
      setSearchMode(searchMode === 'regex' ? 'substring' : 'regex');
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'r' || e.key === 'R')) {
      e.preventDefault();
      setSearchMode(searchMode === 'regex' ? 'substring' : 'regex');
    }
  });

  // ---- Toolbar buttons ----
  document.getElementById('expandAll').addEventListener('click', async function (e) {
    e.preventDefault();
    for (const n of tree.querySelectorAll(':scope > .node.dir')) await expandAll(n);
  });
  document.getElementById('collapseAll').addEventListener('click', function (e) {
    e.preventDefault();
    for (const n of tree.querySelectorAll(':scope > .node')) collapseAll(n);
  });

  document.querySelectorAll('.dropdown-toggle').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      const menu = btn.parentElement.querySelector('.dropdown-menu');
      if (!menu) return;
      const isOpen = menu.classList.contains('open');
      document.querySelectorAll('.dropdown-menu.open').forEach(m => m.classList.remove('open'));
      if (!isOpen) menu.classList.add('open');
    });
  });
  document.addEventListener('click', function () {
    document.querySelectorAll('.dropdown-menu.open').forEach(m => m.classList.remove('open'));
  });

  const helpModal = document.getElementById('helpModal');
  const helpOpen = document.getElementById('helpOpen');
  const helpClose = document.getElementById('helpClose');

  function openModal() { if (helpModal) helpModal.classList.remove('hidden'); }
  function closeModal() { if (helpModal) helpModal.classList.add('hidden'); }
  if (helpOpen) helpOpen.addEventListener('click', function (e) {
    e.preventDefault(); openModal();
  });
  if (helpClose) helpClose.addEventListener('click', closeModal);
  if (helpModal) helpModal.addEventListener('click', function (e) {
    if (e.target === helpModal) closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && helpModal && !helpModal.classList.contains('hidden')) {
      closeModal();
    }
  });

  document.querySelectorAll('.copy-btn').forEach(function (btn) {
    btn.addEventListener('click', async function (e) {
      e.stopPropagation();
      const targetId = btn.getAttribute('data-target');
      const el = document.getElementById(targetId);
      if (!el) return;
      const text = el.textContent;
      let ok = false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text); ok = true;
        }
      } catch (err) {}
      if (!ok) {
        const range = document.createRange();
        range.selectNodeContents(el);
        const sel = window.getSelection();
        sel.removeAllRanges(); sel.addRange(range);
        try { document.execCommand('copy'); ok = true; } catch (err) {}
        sel.removeAllRanges();
      }
      const original = btn.textContent;
      btn.textContent = ok ? 'copied' : 'copy';
      btn.classList.toggle('copied', ok);
      setTimeout(function () {
        btn.textContent = original;
        btn.classList.remove('copied');
      }, 1200);
    });
  });

  if (UPLOADS_ENABLED) {
    const uploadToggles = document.querySelectorAll('.upload-toggle');
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const uploadStatus = document.getElementById('uploadStatus');

    function setStatus(msg, cls) {
      if (!uploadStatus) return;
      uploadStatus.textContent = msg;
      uploadStatus.className = 'upload-status' + (cls ? ' ' + cls : '');
    }

    uploadToggles.forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (!dropzone) return;
        const willShow = dropzone.classList.contains('hidden');
        dropzone.classList.toggle('hidden');
        uploadToggles.forEach(b => b.classList.toggle('active', willShow));
        if (willShow) {
          setStatus('Ready — drop files or click to select', '');
          dropzone.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    });

    if (dropzone) {
      dropzone.addEventListener('click', function (e) {
        if (e.target.tagName === 'CODE') return;
        if (fileInput) fileInput.click();
      });
      ['dragenter', 'dragover'].forEach(ev => {
        dropzone.addEventListener(ev, e => {
          e.preventDefault(); e.stopPropagation();
          dropzone.classList.add('dragover');
        });
      });
      ['dragleave', 'drop'].forEach(ev => {
        dropzone.addEventListener(ev, e => {
          e.preventDefault(); e.stopPropagation();
          dropzone.classList.remove('dragover');
        });
      });
      dropzone.addEventListener('drop', function (e) {
        if (e.dataTransfer && e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
      });
    }
    if (fileInput) {
      fileInput.addEventListener('change', function () {
        if (fileInput.files.length) uploadFiles(fileInput.files);
      });
    }

    function uploadFiles(files) {
      if (!files || !files.length) return;
      const fd = new FormData();
      for (const f of files) fd.append('file', f, f.name);
      const label = files.length === 1 ? files[0].name : files.length + ' files';
      setStatus('Uploading ' + label + '…', 'busy');

      const xhr = new XMLHttpRequest();
      xhr.open('POST', UPLOAD_TARGET);
      xhr.upload.addEventListener('progress', function (e) {
        if (e.lengthComputable) {
          const pct = Math.round(100 * e.loaded / e.total);
          setStatus('Uploading ' + label + ' — ' + pct + '%', 'busy');
        }
      });
      xhr.addEventListener('load', function () {
        if (xhr.status >= 200 && xhr.status < 300) {
          let names = label;
          try {
            const data = JSON.parse(xhr.responseText);
            if (data.saved && data.saved.length)
              names = data.saved.map(s => s.name).join(', ');
          } catch (err) {}
          setStatus('\u2713 Uploaded: ' + names + ' — refreshing…', 'ok');
          if (fileInput) fileInput.value = '';
          setTimeout(function () { window.location.reload(); }, 700);
        } else {
          let msg = xhr.responseText;
          try { msg = JSON.parse(xhr.responseText).error || msg; } catch (err) {}
          setStatus('\u2717 Error ' + xhr.status + ': ' + msg, 'err');
        }
      });
      xhr.addEventListener('error', () => setStatus('\u2717 Network error', 'err'));
      xhr.send(fd);
    }
  }

  // ---- Auto-refresh (fingerprint-based) ----
  //
  // The server computes a SHA1 over every entry under the current path
  // (or over every mount in the virtual root) and exposes it at
  // `?format=json&stat=1`. We poll that cheap endpoint and reload when
  // the fingerprint changes, so ANY change anywhere in the subtree —
  // add, remove, rename, modify — is detected.
  const refreshBtn = document.getElementById('refreshBtn');
  const autoBtn    = document.getElementById('autoRefresh');
  const AUTO_MS    = 15000;
  const STAT_URL   = window.MACULA_STAT_URL || '';
  const INITIAL_FP = window.MACULA_FINGERPRINT || '';
  let autoTimer    = null;

  function pollOnce() {
    if (!STAT_URL) return;
    fetch(STAT_URL, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d || typeof d.fingerprint !== 'string') return;
        if (d.fingerprint !== INITIAL_FP) {
          window.location.reload();
        }
      })
      .catch(() => {});
  }

  function setAuto(on) {
    if (!autoBtn) return;
    autoBtn.classList.toggle('active', on);
    autoBtn.title = on
      ? 'Auto-refresh: ON (polls every ' + (AUTO_MS / 1000) + 's)'
      : 'Auto-refresh: OFF';
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
    if (!on) return;
    autoTimer = setInterval(pollOnce, AUTO_MS);
  }

  if (refreshBtn) refreshBtn.addEventListener('click', () => window.location.reload());
  if (autoBtn) {
    let saved = false;
    try { saved = localStorage.getItem('macula_auto') === '1'; } catch (e) {}
    setAuto(saved);
    autoBtn.addEventListener('click', function () {
      const now = !autoBtn.classList.contains('active');
      try { localStorage.setItem('macula_auto', now ? '1' : '0'); } catch (e) {}
      setAuto(now);
    });
  }
})();