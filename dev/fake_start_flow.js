// Nep-versie van nodejs/start_flow.js voor dev en tests.
const id = process.argv[2];
if (!id) { console.error('Geen flow-id meegegeven.'); process.exit(1); }
if (id === 'fail' || process.env.FAKE_MODE === 'fail') { console.error('Flow starten mislukt: nep-fout'); process.exit(1); }
if (process.env.FAKE_MODE === 'hang') { setTimeout(() => {}, 600000); } else {
  if (process.env.FAKE_LOG) require('fs').appendFileSync(process.env.FAKE_LOG, id + '\n');
  console.log('success');
}
