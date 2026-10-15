// Dashboard: kaarten en feiten vullen vanuit /api/status.
(function () {
  'use strict';
  const { $, h, formatTime } = window.HF;

  function set(id, text) { const el = $(id); if (el) el.textContent = text; }

  function render(status) {
    if (!status) {
      set('#st-flows', '–'); set('#st-sentences', '–'); set('#st-learned', '–'); set('#st-homey', '–');
      return;
    }
    const training = status.training || {};
    const homey = status.homey || {};
    const skill = status.skill || {};

    set('#st-flows', String(status.flows));
    const empty = status.flows - status.flows_with_sentences;
    set('#st-flows-note', empty > 0 ? empty + ' zonder zinnen' : 'alle flows hebben zinnen');
    set('#st-sentences', String(status.sentences));

    if (training.state === 'running' || training.state === 'restarting') {
      set('#st-learned', 'Bezig…'); set('#st-learned-note', training.step || '');
    } else if (status.flows_with_sentences === 0) {
      set('#st-learned', '–'); set('#st-learned-note', 'nog niets om te leren');
    } else if (training.dirty) {
      set('#st-learned', 'Nee'); set('#st-learned-note', 'wijzigingen wachten op leren');
    } else {
      set('#st-learned', 'Ja'); set('#st-learned-note', 'laatst: ' + formatTime(training.learned_at));
    }

    if (!homey.configured) { set('#st-homey', 'Niet ingesteld'); set('#st-homey-note', 'vul adres en token in config.json in'); }
    else if (homey.reachable) { set('#st-homey', 'Bereikbaar'); set('#st-homey-note', ''); }
    else { set('#st-homey', 'Onbereikbaar'); set('#st-homey-note', 'controleer adres en netwerk'); }

    const facts = $('#facts');
    facts.replaceChildren();
    const rows = [
      ['Skill', skill.running ? 'actief' : (skill.detail || 'niet actief')],
      ['Omgeving', skill.mode || '–'],
      ['Taal', skill.language || (status.web && status.web.language) || '–'],
      ['Intents geregistreerd', skill.registered_intents !== undefined ? String(skill.registered_intents) : '–'],
      ['Leermodus', training.mode === 'restart' ? 'skill herstarten' : 'live (zonder herstart)'],
      ['Webserver', 'poort ' + ((status.web && status.web.port) || '–')],
      ['Versie', status.version],
    ];
    rows.forEach(([label, value]) => facts.append(h('dt', { text: label }), h('dd', { text: value })));
  }

  document.addEventListener('hf:status', (event) => render(event.detail));
  if (window.HF.status) render(window.HF.status);
})();
