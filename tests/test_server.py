import json
import urllib.request

from homeyflow.homey import HomeyClient
from homeyflow.web import WebServer, create_app


def test_real_server_start_serve_stop(settings, store, bridge, tmp_path):
    app = create_app(settings, bridge=bridge, homey=HomeyClient(settings), store=store, intent_dir=tmp_path / "i")
    server = WebServer(app, "127.0.0.1", 0)
    server.start()
    assert server.wait_until_ready(5)
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/healthz", timeout=5) as response:
        assert json.load(response)["ok"] is True
    server.stop()
    assert not server.running


def test_port_in_use_is_retried_then_reported(settings, store, bridge, tmp_path):
    import socket
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    app = create_app(settings, bridge=bridge, homey=HomeyClient(settings), store=store, intent_dir=tmp_path / "i")
    server = WebServer(app, "127.0.0.1", port, bind_retry_seconds=2)
    server.start()
    assert not server.wait_until_ready(1)
    assert "kon niet geopend" in (server.last_error or "")
    blocker.close()  # poort komt vrij: de server moet alsnog starten
    assert server.wait_until_ready(5)
    server.stop()
