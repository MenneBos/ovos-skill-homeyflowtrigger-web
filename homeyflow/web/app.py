"""De Flask-app: beheerpagina en JSON-API voor flow_mappings.json."""
from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

from .. import __version__
from ..bridge import BridgeError, SkillBridge
from ..config import Settings
from ..flowrunner import run_utterance
from ..homey import HomeyClient, HomeyError
from ..log import get_logger
from ..mappings import (MappingError, MappingStore, NotFoundError, ValidationError,
                        flow_title, intent_stems, training_fingerprint)
from ..trainer import Trainer

LOG = get_logger()

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")
LOCAL_SUFFIXES = (".local", ".lan", ".home.arpa", ".internal", ".localdomain", ".ts.net")


def _host_allowed(host_header: str, extra_hosts) -> bool:
    """Bescherming tegen DNS-rebinding: alleen IP's, lokale namen en bekende hostnamen."""
    host = (host_header or "").strip().lower()
    if not host:
        return False
    if host.startswith("["):  # IPv6-literal, bv. [::1]:8200
        return True
    hostname = host.rsplit(":", 1)[0] if ":" in host else host
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if hostname == "localhost" or "." not in hostname:
        return True
    if hostname.endswith(LOCAL_SUFFIXES):
        return True
    return hostname in extra_hosts


def create_app(settings: Settings, bridge: Optional[SkillBridge] = None,
               homey: Optional[HomeyClient] = None, store: Optional[MappingStore] = None,
               trainer: Optional[Trainer] = None, intent_dir: Optional[Path] = None) -> Flask:
    bridge = bridge or SkillBridge()
    homey = homey or HomeyClient(settings)
    store = store or MappingStore(settings.mappings_path, settings.backups_dir)
    if trainer is None:
        trainer = Trainer(settings, store, bridge, intent_dir or settings.config_dir / "intents")

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.config["JSON_AS_ASCII"] = False
    allowed_hosts = set(settings.allowed_hosts)

    # -- beveiliging zonder wachtwoord ------------------------------------
    @app.before_request
    def guard():
        if not _host_allowed(request.host, allowed_hosts):
            return jsonify(error="Onbekende hostnaam. Voeg hem toe aan web.allowed_hosts in config.json."), 403
        if request.method in SAFE_METHODS:
            return None
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            return jsonify(error="Verzoek van een andere website geweigerd."), 403
        if request.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            return jsonify(error="Verzoek van een andere website geweigerd."), 403
        if not (request.content_type or "").startswith("application/json"):
            return jsonify(error="Content-Type moet application/json zijn."), 415
        return None

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # -- foutafhandeling ---------------------------------------------------
    @app.errorhandler(ValidationError)
    def _validation(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(NotFoundError)
    def _not_found(exc):
        return jsonify(error=str(exc)), 404

    @app.errorhandler(MappingError)
    def _mapping(exc):
        return jsonify(error=str(exc)), 500

    @app.errorhandler(HomeyError)
    def _homey(exc):
        return jsonify(error=str(exc)), 502

    @app.errorhandler(BridgeError)
    def _bridge(exc):
        return jsonify(error=str(exc)), 501

    @app.errorhandler(404)
    def _404(exc):
        if request.path.startswith("/api/"):
            return jsonify(error="Niet gevonden."), 404
        return render_template("error.html", message="Pagina niet gevonden."), 404

    @app.errorhandler(Exception)
    def _unexpected(exc):
        LOG.error(f"Onverwachte fout in webserver: {exc!r}")
        if request.path.startswith("/api/"):
            return jsonify(error="Onverwachte fout in de server."), 500
        return render_template("error.html", message="Onverwachte fout in de server."), 500

    # -- hulpfuncties ------------------------------------------------------
    def flow_views(mappings):
        stems = intent_stems(mappings)
        return [{"key": key, "title": flow_title(key, entry), "id": entry.get("id", ""),
                 "sentences": entry.get("sentences", []), "stem": stems[key]}
                for key, entry in mappings.items()]

    def overview(mappings=None):
        mappings = store.load() if mappings is None else mappings
        return {"flows": flow_views(mappings), "dirty": trainer.is_dirty(mappings)}

    # -- pagina's ----------------------------------------------------------
    @app.get("/")
    def dashboard():
        return render_template("index.html", page="dashboard", version=__version__)

    @app.get("/flows")
    def flows_page():
        return render_template("flows.html", page="flows", version=__version__)

    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True, skill=bridge.skill_status(), version=__version__)

    # -- API ---------------------------------------------------------------
    @app.get("/api/status")
    def api_status():
        mappings = store.load()
        training = trainer.status()
        training["dirty"] = trainer.is_dirty(mappings)
        training["learned_at"] = trainer.state.learned_at
        training["fingerprint"] = training_fingerprint(mappings)
        return jsonify(
            version=__version__,
            homey=homey.reachable(),
            flows=len(mappings),
            flows_with_sentences=sum(1 for e in mappings.values() if e.get("sentences")),
            sentences=sum(len(e.get("sentences", [])) for e in mappings.values()),
            training=training,
            skill=bridge.skill_status(),
            web={"port": settings.web_port, "language": settings.language},
        )

    @app.get("/api/flows")
    def api_flows():
        return jsonify(overview())

    @app.post("/api/flows")
    def api_add_flows():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("flows"), list):
            raise ValidationError("Verwacht: {\"flows\": [{\"id\": ..., \"name\": ...}]}")
        added = store.add_flows(body["flows"])
        return jsonify(added=added, **overview()), 201 if added else 200

    @app.put("/api/flows/<key>")
    def api_set_sentences(key):
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or "sentences" not in body:
            raise ValidationError("Verwacht: {\"sentences\": [...]}")
        store.set_sentences(key, body["sentences"])
        mappings = store.load()
        view = next(v for v in flow_views(mappings) if v["key"] == key)
        return jsonify(flow=view, dirty=trainer.is_dirty(mappings))

    @app.delete("/api/flows/<key>")
    def api_delete_flow(key):
        store.delete_flow(key)
        return jsonify(overview())

    @app.get("/api/homey/flows")
    def api_homey_flows():
        query = request.args.get("q", "").strip()
        known = {entry.get("id") for entry in store.load().values()}
        flows = homey.get_flows(query)
        return jsonify(flows=[{**flow, "added": flow["id"] in known} for flow in flows], query=query)

    @app.get("/api/learn")
    def api_learn_status():
        status = trainer.status()
        status["dirty"] = trainer.is_dirty()
        return jsonify(status)

    @app.post("/api/learn")
    def api_learn_start():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body.get("confirm") is not True:
            raise ValidationError("Bevestiging ontbreekt (confirm: true).")
        started = trainer.start()
        status = trainer.status()
        status["dirty"] = trainer.is_dirty()
        status["started"] = started
        return jsonify(status), 202 if started else 409

    @app.post("/api/test")
    def api_test():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValidationError("Ongeldig verzoek.")
        utterance = str(body.get("utterance", "")).strip()
        if not utterance:
            raise ValidationError("Geef een zin om te testen.")
        run = bool(body.get("run"))
        if run and body.get("confirm") is not True:
            raise ValidationError("Bevestiging ontbreekt (confirm: true).")

        result = {"fuzzy": run_utterance(utterance, store, homey, run=run)}
        if not run:
            padatious = bridge.padatious_test(utterance)
            if padatious.get("intent"):
                stems = {stem: key for key, stem in intent_stems(store.load()).items()}
                name = str(padatious["intent"]).split(":")[-1]
                stem = name[:-len(".intent")] if name.endswith(".intent") else name
                padatious["flow"] = stems.get(stem)
            result["padatious"] = padatious
        return jsonify(result)

    @app.post("/api/restart")
    def api_restart():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body.get("confirm") is not True:
            raise ValidationError("Bevestiging ontbreekt (confirm: true).")
        if not bridge.supports_restart:
            raise BridgeError("Herstarten wordt in deze omgeving niet ondersteund.")
        bridge.restart()
        return jsonify(ok=True, message="De skill wordt herstart.")

    return app
