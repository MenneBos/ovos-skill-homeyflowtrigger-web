"""Hulpmiddelen om de webpagina zonder OVOS en zonder Homey te draaien (dev en tests)."""
from __future__ import annotations

import time
from typing import Callable

from .bridge import BridgeError, SkillBridge
from .intents import SyncResult
from .mappings import MappingStore, intent_stems
from .matcher import best_match


class FakeBridge(SkillBridge):
    """Doet alsof er een skill en intent-service zijn."""

    supports_restart = True

    def __init__(self, store: MappingStore, delay: float = 0.4, fail: str = ""):
        self.store = store
        self.delay = delay
        self.fail = fail
        self.registered = 0
        self.restarted = False
        self.padatious_available = True

    def skill_status(self) -> dict:
        return {"running": True, "mode": "dev", "language": "nl-nl",
                "registered_intents": self.registered, "web_running": True}

    def apply_intents(self, changes: SyncResult, progress: Callable[[str], None]) -> str:
        for name in changes.files:
            progress(f"Intent registreren: {name}")
            time.sleep(self.delay)
        progress("Wachten tot de intent-service klaar is met leren")
        time.sleep(self.delay)
        if self.fail:
            raise BridgeError(self.fail)
        self.registered = len(changes.files)
        return f"{len(changes.files)} intent(s) geleerd."

    def padatious_test(self, utterance: str) -> dict:
        if not self.padatious_available:
            return {"available": False, "intent": None, "confidence": None}
        mappings = self.store.load()
        match = best_match(utterance, mappings, 0.3)
        if not match:
            return {"available": True, "intent": None, "confidence": None}
        stem = intent_stems(mappings)[match.key]
        return {"available": True, "intent": f"fake-skill:{stem}.intent",
                "confidence": round(match.score * 0.97, 3)}

    def restart(self) -> None:
        self.restarted = True
