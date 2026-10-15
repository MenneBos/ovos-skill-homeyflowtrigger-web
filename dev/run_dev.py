#!/usr/bin/env python3
"""Start de beheerpagina los van OVOS, met een nep-Homey en een nepskill.

    python dev/run_dev.py            # http://127.0.0.1:8200
    python dev/run_dev.py --port 8300

Gegevens komen in een tijdelijke map (of --dir), er wordt niets aan je echte config gewijzigd.
"""
import argparse
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from homeyflow.config import load_settings  # noqa: E402
from homeyflow.devtools import FakeBridge  # noqa: E402
from homeyflow.mappings import MappingStore  # noqa: E402
from homeyflow.web import WebServer, create_app  # noqa: E402

SEED = {
    "kantoor_check_in": {"id": "f1-kantoor-in", "title": "Kantoor: check in",
                         "sentences": ["Ik ben aanwezig op kantoor", "terug op kantoor", "ik ben er"],
                         "favorite_flow": "yes"},
    "kantoor_check_out": {"id": "f2-kantoor-uit", "title": "Kantoor: check out",
                          "sentences": ["Ik ga weg van kantoor", "weg"]},
    "koffie_zetten": {"id": "f3-koffie", "title": "Koffie zetten", "sentences": []},
}


class _FakeHomey(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(401)
        self.end_headers()

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--dir", default="")
    args = parser.parse_args()

    base = Path(args.dir) if args.dir else Path(tempfile.mkdtemp(prefix="homeyflow-dev-"))
    base.mkdir(parents=True, exist_ok=True)

    homey = HTTPServer(("127.0.0.1", 0), _FakeHomey)
    threading.Thread(target=homey.serve_forever, daemon=True).start()

    config = {
        "homey": {"address": f"http://127.0.0.1:{homey.server_port}", "token": "dev-token"},
        "nodejs": {"get_flow": str(ROOT / "dev" / "fake_get_flow.js"),
                   "start_flow": str(ROOT / "dev" / "fake_start_flow.js")},
        "web": {"host": args.host, "port": args.port},
    }
    (base / "config.json").write_text(json.dumps(config), encoding="utf-8")
    settings = load_settings(base)
    if not settings.mappings_path.exists():
        settings.mappings_path.write_text(json.dumps(SEED, indent=2), encoding="utf-8")

    store = MappingStore(settings.mappings_path, settings.backups_dir)
    app = create_app(settings, bridge=FakeBridge(store), store=store, intent_dir=base / "intents")
    server = WebServer(app, settings.web_host, settings.web_port)
    server.start()
    server.wait_until_ready(10)
    print(f"Dev-server: http://{server.host}:{server.port}  (gegevens in {base})")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
