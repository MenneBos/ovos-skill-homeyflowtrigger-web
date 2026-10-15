"""Schrijf de .intent-bestanden (één per flow) die Padatious leert."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .mappings import Mappings, intent_stems


@dataclass
class SyncResult:
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    @property
    def files(self) -> List[str]:
        """Alle bestanden die nu horen te bestaan."""
        return sorted(self.created + self.updated + self.unchanged)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.removed)


def desired_intent_files(mappings: Mappings) -> Dict[str, List[str]]:
    """Bestandsnaam -> zinnen. Flows zonder zinnen krijgen geen bestand (Padatious kan geen lege intent trainen)."""
    stems = intent_stems(mappings)
    return {
        f"{stems[key]}.intent": list(entry.get("sentences", []))
        for key, entry in mappings.items()
        if entry.get("sentences")
    }


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name("." + path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def sync_intent_files(intent_dir: Path, mappings: Mappings) -> SyncResult:
    """Maak de map gelijk aan de mappings: schrijf nieuwe/gewijzigde, verwijder overbodige."""
    intent_dir = Path(intent_dir)
    intent_dir.mkdir(parents=True, exist_ok=True)
    desired = desired_intent_files(mappings)
    result = SyncResult()

    for name, sentences in sorted(desired.items()):
        path = intent_dir / name
        text = "\n".join(sentences) + "\n"
        if not path.exists():
            _write_atomic(path, text)
            result.created.append(name)
        elif path.read_text(encoding="utf-8") != text:
            _write_atomic(path, text)
            result.updated.append(name)
        else:
            result.unchanged.append(name)

    for path in sorted(intent_dir.glob("*.intent")):
        if path.name not in desired:
            path.unlink()
            result.removed.append(path.name)
    return result
