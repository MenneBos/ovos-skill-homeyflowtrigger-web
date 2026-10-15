"""Gesproken meldingen van de skill: standaardteksten (nl/en) en door de gebruiker aangepaste teksten.

De aangepaste teksten staan in ``spoken_messages.json`` naast ``flow_mappings.json`` en worden bij
elke melding opnieuw gelezen. Een wijziging in de webpagina werkt dus direct, zonder leren of herstart.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from string import Formatter
from typing import Dict, List, Optional

from .log import get_logger
from .mappings import ValidationError

LOG = get_logger()

MAX_MESSAGE_LENGTH = 200

# Standaardteksten. 'started' is bewust kort: alleen een korte bevestiging.
MESSAGES: Dict[str, Dict[str, str]] = {
    "nl-nl": {
        "started": "Gedaan.",
        "no_match": "Ik weet niet welke actie ik moet uitvoeren voor '{utterance}'.",
        "no_id": "Ik weet niet welke actie ik moet uitvoeren voor '{flow}'.",
        "error": "Er ging iets mis bij het starten van '{flow}'.",
        "settings_error": "Er ging iets mis bij het openen van de instellingen.",
    },
    "en-us": {
        "started": "Done.",
        "no_match": "Not sure which flow to start for '{utterance}'.",
        "no_id": "Not sure which flow to start for '{flow}'.",
        "error": "Something went wrong while starting the flow '{flow}'.",
        "settings_error": "Something went wrong while opening the settings.",
    },
}

# Volgorde = volgorde op de webpagina.
KEYS: List[dict] = [
    {"key": "started", "label": "Flow gestart",
     "help": "Wordt uitgesproken als de flow in Homey is gestart. Laat het veld leeg om niets te zeggen.",
     "placeholders": ["flow"], "allow_empty": True},
    {"key": "no_match", "label": "Zin niet herkend",
     "help": "Er is geen flow gevonden die bij wat je zei past.",
     "placeholders": ["utterance"], "allow_empty": False},
    {"key": "no_id", "label": "Flow zonder id",
     "help": "De flow staat wel in de lijst, maar heeft geen Homey-id.",
     "placeholders": ["flow"], "allow_empty": False},
    {"key": "error", "label": "Starten mislukt",
     "help": "Homey gaf een fout of reageerde niet.",
     "placeholders": ["flow"], "allow_empty": False},
    {"key": "settings_error", "label": "Instellingen onleesbaar",
     "help": "flow_mappings.json kon niet worden gelezen.",
     "placeholders": [], "allow_empty": False},
]
_BY_KEY = {item["key"]: item for item in KEYS}

# Voorbeeldwaarden voor 'afspelen' op de webpagina.
EXAMPLES = {"flow": "Woonkamer licht", "utterance": "zet het licht aan"}

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def defaults_for(language: str) -> Dict[str, str]:
    return MESSAGES.get((language or "").lower(), MESSAGES["nl-nl"])


def say(language: str, key: str, **values) -> str:
    """Standaardtekst (zonder aanpassingen); blijft bestaan voor eenvoudig gebruik en tests."""
    return defaults_for(language)[key].format(**values)


def clean_message(key: str, text) -> str:
    """Controleer en normaliseer een tekst; geeft de schone tekst terug of gooit ValidationError."""
    spec = _BY_KEY.get(key)
    if spec is None:
        raise ValidationError(f"Onbekende melding: {key!r}.")
    if not isinstance(text, str):
        raise ValidationError("Een melding moet tekst zijn.")
    if _CONTROL.search(text):
        raise ValidationError("Een melding mag geen regeleinden of speciale tekens bevatten.")
    text = " ".join(text.split())
    if not text:
        if spec["allow_empty"]:
            return ""
        raise ValidationError(f"'{spec['label']}' mag niet leeg zijn.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValidationError(f"Een melding mag maximaal {MAX_MESSAGE_LENGTH} tekens bevatten.")
    allowed = set(spec["placeholders"])
    hint = ("Je kunt " + ", ".join("{" + p + "}" for p in sorted(allowed)) + " gebruiken."
            if allowed else "In deze melding kun je geen invulvelden gebruiken.")
    try:
        parts = list(Formatter().parse(text))
    except ValueError:
        raise ValidationError(f"Accolades kloppen niet. {hint}") from None
    for literal, field, spec_text, conversion in parts:
        if "{" in literal or "}" in literal:
            raise ValidationError(f"Accolades kloppen niet. {hint}")
        if field is None:
            continue
        if field not in allowed or spec_text or conversion:
            raise ValidationError(f"Onbekend invulveld {{{field}}}. {hint}")
    return text


def render_text(text: str, **values) -> str:
    """Vul de invulvelden in; ontbrekende waarden worden leeg."""
    class _Values(dict):
        def __missing__(self, name):
            return ""
    return text.format_map(_Values(values))


class MessageStore:
    """Leest en schrijft de aangepaste meldingen (spoken_messages.json)."""

    def __init__(self, path: Path, language: str = "nl-nl"):
        self.path = Path(path)
        self.language = language
        self._lock = threading.Lock()

    # -- lezen ---------------------------------------------------------------
    def custom(self) -> Dict[str, str]:
        """Alleen geldige aangepaste teksten; een kapot bestand of een ongeldige tekst wordt genegeerd."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception as exc:
            LOG.error(f"{self.path.name} kon niet gelezen worden, standaardmeldingen gebruikt: {exc}")
            return {}
        if not isinstance(raw, dict):
            return {}
        result: Dict[str, str] = {}
        for key, text in raw.items():
            try:
                result[key] = clean_message(key, text)
            except ValidationError as exc:
                LOG.warning(f"Aangepaste melding '{key}' genegeerd: {exc}")
        return result

    def text(self, key: str) -> str:
        """De tekst die nu geldt (aangepast of standaard); leeg betekent: niets zeggen."""
        custom = self.custom()
        if key in custom:
            return custom[key]
        return defaults_for(self.language)[key]

    def render(self, key: str, **values) -> str:
        try:
            return render_text(self.text(key), **values).strip()
        except Exception as exc:  # nooit de spraak laten falen door een foute tekst
            LOG.error(f"Melding '{key}' kon niet worden opgebouwd: {exc}")
            return render_text(defaults_for(self.language)[key], **values).strip()

    def overview(self) -> List[dict]:
        defaults = defaults_for(self.language)
        custom = self.custom()
        items = []
        for spec in KEYS:
            key = spec["key"]
            items.append({
                "key": key, "label": spec["label"], "help": spec["help"],
                "placeholders": spec["placeholders"], "allow_empty": spec["allow_empty"],
                "default": defaults[key],
                "value": custom.get(key, defaults[key]),
                "custom": key in custom,
            })
        return items

    # -- schrijven -----------------------------------------------------------
    def update(self, updates: Dict[str, Optional[str]]) -> List[dict]:
        """``{sleutel: tekst}`` stelt in; ``{sleutel: None}`` zet terug naar de standaardtekst.
        Alles wordt eerst gecontroleerd; bij een fout wordt er niets opgeslagen."""
        if not isinstance(updates, dict) or not updates:
            raise ValidationError("Verwacht: {\"messages\": {sleutel: tekst}}")
        defaults = defaults_for(self.language)
        cleaned: Dict[str, Optional[str]] = {}
        for key, value in updates.items():
            if key not in _BY_KEY:
                raise ValidationError(f"Onbekende melding: {key!r}.")
            cleaned[key] = None if value is None else clean_message(key, value)
        with self._lock:
            current = self.custom()
            for key, value in cleaned.items():
                if value is None or (value == defaults[key]):
                    current.pop(key, None)
                else:
                    current[key] = value
            self._write(current)
        return self.overview()

    def _write(self, data: Dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".spoken_messages-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
