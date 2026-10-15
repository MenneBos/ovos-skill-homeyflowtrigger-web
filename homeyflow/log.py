"""Logger die de OVOS-logger gebruikt als die beschikbaar is."""
import logging

try:  # pragma: no cover - alleen aanwezig in een OVOS-omgeving
    from ovos_utils.log import LOG as _OVOS_LOG
except Exception:  # pragma: no cover
    _OVOS_LOG = None


def get_logger(name: str = "homeyflow"):
    if _OVOS_LOG is not None:
        return _OVOS_LOG
    return logging.getLogger(name)
