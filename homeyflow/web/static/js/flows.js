// Flows-pagina: lijst links, zinnen rechts, flows toevoegen, intents leren en testen.
(function () {
  'use strict';
  const { $, h, api, toast, formatTime } = window.HF;

  const state = { flows: [], dirty: false, selected: null, filter: '' };

  // ---------- dialoog-hulpjes ----------
  function openDialog(dlg) { if (!dlg.open) dlg.showModal(); }
  function closeDialog(dlg) { if (dlg.open) dlg.close(); }

  function confirmDialog(opts) {
    const dlg = $('#dlg-confirm');
    $('#confirm-title').textContent = opts.title;
    $('#confirm-body').textContent = opts.body;
    const ok = $('#confirm-ok');
    ok.textContent = opts.okText || 'Doorgaan';
    ok.className = 'btn ' + (opts.danger ? 'btn-danger' : 'btn-primary');
    return new Promise((resolve) => {
      const done = (value) => {
        ok.removeEventListener('click', onOk);
        $('#confirm-cancel').removeEventListener('click', onCancel);
        dlg.removeEventListener('close', onClose);
        closeDialog(dlg);
        resolve(value);
      };
      const onOk = () => done(true);
      const onCancel = () => done(false);
      const onClose = () => done(false);
      ok.addEventListener('click', onOk);
      $('#confirm-cancel').addEventListener('click', onCancel);
      dlg.addEventListener('close', onClose);
      openDialog(dlg);
    });
  }

  // ---------- lijst en detail ----------
  const selectedFlow = () => state.flows.find((f) => f.key === state.selected) || null;

  function renderList() {
    const list = $('#flow-list');
    const needle = state.filter.trim().toLowerCase();
    const shown = state.flows.filter((f) => !needle || f.title.toLowerCase().includes(needle) || f.key.includes(needle));
    $('#flow-count').textContent = String(state.flows.length);
    list.replaceChildren();
    if (!shown.length) {
      list.append(h('li', { class: 'list-empty', text: state.flows.length ? 'Geen flows gevonden voor dit filter.' : 'Nog geen flows. Klik op + om er een toe te voegen.' }));
      return;
    }
    shown.forEach((flow) => {
      const count = flow.sentences.length;
      const button = h('button', {
        type: 'button', class: 'flow-item' + (flow.key === state.selected ? ' active' : ''),
        title: flow.title, onclick: () => select(flow.key),
      }, h('span', { class: 'name', text: flow.title }),
         h('span', { class: 'badge' + (count === 0 ? ' warn' : ''), text: String(count) }));
      list.append(h('li', null, button));
    });
  }

  function currentInputs() {
    return Array.from(document.querySelectorAll('#sentence-list input')).map((i) => i.value);
  }

  function renderSentences(flow) {
    const list = $('#sentence-list');
    list.replaceChildren();
    if (!flow.sentences.length) {
      list.append(h('li', { class: 'sentence-empty', text: 'Deze flow heeft nog geen zinnen en wordt dus niet geleerd.' }));
    }
    flow.sentences.forEach((sentence, index) => {
      const input = h('input', { type: 'text', value: sentence, maxlength: '200', 'aria-label': 'Zin ' + (index + 1) });
      input.addEventListener('change', () => saveSentences(flow.key, currentInputs()));
      const remove = h('button', {
        type: 'button', class: 'btn btn-danger', title: 'Zin verwijderen', 'aria-label': 'Zin verwijderen',
        onclick: () => saveSentences(flow.key, currentInputs().filter((_, i) => i !== index)),
      }, '✕');
      list.append(h('li', { class: 'sentence-row' }, input, remove));
    });
  }

  function renderDetail() {
    const flow = selectedFlow();
    $('#detail-empty').hidden = !!flow;
    $('#detail-body').hidden = !flow;
    if (!flow) return;
    $('#d-title').textContent = flow.title;
    $('#d-id').textContent = flow.id || '(geen Homey-id)';
    renderSentences(flow);
  }

  function select(key) {
    state.selected = key;
    try { history.replaceState(null, '', '#' + encodeURIComponent(key)); } catch (e) { /* niet erg */ }
    renderList();
    renderDetail();
  }

  function renderLearnBar() {
    const text = $('#learn-text');
    const dot = $('#learn-dot');
    const status = window.HF.status;
    const training = (status && status.training) || {};
    const withSentences = state.flows.filter((f) => f.sentences.length).length;
    if (training.state === 'running' || training.state === 'restarting') {
      dot.dataset.state = 'busy'; text.textContent = 'Bezig met leren…';
    } else if (!withSentences) {
      dot.dataset.state = ''; text.textContent = 'Voeg zinnen toe om te kunnen leren.';
    } else if (state.dirty) {
      dot.dataset.state = 'warn'; text.textContent = 'Er zijn wijzigingen die nog niet geleerd zijn.';
    } else {
      dot.dataset.state = 'ok';
      text.textContent = 'Alles is geleerd' + (training.learned_at ? ' (' + formatTime(training.learned_at) + ').' : '.');
    }
    $('#btn-learn').disabled = !withSentences || training.state === 'running' || training.state === 'restarting';
  }

  function applyOverview(data) {
    state.flows = data.flows;
    state.dirty = data.dirty;
    if (state.selected && !selectedFlow()) state.selected = null;
    renderList();
    renderDetail();
    renderLearnBar();
  }

  async function load() {
    try {
      applyOverview(await api('/api/flows'));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function saveSentences(key, sentences) {
    try {
      const data = await api('/api/flows/' + encodeURIComponent(key), { method: 'PUT', body: { sentences } });
      const index = state.flows.findIndex((f) => f.key === key);
      if (index >= 0) state.flows[index] = data.flow;
      state.dirty = data.dirty;
      renderList();
      renderLearnBar();
      // Alleen opnieuw tekenen als de server iets heeft opgeschoond (anders raakt de cursor kwijt).
      if (JSON.stringify(currentInputs()) !== JSON.stringify(data.flow.sentences) || state.selected !== key) renderDetail();
      toast('Opgeslagen');
    } catch (err) {
      toast(err.message, 'error');
      await load();
    }
  }

  $('#sentence-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const flow = selectedFlow();
    const input = $('#sentence-input');
    const value = input.value.trim();
    if (!flow || !value) return;
    input.value = '';
    saveSentences(flow.key, currentInputs().concat([value])).then(() => input.focus());
  });

  $('#flow-filter').addEventListener('input', (event) => { state.filter = event.target.value; renderList(); });

  $('#btn-delete').addEventListener('click', async () => {
    const flow = selectedFlow();
    if (!flow) return;
    const ok = await confirmDialog({
      title: 'Flow verwijderen?', danger: true, okText: 'Verwijderen',
      body: '“' + flow.title + '” en alle bijbehorende zinnen worden uit de lijst gehaald. De flow in Homey blijft bestaan.',
    });
    if (!ok) return;
    try {
      applyOverview(await api('/api/flows/' + encodeURIComponent(flow.key), { method: 'DELETE' }));
      toast('Flow verwijderd');
    } catch (err) { toast(err.message, 'error'); }
  });

  // ---------- flow toevoegen vanuit Homey ----------
  const add = { results: [], picked: new Set() };

  function renderAddResults() {
    const list = $('#add-results');
    list.replaceChildren();
    add.results.forEach((flow) => {
      const checkbox = h('input', { type: 'checkbox', checked: add.picked.has(flow.id), disabled: flow.added });
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) add.picked.add(flow.id); else add.picked.delete(flow.id);
        renderAddFooter();
      });
      const label = h('label', { class: 'pick' + (flow.added ? ' is-added' : '') },
        checkbox, h('span', { class: 'name', text: flow.name }),
        flow.added ? h('span', { class: 'badge', text: 'al toegevoegd' }) : null,
        flow.enabled === false ? h('span', { class: 'badge warn', text: 'uitgeschakeld' }) : null);
      list.append(h('li', null, label));
    });
    renderAddFooter();
  }

  function renderAddFooter() {
    const addable = add.results.filter((f) => !f.added);
    const confirm = $('#add-confirm');
    confirm.disabled = add.picked.size === 0;
    confirm.textContent = add.picked.size ? 'Toevoegen (' + add.picked.size + ')' : 'Toevoegen';
    const all = $('#add-select-all');
    all.hidden = addable.length === 0;
    all.textContent = add.picked.size === addable.length ? 'Selectie wissen' : 'Alles selecteren';
  }

  async function searchHomey() {
    const note = $('#add-note');
    const button = $('#add-search');
    button.disabled = true;
    note.textContent = 'Zoeken in Homey…';
    add.results = []; add.picked.clear(); renderAddResults();
    try {
      const data = await api('/api/homey/flows?q=' + encodeURIComponent($('#add-query').value.trim()));
      add.results = data.flows;
      note.textContent = data.flows.length
        ? data.flows.length + ' flow(s) gevonden. Vink de flows aan die je wilt toevoegen.'
        : 'Geen flows gevonden' + (data.query ? ' voor “' + data.query + '”.' : '.');
    } catch (err) {
      note.textContent = 'Zoeken mislukt: ' + err.message;
    } finally {
      button.disabled = false;
      renderAddResults();
    }
  }

  $('#btn-add').addEventListener('click', () => {
    add.results = []; add.picked.clear();
    $('#add-query').value = '';
    $('#add-note').textContent = 'Typ een zoekterm, of laat het veld leeg om alle flows te tonen, en klik op Zoeken.';
    renderAddResults();
    openDialog($('#dlg-add'));
    $('#add-query').focus();
  });
  $('#add-form').addEventListener('submit', (event) => { event.preventDefault(); searchHomey(); });
  $('#add-search').addEventListener('click', searchHomey);
  $('#add-cancel').addEventListener('click', () => closeDialog($('#dlg-add')));
  $('#add-select-all').addEventListener('click', () => {
    const addable = add.results.filter((f) => !f.added);
    if (add.picked.size === addable.length) add.picked.clear();
    else addable.forEach((f) => add.picked.add(f.id));
    renderAddResults();
  });
  $('#add-confirm').addEventListener('click', async () => {
    const flows = add.results.filter((f) => add.picked.has(f.id)).map((f) => ({ id: f.id, name: f.name }));
    if (!flows.length) return;
    try {
      const data = await api('/api/flows', { method: 'POST', body: { flows } });
      closeDialog($('#dlg-add'));
      applyOverview(data);
      if (data.added.length) select(data.added[0]);
      toast(data.added.length + ' flow(s) toegevoegd. Voeg zinnen toe en klik op Intents leren.');
    } catch (err) { toast(err.message, 'error'); }
  });

  // ---------- intents leren ----------
  let learning = false;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function showLearnView(view) {
    $('#learn-confirm').hidden = view !== 'confirm';
    $('#learn-progress').hidden = view !== 'progress';
  }

  function renderSteps(log) {
    const steps = $('#learn-steps');
    steps.replaceChildren();
    (log || []).forEach((entry) => steps.append(h('li', { text: entry.msg })));
    steps.scrollTop = steps.scrollHeight;
  }

  function finishLearn(kind, title, message) {
    learning = false;
    const spinner = $('#learn-spinner');
    spinner.className = 'spinner ' + (kind === 'ok' ? 'done' : 'fail');
    $('#learn-title').textContent = title;
    const error = $('#learn-error');
    error.hidden = !message;
    error.className = 'notice ' + (kind === 'ok' ? 'notice-ok' : 'notice-error');
    error.textContent = message || '';
    $('#learn-close').hidden = false;
    $('#learn-test').hidden = kind !== 'ok';
  }

  async function waitForServer() {
    // Na een herstart eerst wachten tot de server even weg is geweest en weer antwoordt.
    let wentDown = false;
    const until = Date.now() + 120000;
    while (Date.now() < until) {
      try {
        const response = await fetch('/healthz', { cache: 'no-store' });
        if (response.ok && (wentDown || Date.now() > until - 100000)) return true;
      } catch (err) { wentDown = true; }
      await sleep(1500);
    }
    return false;
  }

  async function pollLearn() {
    for (;;) {
      let status;
      try {
        status = await api('/api/learn');
      } catch (err) {
        await sleep(1000);
        continue;
      }
      renderSteps(status.log);
      if (status.state === 'running') {
        $('#learn-title').textContent = status.step || 'Bezig…';
      } else if (status.state === 'restarting') {
        $('#learn-title').textContent = 'Skill wordt herstart…';
        const back = await waitForServer();
        if (back) {
          finishLearn('ok', 'Klaar', 'De skill is herstart en heeft de zinnen geleerd.');
          await refreshAll();
        } else {
          finishLearn('fail', 'Herstart duurt lang', 'De server antwoordt nog niet. Controleer de container en laad de pagina opnieuw.');
        }
        return;
      } else if (status.state === 'done') {
        finishLearn('ok', 'Klaar', status.message);
        await refreshAll();
        return;
      } else if (status.state === 'error') {
        finishLearn('fail', 'Leren mislukt', status.message);
        await refreshAll();
        return;
      }
      await sleep(800);
    }
  }

  async function refreshAll() {
    await window.HF.refreshStatus();
    await load();
  }

  $('#btn-learn').addEventListener('click', () => {
    showLearnView('confirm');
    openDialog($('#dlg-learn'));
  });
  $('#learn-cancel').addEventListener('click', () => closeDialog($('#dlg-learn')));
  $('#learn-close').addEventListener('click', () => closeDialog($('#dlg-learn')));
  $('#dlg-learn').addEventListener('cancel', (event) => { if (learning) event.preventDefault(); });
  $('#learn-go').addEventListener('click', async () => {
    try {
      await api('/api/learn', { method: 'POST', body: { confirm: true } });
    } catch (err) {
      if (err.status !== 409) { toast(err.message, 'error'); return; }
    }
    learning = true;
    showLearnView('progress');
    $('#learn-spinner').className = 'spinner';
    $('#learn-title').textContent = 'Bezig…';
    $('#learn-error').hidden = true;
    $('#learn-close').hidden = true;
    $('#learn-test').hidden = true;
    renderSteps([]);
    pollLearn();
  });
  $('#learn-test').addEventListener('click', () => { closeDialog($('#dlg-learn')); openTest(); });

  // ---------- testen ----------
  function pct(value) { return Math.round(value * 100) + '%'; }

  function renderTest(utterance, data) {
    const box = $('#test-result');
    box.hidden = false;
    box.replaceChildren();
    const fuzzy = data.fuzzy || {};
    const padatious = data.padatious;

    // Spraakherkenning (Padatious)
    const heard = h('div', { class: 'result-card' }, h('h3', { text: 'Spraakherkenning (Padatious)' }));
    if (!padatious || !padatious.available) {
      heard.append(h('div', { class: 'muted', text: 'Niet beschikbaar: de intent-service gaf geen antwoord.' }));
    } else if (!padatious.intent) {
      heard.append(h('div', { class: 'big', text: 'Geen intent herkend' }),
        h('div', { class: 'muted small', text: 'Heb je al op Intents leren geklikt na je laatste wijziging?' }));
    } else {
      const flow = state.flows.find((f) => f.key === padatious.flow);
      heard.append(h('div', { class: 'big', text: flow ? flow.title : padatious.intent }),
        h('div', { class: 'muted small', text: 'zekerheid ' + (padatious.confidence != null ? pct(padatious.confidence) : 'onbekend') }));
    }
    box.append(heard);

    // Gekozen flow (fuzzy)
    const chosen = h('div', { class: 'result-card' }, h('h3', { text: 'Gekozen flow (zoals de skill kiest)' }));
    if (fuzzy.status === 'no_match') {
      chosen.append(h('div', { class: 'big', text: 'Geen flow gevonden' }),
        h('div', { class: 'muted small', text: 'Geen zin komt voor minstens ' + pct(fuzzy.cutoff || 0.6) + ' overeen.' }));
    } else {
      chosen.append(h('div', { class: 'big', text: fuzzy.title }),
        h('div', { class: 'muted small', text: 'overeenkomst met “' + fuzzy.sentence + '”: ' + pct(fuzzy.score) }));
      if (fuzzy.status === 'no_id') chosen.append(h('div', { class: 'sentence-empty', text: 'Deze flow heeft geen Homey-id en kan niet gestart worden.' }));
    }
    box.append(chosen);

    if (padatious && padatious.flow && fuzzy.flow && padatious.flow !== fuzzy.flow) {
      box.append(h('p', { class: 'notice notice-error', text: 'Let op: de spraakherkenning wijst een andere flow aan dan de skill kiest. De skill gebruikt de keuze hierboven.' }));
    }

    if (fuzzy.status === 'matched') {
      const confirmBox = h('div', { class: 'confirm-run', hidden: true },
        h('p', { text: 'Dit start de echte flow “' + fuzzy.title + '” in Homey.' }),
        h('div', { class: 'row' },
          h('button', { type: 'button', class: 'btn btn-primary', onclick: () => runFlow(utterance, box, confirmBox) }, 'Ja, start de flow'),
          h('button', { type: 'button', class: 'btn', onclick: () => { confirmBox.hidden = true; startButton.hidden = false; } }, 'Annuleren')));
      const startButton = h('button', { type: 'button', class: 'btn', onclick: () => { confirmBox.hidden = false; startButton.hidden = true; } },
        'Start deze flow in Homey…');
      box.append(startButton, confirmBox);
    }
  }

  async function runFlow(utterance, box, confirmBox) {
    confirmBox.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    try {
      const data = await api('/api/test', { method: 'POST', body: { utterance, run: true, confirm: true } });
      const result = data.fuzzy || {};
      confirmBox.hidden = true;
      box.append(result.status === 'started'
        ? h('p', { class: 'notice notice-ok', text: 'Flow “' + result.title + '” is gestart.' })
        : h('p', { class: 'notice notice-error', text: result.error || 'De flow kon niet gestart worden.' }));
    } catch (err) {
      confirmBox.hidden = true;
      box.append(h('p', { class: 'notice notice-error', text: err.message }));
    }
  }

  function openTest() {
    $('#test-result').hidden = true;
    openDialog($('#dlg-test'));
    $('#test-input').focus();
  }
  $('#btn-test').addEventListener('click', openTest);
  $('#test-close').addEventListener('click', () => closeDialog($('#dlg-test')));
  $('#test-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const utterance = $('#test-input').value.trim();
    if (!utterance) return;
    try {
      renderTest(utterance, await api('/api/test', { method: 'POST', body: { utterance } }));
    } catch (err) { toast(err.message, 'error'); }
  });

  // ---------- start ----------
  document.addEventListener('hf:status', renderLearnBar);
  const initial = decodeURIComponent((location.hash || '').slice(1));
  load().then(() => {
    if (initial && state.flows.some((f) => f.key === initial)) select(initial);
    else if (state.flows.length) select(state.flows[0].key);
  });
})();
