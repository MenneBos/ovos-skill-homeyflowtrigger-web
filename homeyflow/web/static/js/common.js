// Gedeelde hulpfuncties: API-aanroepen, meldingen, thema en statuslabel.
(function () {
  'use strict';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  // Kleine DOM-bouwer; gebruikt altijd textContent, dus nooit ruwe HTML uit Homey of de gebruiker.
  function h(tag, attrs) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value === false || value === null || value === undefined) return;
      if (key === 'class') el.className = value;
      else if (key === 'text') el.textContent = value;
      else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
      else if (key === 'value') el.value = value;
      else if (key === 'checked' || key === 'disabled') el[key] = !!value;
      else el.setAttribute(key, value === true ? '' : value);
    });
    for (let i = 2; i < arguments.length; i++) {
      const child = arguments[i];
      if (child === null || child === undefined || child === false) continue;
      el.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return el;
  }

  async function api(path, options) {
    const opts = Object.assign({ method: 'GET' }, options || {});
    const init = { method: opts.method, headers: {} };
    if (opts.method !== 'GET') {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body === undefined ? {} : opts.body);
    }
    let response;
    try {
      response = await fetch(path, init);
    } catch (err) {
      const e = new Error('Server niet bereikbaar.');
      e.network = true;
      throw e;
    }
    let data = null;
    try { data = await response.json(); } catch (err) { /* geen JSON */ }
    if (!response.ok) {
      const e = new Error((data && data.error) || ('Fout ' + response.status));
      e.status = response.status;
      e.data = data;
      throw e;
    }
    return data;
  }

  function toast(message, kind) {
    const box = $('#toasts');
    if (!box) return;
    const el = h('div', { class: 'toast' + (kind === 'error' ? ' error' : ''), role: 'status', text: message });
    box.append(el);
    setTimeout(() => el.remove(), kind === 'error' ? 7000 : 3500);
  }

  function formatTime(epoch) {
    if (!epoch) return '–';
    return new Date(epoch * 1000).toLocaleString('nl-NL', { dateStyle: 'medium', timeStyle: 'short' });
  }

  // Thema
  const themeButton = $('#theme-toggle');
  if (themeButton) {
    themeButton.addEventListener('click', () => {
      const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('hf-theme', next); } catch (e) { /* niet erg */ }
    });
  }

  // Statuslabel rechtsboven + gebeurtenis voor de pagina's
  const pill = $('#homey-pill');
  let latest = null;

  function updatePill(status) {
    if (!pill) return;
    let state = 'bad';
    let text = 'Server niet bereikbaar';
    if (status) {
      const homey = status.homey || {};
      if (!homey.configured) { state = 'warn'; text = 'Homey niet ingesteld'; }
      else if (homey.reachable) { state = 'ok'; text = 'Homey bereikbaar'; }
      else { state = 'bad'; text = 'Homey niet bereikbaar'; }
    }
    pill.dataset.state = state;
    pill.querySelector('span').textContent = text;
  }

  async function refreshStatus() {
    try { latest = await api('/api/status'); } catch (err) { latest = null; }
    updatePill(latest);
    document.dispatchEvent(new CustomEvent('hf:status', { detail: latest }));
    return latest;
  }

  window.HF = { $, $$, h, api, toast, formatTime, refreshStatus, get status() { return latest; } };
  refreshStatus();
  setInterval(refreshStatus, 15000);
})();
