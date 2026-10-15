"""Draait de echte skill-klasse (ovos-workshop) tegen een nagebootste intent-service.

De nagebootste service volgt het gedrag van ovos-padatious (opm.py): registreren voegt een object toe
(ook bij dezelfde naam, dus dubbel), detach verwijdert, en alles wordt in losse threads afgehandeld.
Wordt overgeslagen als ovos-workshop niet is geïnstalleerd.
"""
import json
import random
import shutil
import socket
import sys
import threading
import time
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

import pytest

pytest.importorskip("ovos_workshop")
from ovos_bus_client.message import Message  # noqa: E402
from ovos_utils.fakebus import FakeBus  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKILL_ID = "ovos-skill-homeyflowtrigger-web.stemcom"
PKG = "ovos_skill_homeyflowtrigger_web"


class FakeIntentService:
    def __init__(self, bus):
        self.bus = bus
        self.registered = []   # namen, zoals opm.registered_intents
        self.objects = []      # (naam, zinnen); dubbele namen blijven dubbel staan
        self.lock = threading.Lock()
        self.manifest_enabled = True
        self.trained_events = 0
        bus.on("padatious:register_intent", lambda m: self._async(self._register, m))
        bus.on("detach_intent", lambda m: self._async(self._detach, m))
        bus.on("intent.service.padatious.manifest.get", self._manifest)
        bus.on("intent.service.padatious.get", self._get)

    def _async(self, fn, message):
        def run():
            time.sleep(random.uniform(0, 0.05))  # verschillende volgorde, zoals losse bus-threads
            fn(message)
        threading.Thread(target=run, daemon=True).start()

    def _register(self, message):
        with self.lock:
            self.registered.append(message.data["name"])
            self.objects.append((message.data["name"], list(message.data["samples"])))
        time.sleep(0.03)
        self.trained_events += 1
        self.bus.emit(Message("mycroft.skills.trained"))

    def _detach(self, message):
        name = message.data["intent_name"]
        with self.lock:
            if name in self.registered:
                self.registered.remove(name)
                self.objects = [o for o in self.objects if o[0] != name]

    def _manifest(self, message):
        if self.manifest_enabled:
            with self.lock:
                self.bus.emit(message.reply("intent.service.padatious.manifest", {"intents": list(self.registered)}))

    def _get(self, message):
        utterance = message.data["utterance"].lower()
        best = None
        with self.lock:
            for name, samples in self.objects:
                for sample in samples:
                    score = SequenceMatcher(None, utterance, sample.lower()).ratio()
                    if best is None or score > best[0]:
                        best = (score, name, sample)
        intent = None
        if best and best[0] > 0.6:
            intent = {"name": best[1], "sent": best[2], "conf": round(best[0], 3), "matches": {}}
        self.bus.emit(message.reply("intent.service.padatious.reply", {"intent": intent}))


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(port, path, method="GET", body=None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def wait_for(predicate, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("time-out")


@pytest.fixture
def env(tmp_path, monkeypatch):
    package_dir = tmp_path / "site" / PKG
    shutil.copytree(ROOT, package_dir, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", "tests", ".pytest_cache"))
    monkeypatch.syspath_prepend(str(package_dir.parent))

    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({
        "homey": {"address": "http://127.0.0.1:9", "token": "t"},
        "nodejs": {"get_flow": str(ROOT / "dev" / "fake_get_flow.js"), "start_flow": str(ROOT / "dev" / "fake_start_flow.js")},
    }))
    (config_dir / "flow_mappings.json").write_text(json.dumps({
        "kantoor_check_in": {"id": "f1-kantoor-in", "title": "Kantoor: check in", "sentences": ["terug op kantoor", "ik ben er"]},
        "kantoor_check_out": {"id": "f2-kantoor-uit", "title": "Kantoor: check out", "sentences": ["ik ga weg van kantoor"]},
    }))
    port = _free_port()
    started = tmp_path / "started.log"
    monkeypatch.setenv("HOMEYFLOW_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOMEYFLOW_WEB_PORT", str(port))
    monkeypatch.setenv("HOMEYFLOW_WEB_HOST", "127.0.0.1")
    monkeypatch.setenv("FAKE_LOG", str(started))

    bus = FakeBus()
    service = FakeIntentService(bus)
    spoken = []
    bus.on("speak", lambda m: spoken.append(m.data["utterance"]))

    module = __import__(PKG)
    skill = module.HomeyFlowSkill(bus=bus, skill_id=SKILL_ID)
    if not getattr(skill, "hf_settings", None):
        skill._startup(bus, SKILL_ID)
    wait_for(lambda: skill._web and skill._web.running)
    yield type("Env", (), dict(skill=skill, bus=bus, service=service, port=port, spoken=spoken,
                               started=started, config_dir=config_dir, package_dir=package_dir))
    skill.shutdown()
    sys.modules.pop(PKG, None)
    for name in [n for n in sys.modules if n.startswith(PKG + ".")]:
        sys.modules.pop(name, None)


def learn(env):
    status, _ = http(env.port, "/api/learn", "POST", {"confirm": True})
    assert status == 202
    return wait_for(lambda: (lambda s: s if s["state"] in ("done", "error") else None)(http(env.port, "/api/learn")[1]), 30)


def test_startup_registers_intents_and_marks_learned(env):
    full = {f"{SKILL_ID}:kantoor_check_in.intent", f"{SKILL_ID}:kantoor_check_out.intent"}
    wait_for(lambda: set(env.service.registered) == full)
    assert (env.package_dir / "locale" / "nl-nl" / "intents" / "kantoor_check_in.intent").read_text() == "terug op kantoor\nik ben er\n"
    status = http(env.port, "/api/status")[1]
    assert status["training"]["dirty"] is False
    assert status["skill"]["registered_intents"] == 2 and status["skill"]["mode"] is not None


def test_voice_command_starts_flow_and_speaks(env):
    env.bus.emit(Message(f"{SKILL_ID}:kantoor_check_in.intent", {"utterance": "terug op kantoor"}))
    wait_for(lambda: env.spoken)
    assert env.spoken[-1] == "De actie 'Kantoor: check in' is gestart."
    assert env.started.read_text().strip() == "f1-kantoor-in"


def test_learn_replaces_old_sentences_without_duplicates(env):
    wait_for(lambda: len(env.service.registered) == 2)
    http(env.port, "/api/flows/kantoor_check_in", "PUT", {"sentences": ["helemaal nieuwe zin"]})
    http(env.port, "/api/flows", "POST", {"flows": [{"id": "f3-koffie", "name": "Koffie zetten"}]})
    http(env.port, "/api/flows/koffie_zetten", "PUT", {"sentences": ["zet koffie"]})
    http(env.port, "/api/flows/kantoor_check_out", "DELETE", {})
    assert http(env.port, "/api/status")[1]["training"]["dirty"] is True

    result = learn(env)
    assert result["state"] == "done", result
    assert "2 intent(s) geleerd" in result["message"]

    assert sorted(env.service.registered) == sorted([f"{SKILL_ID}:kantoor_check_in.intent", f"{SKILL_ID}:koffie_zetten.intent"])
    samples = {name: s for name, s in env.service.objects}
    assert samples[f"{SKILL_ID}:kantoor_check_in.intent"] == ["helemaal nieuwe zin"]  # geen oude zinnen meer
    assert len(env.service.objects) == 2  # geen dubbele objecten
    assert not (env.package_dir / "locale" / "nl-nl" / "intents" / "kantoor_check_out.intent").exists()
    assert http(env.port, "/api/status")[1]["training"]["dirty"] is False

    # Padatious-test via de webpagina: nieuwe zin herkend, oude zin niet meer
    test = http(env.port, "/api/test", "POST", {"utterance": "helemaal nieuwe zin"})[1]
    assert test["padatious"]["flow"] == "kantoor_check_in" and test["fuzzy"]["flow"] == "kantoor_check_in"
    old = http(env.port, "/api/test", "POST", {"utterance": "terug op kantoor"})[1]
    assert old["padatious"]["intent"] is None

    # De verwijderde intent doet niets meer; de nieuwe werkt
    env.spoken.clear()
    env.bus.emit(Message(f"{SKILL_ID}:kantoor_check_out.intent", {"utterance": "ik ga weg van kantoor"}))
    time.sleep(0.5)
    assert env.spoken == []
    env.bus.emit(Message(f"{SKILL_ID}:koffie_zetten.intent", {"utterance": "zet koffie"}))
    wait_for(lambda: env.spoken)
    assert env.spoken[-1] == "De actie 'Koffie zetten' is gestart."


def test_learn_twice_is_stable(env):
    wait_for(lambda: len(env.service.registered) == 2)
    for _ in range(3):
        assert learn(env)["state"] == "done"
        assert len(env.service.registered) == 2 and len(env.service.objects) == 2
        assert len(set(env.service.registered)) == 2


def test_learn_without_manifest_support_still_finishes(env):
    wait_for(lambda: len(env.service.registered) == 2)
    env.service.manifest_enabled = False
    result = learn(env)
    assert result["state"] == "done", result


def test_learn_with_no_sentences(env):
    for key in ("kantoor_check_in", "kantoor_check_out"):
        http(env.port, f"/api/flows/{key}", "PUT", {"sentences": []})
    result = learn(env)
    assert result["state"] == "done" and "geen zinnen" in result["message"].lower()
    assert env.service.registered == []


def test_padatious_unavailable_is_reported(env):
    env.bus.ee.remove_all_listeners("intent.service.padatious.get")  # intent-service antwoordt niet
    test = http(env.port, "/api/test", "POST", {"utterance": "terug op kantoor"})[1]
    assert test["padatious"]["available"] is False
