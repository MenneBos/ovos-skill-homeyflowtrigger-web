"""Instellingen: config.json in de gebruikersmap, met optionele omgevingsvariabelen."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Mapping, Optional

from .log import get_logger

LOG = get_logger()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR_NAME = "ovos_skill_homeyflowtrigger"
DEFAULT_PORT = 8200
_LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")


def default_config_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if env is None else env
    custom = env.get("HOMEYFLOW_CONFIG_DIR")
    if custom:
        return Path(custom).expanduser()
    return Path("~/.config").expanduser() / CONFIG_DIR_NAME


def _script_path(value: str, default: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


@dataclass
class Settings:
    config_dir: Path
    homey_address: str = ""
    homey_token: str = ""
    node_cmd: str = "node"
    node_get_flow: Path = REPO_ROOT / "nodejs" / "get_flow.js"
    node_start_flow: Path = REPO_ROOT / "nodejs" / "start_flow.js"
    web_host: str = "0.0.0.0"
    web_port: int = DEFAULT_PORT
    allowed_hosts: List[str] = field(default_factory=list)
    language: str = "nl-nl"
    training_mode: str = "live"  # "live" (via messagebus) of "restart"
    training_timeout: int = 120

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def mappings_path(self) -> Path:
        return self.config_dir / "flow_mappings.json"

    @property
    def backups_dir(self) -> Path:
        return self.config_dir / "flow_mappings_backups"

    @property
    def state_path(self) -> Path:
        return self.config_dir / "training_state.json"


def _as_int(value, default: int, name: str) -> int:
    try:
        number = int(value)
        if number <= 0:
            raise ValueError
        return number
    except (TypeError, ValueError):
        LOG.warning(f"Ongeldige waarde voor {name}: {value!r}, standaard {default} gebruikt.")
        return default


def load_settings(config_dir: Optional[Path] = None,
                  env: Optional[Mapping[str, str]] = None) -> Settings:
    """Lees config.json (indien aanwezig) en pas omgevingsvariabelen toe."""
    env = os.environ if env is None else env
    config_dir = Path(config_dir) if config_dir else default_config_dir(env)
    settings = Settings(config_dir=config_dir)

    data: dict = {}
    path = settings.config_path
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("config.json moet een JSON-object zijn")
        except Exception as exc:
            LOG.error(f"config.json kon niet gelezen worden ({path}): {exc}")
            data = {}
    else:
        LOG.warning(f"Geen config.json gevonden in {config_dir}; standaardwaarden gebruikt.")

    homey = data.get("homey") or {}
    nodejs = data.get("nodejs") or {}
    web = data.get("web") or {}
    training = data.get("training") or {}

    settings.homey_address = str(homey.get("address", "") or "")
    settings.homey_token = str(homey.get("token", "") or "")
    settings.node_cmd = str(nodejs.get("command", "") or "node")
    settings.node_get_flow = _script_path(str(nodejs.get("get_flow", "") or ""), settings.node_get_flow)
    settings.node_start_flow = _script_path(str(nodejs.get("start_flow", "") or ""), settings.node_start_flow)
    settings.web_host = str(web.get("host", "") or settings.web_host)
    settings.web_port = _as_int(web.get("port", DEFAULT_PORT), DEFAULT_PORT, "web.port")
    hosts = web.get("allowed_hosts") or []
    settings.allowed_hosts = [str(h).strip().lower() for h in hosts if str(h).strip()]
    settings.language = str(data.get("language", "") or settings.language).lower()
    settings.training_mode = str(training.get("mode", "") or settings.training_mode).lower()
    settings.training_timeout = _as_int(training.get("timeout", 120), 120, "training.timeout")

    # Omgevingsvariabelen hebben voorrang (handig in compose).
    if env.get("HOMEYFLOW_HOMEY_ADDRESS"):
        settings.homey_address = env["HOMEYFLOW_HOMEY_ADDRESS"]
    if env.get("HOMEYFLOW_HOMEY_TOKEN"):
        settings.homey_token = env["HOMEYFLOW_HOMEY_TOKEN"]
    if env.get("HOMEYFLOW_WEB_HOST"):
        settings.web_host = env["HOMEYFLOW_WEB_HOST"]
    if env.get("HOMEYFLOW_WEB_PORT"):
        settings.web_port = _as_int(env["HOMEYFLOW_WEB_PORT"], DEFAULT_PORT, "HOMEYFLOW_WEB_PORT")
    if env.get("HOMEYFLOW_ALLOWED_HOSTS"):
        settings.allowed_hosts = [h.strip().lower() for h in env["HOMEYFLOW_ALLOWED_HOSTS"].split(",") if h.strip()]
    if env.get("HOMEYFLOW_LANGUAGE"):
        settings.language = env["HOMEYFLOW_LANGUAGE"].lower()
    if env.get("HOMEYFLOW_TRAINING_MODE"):
        settings.training_mode = env["HOMEYFLOW_TRAINING_MODE"].lower()

    if not _LANG_RE.match(settings.language):
        LOG.warning(f"Ongeldige taal {settings.language!r}, nl-nl gebruikt.")
        settings.language = "nl-nl"
    if settings.training_mode not in ("live", "restart"):
        LOG.warning(f"Onbekende training-modus {settings.training_mode!r}, 'live' gebruikt.")
        settings.training_mode = "live"
    return settings
