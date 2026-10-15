// Gedeelde configuratie voor de Homey-scripts.
// De skill geeft adres en token mee via de omgeving (HOMEY_ADDRESS / HOMEY_TOKEN).
// Zonder omgevingsvariabelen wordt config.json in de gebruikersmap gelezen.
import fs from 'fs';
import os from 'os';
import path from 'path';

export function loadHomeyConfig() {
  let address = process.env.HOMEY_ADDRESS;
  let token = process.env.HOMEY_TOKEN;

  if (!address || !token) {
    const dir = process.env.HOMEYFLOW_CONFIG_DIR
      || path.join(os.homedir(), '.config', 'ovos_skill_homeyflowtrigger');
    try {
      const config = JSON.parse(fs.readFileSync(path.join(dir, 'config.json'), 'utf8'));
      address = address || (config.homey && config.homey.address);
      token = token || (config.homey && config.homey.token);
    } catch (error) {
      console.error(`config.json kon niet gelezen worden: ${error.message}`);
    }
  }

  if (!address || !token) {
    console.error('Homey-adres of token ontbreekt.');
    process.exit(1);
  }
  return { address, token };
}
