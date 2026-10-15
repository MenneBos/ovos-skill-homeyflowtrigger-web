"""Wat de webserver van de skill nodig heeft (zodat de web-code los van OVOS blijft)."""
from __future__ import annotations

from typing import Callable, Optional

from .intents import SyncResult


class BridgeError(Exception):
    """De skill kon de gevraagde actie niet uitvoeren."""


class SkillBridge:
    """Basisklasse; de echte skill en de dev-/testversie vullen dit in."""

    supports_restart = False

    def skill_status(self) -> dict:
        return {"running": False, "detail": "geen skill gekoppeld"}

    def apply_intents(self, changes: SyncResult, progress: Callable[[str], None]) -> str:
        """Registreer alle intents opnieuw bij de intent-service en wacht tot ze geleerd zijn."""
        raise BridgeError("Live leren wordt niet ondersteund.")

    def padatious_test(self, utterance: str) -> dict:
        """{'available': bool, 'intent': naam|None, 'confidence': float|None}"""
        return {"available": False, "intent": None, "confidence": None}

    def restart(self) -> None:
        """Herstart de skill kort na dit antwoord (zodat het HTTP-antwoord nog aankomt)."""
        raise BridgeError("Herstarten wordt niet ondersteund.")
