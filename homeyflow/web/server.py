"""Draait de Flask-app met waitress in een achtergrondthread."""
from __future__ import annotations

import threading
import time
from typing import Optional

from ..log import get_logger

LOG = get_logger()


class WebServer:
    """Start/stop een waitress-server; probeert opnieuw als de poort net bezet is (skill-herlaad)."""

    def __init__(self, app, host: str, port: int, threads: int = 6, bind_retry_seconds: int = 30):
        self.app = app
        self.host = host
        self.port = port
        self.threads = threads
        self.bind_retry_seconds = bind_retry_seconds
        self.last_error: Optional[str] = None
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ready = threading.Event()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._ready.is_set())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._serve, name="homeyflow-web", daemon=True)
        self._thread.start()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        return self._ready.wait(timeout)

    def _serve(self) -> None:
        from waitress.server import create_server  # lokaal importeren: alleen nodig bij starten

        deadline = time.monotonic() + self.bind_retry_seconds
        while not self._stop.is_set():
            try:
                self._server = create_server(self.app, host=self.host, port=self.port,
                                             threads=self.threads, ident="homeyflowtrigger",
                                             clear_untrusted_proxy_headers=True)
                break
            except OSError as exc:
                self.last_error = f"Poort {self.port} kon niet geopend worden: {exc}"
                if time.monotonic() > deadline:
                    LOG.error(self.last_error)
                    return
                time.sleep(1)
        if self._server is None:
            return
        # waitress kan op 0.0.0.0 én :: luisteren; port 0 (tests) krijgt een echte poort
        try:
            self.port = self._server.effective_port
        except AttributeError:
            pass
        self.last_error = None
        self._ready.set()
        LOG.info(f"Webserver bereikbaar op http://{self.host}:{self.port}")
        try:
            self._server.run()
        except Exception as exc:  # pragma: no cover
            self.last_error = f"Webserver gestopt: {exc}"
            LOG.error(self.last_error)
        finally:
            self._ready.clear()

    def stop(self) -> None:
        self._stop.set()
        server, self._server = self._server, None
        if server is not None:
            try:
                server.close()
            except Exception as exc:  # pragma: no cover
                LOG.warning(f"Webserver stoppen gaf een fout: {exc}")
        if self._thread:
            self._thread.join(timeout=5)
