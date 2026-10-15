import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from homeyflow.config import Settings  # noqa: E402
from homeyflow.devtools import FakeBridge  # noqa: E402
from homeyflow.homey import HomeyClient  # noqa: E402
from homeyflow.mappings import MappingStore  # noqa: E402
from homeyflow.web import create_app  # noqa: E402

SEED = {
    "kantoor_check_in": {"id": "f1-kantoor-in", "title": "Kantoor: check in", "favorite_flow": "yes",
                         "sentences": ["Ik ben aanwezig op kantoor", "terug op kantoor"]},
    "kantoor_check_out": {"id": "f2-kantoor-uit", "sentences": ["ik ga weg van kantoor"]},
}


@pytest.fixture
def settings(tmp_path):
    return Settings(
        config_dir=tmp_path / "cfg",
        homey_address="http://127.0.0.1:9",
        homey_token="geheim-token-123",
        node_get_flow=ROOT / "dev" / "fake_get_flow.js",
        node_start_flow=ROOT / "dev" / "fake_start_flow.js",
    )


@pytest.fixture
def store(settings):
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    settings.mappings_path.write_text(json.dumps(SEED), encoding="utf-8")
    return MappingStore(settings.mappings_path, settings.backups_dir)


@pytest.fixture
def bridge(store):
    return FakeBridge(store, delay=0.01)


@pytest.fixture
def client(settings, store, bridge, tmp_path):
    app = create_app(settings, bridge=bridge, homey=HomeyClient(settings), store=store,
                     intent_dir=tmp_path / "intents")
    app.testing = True
    return app.test_client()

