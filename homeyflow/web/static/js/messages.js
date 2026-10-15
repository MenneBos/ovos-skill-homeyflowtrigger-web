// Meldingen: gesproken teksten bekijken, aanpassen, beluisteren en opslaan.
(function () {
  'use strict';
  const { $, h, api, toast } = window.HF;

  let items = [];     // laatste toestand van de server
  let inputs = {};    // sleutel -> invoerveld

  function currentValue(item) { return inputs[item.key].value; }

  function isChanged(item) { return currentValue(item) !== item.value; }

  function refreshRow(item) {
    const row = inputs[item.key].closest('.msg-row');
    const value = currentValue(item);
    row.classList.toggle('changed', isChanged(item));
    const tag = row.querySelector('.msg-tag');
    if (isChanged(item)) tag.textContent = 'niet opgeslagen';
    else if (item.custom) tag.textContent = 'aangepast';
    else tag.textContent = 'standaard';
    row.querySelector('.msg-default').disabled = value === item.default;
    $('#msg-save').disabled = !items.some(isChanged);
  }

  function row(item) {
    const input = h('input', { type: 'text', id: 'msg-' + item.key, value: item.value, maxlength: '200',
                               'aria-label': item.label, autocomplete: 'off' });
    inputs[item.key] = input;
    input.addEventListener('input', () => refreshRow(item));

    const hint = item.placeholders.length
      ? 'Invulvelden: ' + item.placeholders.map((p) => '{' + p + '}').join(', ')
      : 'Geen invulvelden';

    const speak = h('button', { type: 'button', class: 'btn', text: 'Afspelen', onclick: async () => {
      speak.disabled = true;
      try {
        const result = await api('/api/messages/speak', { method: 'POST', body: { key: item.key, text: input.value } });
        toast('Uitgesproken: ' + result.spoken);
      } catch (err) { toast(err.message, 'error'); }
      speak.disabled = false;
    } });
    const reset = h('button', { type: 'button', class: 'btn btn-ghost msg-default', text: 'Standaard', onclick: () => {
      input.value = item.default; refreshRow(item);
    } });

    return h('li', { class: 'msg-row' },
      h('div', { class: 'msg-head' },
        h('label', { for: 'msg-' + item.key, class: 'msg-label', text: item.label }),
        h('span', { class: 'msg-tag muted small' })),
      h('p', { class: 'muted small', text: item.help }),
      h('div', { class: 'msg-edit' }, input, speak, reset),
      h('p', { class: 'muted small', text: hint + (item.allow_empty ? ' · leeg = niets zeggen' : '') }));
  }

  function render(data) {
    items = data.messages;
    inputs = {};
    const list = $('#msg-list');
    list.replaceChildren(...items.map(row));
    items.forEach(refreshRow);
  }

  async function load() {
    try { render(await api('/api/messages')); }
    catch (err) { $('#msg-list').replaceChildren(h('li', { class: 'notice notice-error', text: err.message })); }
  }

  async function save(payload, okText) {
    try {
      render(await api('/api/messages', { method: 'PUT', body: { messages: payload } }));
      toast(okText);
    } catch (err) { toast(err.message, 'error'); }
  }

  $('#msg-save').addEventListener('click', () => {
    const payload = {};
    items.filter(isChanged).forEach((item) => {
      const value = currentValue(item);
      payload[item.key] = value === item.default ? null : value;
    });
    save(payload, 'Meldingen opgeslagen.');
  });

  const dialog = $('#dlg-reset');
  $('#msg-reset-all').addEventListener('click', () => { if (!dialog.open) dialog.showModal(); });
  $('#reset-cancel').addEventListener('click', () => dialog.close());
  $('#reset-ok').addEventListener('click', () => {
    dialog.close();
    const payload = {};
    items.forEach((item) => { payload[item.key] = null; });
    save(payload, 'Standaardmeldingen teruggezet.');
  });

  load();
})();
