// Start één Homey-flow op basis van het id (eerste argument).
// Geeft exitcode 0 en "success" bij succes, anders exitcode 1.
import { HomeyAPI } from 'homey-api';
import { loadHomeyConfig } from './homey_config.js';

const flowId = process.argv[2];
if (!flowId) {
  console.error('Geen flow-id meegegeven.');
  process.exit(1);
}

const { address, token } = loadHomeyConfig();

try {
  const homeyApi = await HomeyAPI.createLocalAPI({ address, token });
  await homeyApi.flow.triggerFlow({ uri: 'homey:manager:flow', id: flowId });
  process.stdout.write('success\n');
  process.exit(0);
} catch (error) {
  console.error('Flow starten mislukt:', error.message);
  process.exit(1);
}
