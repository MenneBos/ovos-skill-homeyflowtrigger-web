// Nep-versie van nodejs/get_flow.js voor dev en tests (geen Homey nodig).
const search = (process.argv[2] || '').toLowerCase();
const mode = process.env.FAKE_MODE || '';
if (mode === 'fail') { console.error('Een fout in het verkrijgen van de flows: nep-fout'); process.exit(1); }
if (mode === 'hang') { setTimeout(() => {}, 600000); } else {
  const flows = [
    { id: 'f1-kantoor-in', name: 'Kantoor: check in', enabled: true },
    { id: 'f2-kantoor-uit', name: 'Kantoor: check out', enabled: true },
    { id: 'f3-koffie', name: 'Koffie zetten', enabled: true },
    { id: 'f4-gordijnen', name: 'Gordijnen open (slaapkamer)', enabled: true },
    { id: 'f5-nacht', name: 'Goedenacht', enabled: false },
    { id: 'f6-<script>', name: '<b>Rare naam</b> & "quotes"', enabled: true },
  ].filter((f) => f.name.toLowerCase().includes(search));
  if (mode === 'noise') console.log('ruis voor de JSON');
  if (mode === 'old') {
    const old = {}; flows.forEach((f) => { old[f.name] = { id: f.id, sentences: [] }; });
    console.log(JSON.stringify(old));
  } else {
    console.log(JSON.stringify(flows));
  }
}
