"""Praat met Homey via de Node.js-scripts (homey-api)."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import List, Optional

from .config import Settings
from .log import get_logger

LOG = get_logger()


class HomeyError(Exception):
    """Fout bij het aanspreken van Homey (bedoeld om aan de gebruiker te tonen)."""


class HomeyClient:
    GET_TIMEOUT = 60
    START_TIMEOUT = 30

    def __init__(self, settings: Settings):
        self.settings = settings
        self._reach_lock = threading.Lock()
        self._reach_cache: Optional[tuple] = None  # (tijdstip, resultaat)

    # -- helpers -----------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.settings.homey_address and self.settings.homey_token)

    def _scrub(self, text: str) -> str:
        token = self.settings.homey_token
        return text.replace(token, "***") if token else text

    def _run(self, script, args: List[str], timeout: int) -> str:
        if not self.configured:
            raise HomeyError("Homey-adres of token ontbreekt in config.json.")
        if not os.path.exists(script):
            raise HomeyError(f"Script niet gevonden: {script}")
        env = dict(os.environ)
        env["HOMEY_ADDRESS"] = self.settings.homey_address
        env["HOMEY_TOKEN"] = self.settings.homey_token
        env["HOMEYFLOW_CONFIG_DIR"] = str(self.settings.config_dir)
        try:
            proc = subprocess.run(
                [self.settings.node_cmd, str(script), *args],
                cwd=os.path.dirname(os.path.abspath(script)),
                capture_output=True, text=True, timeout=timeout, env=env,
            )
        except FileNotFoundError:
            raise HomeyError("Node.js is niet gevonden in de container.") from None
        except subprocess.TimeoutExpired:
            raise HomeyError("Homey reageert niet (timeout).") from None
        if proc.returncode != 0:
            lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = self._scrub(lines[-1]) if lines else "onbekende fout"
            raise HomeyError(f"Homey-script mislukt: {detail}")
        return proc.stdout

    @staticmethod
    def _parse_json(stdout: str):
        """Zoek de laatste regel met JSON; losse logregels ervoor worden genegeerd."""
        for line in reversed([l.strip() for l in stdout.splitlines() if l.strip()]):
            if line[0] in "[{":
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise HomeyError("Onverwacht antwoord van Homey-script (geen JSON).")

    # -- API ---------------------------------------------------------------
    def get_flows(self, search: str = "") -> List[dict]:
        """Lijst van {id, name, enabled} (gefilterd op zoekterm in de naam)."""
        data = self._parse_json(self._run(self.settings.node_get_flow, [search or ""], self.GET_TIMEOUT))
        flows: List[dict] = []
        if isinstance(data, dict):  # oud formaat: {naam: {id, sentences}}
            data = [{"name": name, "id": (value or {}).get("id")} for name, value in data.items()]
        for item in data:
            if isinstance(item, dict) and item.get("id") and item.get("name"):
                flows.append({"id": str(item["id"]), "name": str(item["name"]),
                              "enabled": item.get("enabled", True)})
        flows.sort(key=lambda f: f["name"].lower())
        return flows

    def start_flow(self, flow_id: str) -> None:
        if not flow_id:
            raise HomeyError("Geen flow-id opgegeven.")
        self._run(self.settings.node_start_flow, [flow_id], self.START_TIMEOUT)

    def reachable(self, ttl: float = 15.0) -> dict:
        """Snelle bereikbaarheidscontrole (HTTP-verbinding, geen inlog)."""
        if not self.settings.homey_address:
            return {"configured": False, "reachable": None}
        now = time.monotonic()
        with self._reach_lock:
            if self._reach_cache and now - self._reach_cache[0] < ttl:
                return self._reach_cache[1]
            url = self.settings.homey_address
            if "://" not in url:
                url = "http://" + url
            ok = False
            try:
                urllib.request.urlopen(url, timeout=2).close()
                ok = True
            except urllib.error.HTTPError:
                ok = True  # er kwam een HTTP-antwoord, dus Homey leeft
            except Exception:
                ok = False
            result = {"configured": self.configured, "reachable": ok}
            self._reach_cache = (now, result)
            return result
