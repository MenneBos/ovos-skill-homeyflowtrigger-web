"""Het 'leren' van intents: bestanden schrijven, intent-service bijwerken, status bijhouden."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from .bridge import SkillBridge
from .config import Settings
from .intents import sync_intent_files
from .log import get_logger
from .mappings import MappingStore, training_fingerprint

LOG = get_logger()


class TrainingState:
    """Onthoudt welke zinnen het laatst geleerd zijn (voor de 'nog niet geleerd'-melding)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @property
    def learned_fingerprint(self) -> Optional[str]:
        return self.read().get("learned_fingerprint")

    @property
    def learned_at(self) -> Optional[float]:
        return self.read().get("learned_at")

    def mark_learned(self, fingerprint: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({"learned_fingerprint": fingerprint, "learned_at": time.time()}),
                           encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            LOG.warning(f"Kon training_state.json niet schrijven: {exc}")


class Trainer:
    def __init__(self, settings: Settings, store: MappingStore, bridge: SkillBridge,
                 intent_dir: Path, state: Optional[TrainingState] = None):
        self.settings = settings
        self.store = store
        self.bridge = bridge
        self.intent_dir = Path(intent_dir)
        self.state = state or TrainingState(settings.state_path)
        self._lock = threading.Lock()
        self._status = {"state": "idle", "step": "", "message": "", "log": [],
                        "started_at": None, "finished_at": None}

    # -- status ------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            snapshot = dict(self._status)
            snapshot["log"] = list(self._status["log"])
        snapshot["mode"] = self.settings.training_mode
        return snapshot

    def is_dirty(self, mappings=None) -> bool:
        mappings = self.store.load() if mappings is None else mappings
        return training_fingerprint(mappings) != self.state.learned_fingerprint

    def _set(self, **values) -> None:
        with self._lock:
            self._status.update(values)

    def _step(self, text: str) -> None:
        LOG.info(f"Leren: {text}")
        with self._lock:
            self._status["step"] = text
            self._status["log"].append({"t": time.time(), "msg": text})

    # -- uitvoeren ---------------------------------------------------------
    def start(self) -> bool:
        """Start het leren op de achtergrond. False als er al een run bezig is."""
        with self._lock:
            if self._status["state"] in ("running", "restarting"):
                return False
            self._status = {"state": "running", "step": "Starten", "message": "", "log": [],
                            "started_at": time.time(), "finished_at": None}
        threading.Thread(target=self._run, name="homeyflow-learn", daemon=True).start()
        return True

    def _finish(self, state: str, message: str) -> None:
        self._set(state=state, message=message, finished_at=time.time())

    def _run(self) -> None:
        try:
            self._step("Intent-bestanden bijwerken")
            mappings = self.store.load()
            fingerprint = training_fingerprint(mappings)
            changes = sync_intent_files(self.intent_dir, mappings)
            self._step(f"{len(changes.files)} intent-bestand(en), "
                       f"{len(changes.created)} nieuw, {len(changes.updated)} gewijzigd, "
                       f"{len(changes.removed)} verwijderd")

            if self.settings.training_mode == "restart":
                self.state.mark_learned(fingerprint)
                self._step("Skill herstarten")
                self.bridge.restart()
                self._set(state="restarting", message="De skill wordt herstart; de pagina is zo weer bereikbaar.")
                return

            message = self.bridge.apply_intents(changes, self._step)
            self.state.mark_learned(fingerprint)
            self._finish("done", message or "Klaar.")
        except Exception as exc:  # fouten tonen aan de gebruiker, nooit de thread laten sneuvelen
            LOG.error(f"Leren mislukt: {exc}")
            self._finish("error", str(exc) or exc.__class__.__name__)
