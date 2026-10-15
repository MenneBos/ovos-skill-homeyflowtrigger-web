// Haalt de flows uit Homey op en filtert op een zoekterm in de naam.
// Uitvoer (stdout): één regel JSON, een lijst met {id, name, enabled}.
// Alles wat geen JSON is gaat naar stderr.
import { HomeyAPI } from 'homey-api';
import { loadHomeyConfig } from './homey_config.js';

const searchString = (process.argv[2] || '').toLowerCase();
const { address, token } = loadHomeyConfig();

try {
  const homeyApi = await HomeyAPI.createLocalAPI({ address, token });
  const flows = await homeyApi.flow.getFlows();

  const result = Object.values(flows)
    .filter((flow) => flow.name.toLowerCase().includes(searchString))
    .map((flow) => ({ id: flow.id, name: flow.name, enabled: flow.enabled !== false }));

  process.stdout.write(JSON.stringify(result) + '\n');
  process.exit(0);
} catch (error) {
  console.error('Een fout in het verkrijgen van de flows:', error.message);
  process.exit(1);
}
