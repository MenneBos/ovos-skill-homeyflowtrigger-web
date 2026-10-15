"""flow_mappings.json: laden, valideren, veilig opslaan (met back-ups)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

Mappings = Dict[str, dict]

MAX_SENTENCE_LENGTH = 200
MAX_SENTENCES_PER_FLOW = 100


class MappingError(Exception):
    """Algemene fout met de flow mappings."""


class ValidationError(MappingError):
    """Ongeldige invoer (bedoeld om aan de gebruiker te tonen)."""


class NotFoundError(MappingError):
    """Flow bestaat niet."""


def slugify(name: str) -> str:
    """Veilige, stabiele bestandsnaam: kleine letters, cijfers, _ en -."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", "_", text.lower().strip())
    text = re.sub(r"[^a-z0-9_-]", "", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    return text or "flow"


def intent_stems(mappings: Mappings) -> Dict[str, str]:
    """Koppel elke flow-sleutel aan een unieke bestandsnaam zonder extensie."""
    used = set()
    stems: Dict[str, str] = {}
    for key in mappings:
        base = slugify(key)
        stem, number = base, 2
        while stem in used:
            stem = f"{base}_{number}"
            number += 1
        used.add(stem)
        stems[key] = stem
    return stems


def clean_sentence(sentence) -> str:
    text = re.sub(r"\s+", " ", str(sentence)).strip()
    if not text:
        raise ValidationError("Een zin mag niet leeg zijn.")
    if len(text) > MAX_SENTENCE_LENGTH:
        raise ValidationError(f"Een zin mag maximaal {MAX_SENTENCE_LENGTH} tekens bevatten.")
    if "{" in text or "}" in text:
        raise ValidationError("Accolades {} zijn niet toegestaan in zinnen.")
    if text.startswith("#"):
        raise ValidationError("Een zin mag niet beginnen met #.")
    return text


def clean_sentences(items: Iterable) -> List[str]:
    """Maak een lijst zinnen schoon: trim, geen lege, geen dubbele (hoofdletterongevoelig)."""
    if isinstance(items, (str, bytes)) or not isinstance(items, Iterable):
        raise ValidationError("'sentences' moet een lijst zijn.")
    result: List[str] = []
    seen = set()
    for item in items:
        if item is None or not str(item).strip():
            continue
        text = clean_sentence(item)
        marker = text.lower()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(text)
    if len(result) > MAX_SENTENCES_PER_FLOW:
        raise ValidationError(f"Maximaal {MAX_SENTENCES_PER_FLOW} zinnen per flow.")
    return result


def training_fingerprint(mappings: Mappings) -> str:
    """Vingerafdruk van alles wat Padatious moet leren (alleen flows met zinnen)."""
    stems = intent_stems(mappings)
    payload = [
        [stems[key], mappings[key].get("sentences", [])]
        for key in sorted(stems, key=stems.get)
        if mappings[key].get("sentences")
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def flow_title(key: str, entry: dict) -> str:
    return str(entry.get("title") or key.replace("_", " "))


class MappingStore:
    """Thread-veilige opslag van flow_mappings.json."""

    def __init__(self, path: Path, backups_dir: Optional[Path] = None, keep_backups: int = 10):
        self.path = Path(path)
        self.backups_dir = Path(backups_dir) if backups_dir else None
        self.keep_backups = keep_backups
        self._lock = threading.RLock()

    # -- lezen / schrijven -------------------------------------------------
    def load(self) -> Mappings:
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise MappingError(f"{self.path.name} bevat geen geldige JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise MappingError(f"{self.path.name} moet een JSON-object zijn.")
            return self._normalize(data)

    @staticmethod
    def _normalize(data: dict) -> Mappings:
        result: Mappings = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            entry = dict(value)  # onbekende velden (bv. favorite_flow) blijven behouden
            sentences = entry.get("sentences", [])
            if not isinstance(sentences, list):
                sentences = []
            entry["sentences"] = [str(s).strip() for s in sentences if str(s).strip()]
            entry["id"] = str(entry.get("id", "") or "")
            result[str(key)] = entry
        return result

    def save(self, mappings: Mappings) -> bool:
        """Schrijf atomair; bewaar de vorige versie. Geeft False als er niets veranderde."""
        with self._lock:
            text = json.dumps(mappings, indent=2, ensure_ascii=False) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                try:
                    old = self.path.read_text(encoding="utf-8")
                except OSError:
                    old = None
                if old == text:
                    return False
                if old is not None:
                    self._backup(old)
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            return True

    def _backup(self, old_text: str) -> None:
        if not self.backups_dir:
            return
        try:
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            (self.backups_dir / f"flow_mappings-{stamp}.json").write_text(old_text, encoding="utf-8")
            backups = sorted(self.backups_dir.glob("flow_mappings-*.json"))
            for stale in backups[: max(0, len(backups) - self.keep_backups)]:
                stale.unlink(missing_ok=True)
        except OSError:
            pass  # een back-up mag het opslaan nooit blokkeren

    def list_backups(self) -> List[str]:
        if not self.backups_dir or not self.backups_dir.exists():
            return []
        return sorted(p.name for p in self.backups_dir.glob("flow_mappings-*.json"))

    # -- bewerkingen -------------------------------------------------------
    def add_flows(self, flows: Iterable[dict]) -> List[str]:
        """Voeg flows uit Homey toe (dubbele id's worden overgeslagen). Geeft de nieuwe sleutels."""
        with self._lock:
            mappings = self.load()
            known_ids = {entry.get("id") for entry in mappings.values()}
            added: List[str] = []
            for flow in flows:
                if not isinstance(flow, dict):
                    raise ValidationError("Ongeldige flow in verzoek.")
                flow_id = str(flow.get("id", "") or "").strip()
                name = str(flow.get("name", "") or "").strip()
                if not flow_id or not name:
                    raise ValidationError("Elke flow heeft een 'id' en een 'name' nodig.")
                if flow_id in known_ids:
                    continue
                base = slugify(name)
                key, number = base, 2
                while key in mappings:
                    key = f"{base}_{number}"
                    number += 1
                mappings[key] = {"id": flow_id, "sentences": [], "title": name}
                known_ids.add(flow_id)
                added.append(key)
            if added:
                self.save(mappings)
            return added

    def set_sentences(self, key: str, sentences: Iterable) -> dict:
        with self._lock:
            mappings = self.load()
            if key not in mappings:
                raise NotFoundError(f"Flow '{key}' bestaat niet.")
            mappings[key]["sentences"] = clean_sentences(sentences)
            self.save(mappings)
            return mappings[key]

    def delete_flow(self, key: str) -> None:
        with self._lock:
            mappings = self.load()
            if key not in mappings:
                raise NotFoundError(f"Flow '{key}' bestaat niet.")
            del mappings[key]
            self.save(mappings)
