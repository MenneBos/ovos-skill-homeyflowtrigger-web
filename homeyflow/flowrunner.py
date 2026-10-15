"""Zoek de flow bij een uitspraak en start hem (gedeeld door de skill en de testpagina)."""
from __future__ import annotations

from .homey import HomeyClient, HomeyError
from .log import get_logger
from .mappings import MappingStore, flow_title
from .matcher import DEFAULT_CUTOFF, best_match

LOG = get_logger()


def run_utterance(utterance: str, store: MappingStore, homey: HomeyClient,
                  run: bool = True, cutoff: float = DEFAULT_CUTOFF) -> dict:
    """status: matched | no_match | no_id | started | error"""
    mappings = store.load()
    match = best_match(utterance, mappings, cutoff)
    if match is None:
        return {"status": "no_match", "utterance": utterance, "cutoff": cutoff}

    entry = mappings[match.key]
    info = {
        "utterance": utterance,
        "flow": match.key,
        "title": flow_title(match.key, entry),
        "sentence": match.sentence,
        "score": round(match.score, 3),
        "cutoff": cutoff,
    }
    flow_id = entry.get("id")
    if not flow_id:
        return {**info, "status": "no_id"}
    if not run:
        return {**info, "status": "matched"}
    try:
        homey.start_flow(flow_id)
    except HomeyError as exc:
        LOG.error(f"Flow '{match.key}' kon niet gestart worden: {exc}")
        return {**info, "status": "error", "error": str(exc)}
    return {**info, "status": "started"}
