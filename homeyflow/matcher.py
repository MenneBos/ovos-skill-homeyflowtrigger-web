"""Fuzzy matching van een uitspraak op de zinnen in flow_mappings.json (zoals de originele skill)."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from .mappings import Mappings

DEFAULT_CUTOFF = 0.6


@dataclass
class Match:
    key: str
    sentence: str
    score: float


def best_match(utterance: str, mappings: Mappings, cutoff: float = DEFAULT_CUTOFF) -> Optional[Match]:
    """Zelfde gedrag als difflib.get_close_matches(n=1): hoogste score, drempel `cutoff`."""
    utterance = (utterance or "").strip().lower()
    if not utterance:
        return None

    sentence_to_flow = {}
    for key, entry in mappings.items():
        for sentence in entry.get("sentences", []):
            sentence_to_flow[sentence.lower()] = key  # laatste wint, zoals in de originele skill

    matcher = SequenceMatcher()
    matcher.set_seq2(utterance)
    best: Optional[tuple] = None
    for sentence in sentence_to_flow:
        matcher.set_seq1(sentence)
        if (matcher.real_quick_ratio() >= cutoff and matcher.quick_ratio() >= cutoff):
            score = matcher.ratio()
            if score >= cutoff and (best is None or (score, sentence) > best):
                best = (score, sentence)
    if best is None:
        return None
    score, sentence = best
    return Match(key=sentence_to_flow[sentence], sentence=sentence, score=score)
