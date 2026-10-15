"""De OVOS-skill: spraakopdracht -> Homey-flow, plus de ingebouwde beheerwebserver."""
import threading
import time
from pathlib import Path

from ovos_bus_client.message import Message
from ovos_workshop.skills.ovos import OVOSSkill

from .homeyflow.bridge import BridgeError, SkillBridge
from .homeyflow.config import load_settings
from .homeyflow.flowrunner import run_utterance
from .homeyflow.homey import HomeyClient
from .homeyflow.intents import SyncResult, sync_intent_files
from .homeyflow.mappings import MappingError, MappingStore, training_fingerprint
from .homeyflow.messages import say
from .homeyflow.trainer import TrainingState
from .homeyflow.web import WebServer, create_app


class _Bridge(SkillBridge):
    """Laat de webserver met de skill praten."""

    supports_restart = True

    def __init__(self, skill):
        self.skill = skill

    def skill_status(self):
        skill = self.skill
        web = skill._web
        return {
            "running": True,
            "mode": skill.deploy_mode,
            "language": skill.language,
            "registered_intents": len(skill._registered),
            "web_running": bool(web and web.running),
        }

    def apply_intents(self, changes, progress):
        return self.skill.apply_intents(changes, progress)

    def padatious_test(self, utterance):
        return self.skill.padatious_test(utterance)

    def restart(self):
        self.skill.schedule_restart()


class HomeyFlowBaseSkill(OVOSSkill):
    """Gemeenschappelijke skill-code; de varianten bepalen alleen hoe herstarten gaat."""

    deploy_mode = "unknown"

    # ------------------------------------------------------------------ start
    def initialize(self):
        self.hf_settings = load_settings()
        self.language = self.hf_settings.language
        self.intent_dir = Path(self.root_dir) / "locale" / self.language / "intents"
        self.store = MappingStore(self.hf_settings.mappings_path, self.hf_settings.backups_dir)
        self.homey = HomeyClient(self.hf_settings)
        self.training_state = TrainingState(self.hf_settings.state_path)
        self._registered = set()  # intent-bestanden die nu bij de intent-service staan
        self._intent_lock = threading.Lock()
        self._web = None

        # Eerst de webserver: die blijft bereikbaar (en toont fouten) ook als de rest niet lukt.
        self._start_web()
        self._register_intents_at_startup()

    def _start_web(self):
        try:
            app = create_app(self.hf_settings, bridge=_Bridge(self), homey=self.homey,
                             store=self.store, intent_dir=self.intent_dir)
            self._web = WebServer(app, self.hf_settings.web_host, self.hf_settings.web_port)
            self._web.start()
            self.log.info(f"Beheerwebserver gestart op poort {self.hf_settings.web_port}")
        except Exception as exc:
            self.log.error(f"Webserver kon niet starten: {exc}")

    def _register_intents_at_startup(self):
        try:
            mappings = self.store.load()
            changes = sync_intent_files(self.intent_dir, mappings)
            for name in changes.files:
                self._register_file(name)
                self.log.info(f"Intent '{name}' geregistreerd.")
            self.training_state.mark_learned(training_fingerprint(mappings))
        except MappingError as exc:
            self.log.error(f"flow_mappings.json kon niet geladen worden: {exc}")
        except Exception as exc:
            self.log.error(f"Intents registreren mislukt: {exc}")

    def shutdown(self):
        if getattr(self, "_web", None):
            self._web.stop()

    # ---------------------------------------------------------------- spraak
    def handle_start_flow(self, message):
        utterance = (message.data.get("utterance") or "").strip().lower()
        if not utterance and message.data.get("utterances"):
            utterance = message.data["utterances"][0].strip().lower()
        self.log.info(f"Uitspraak: '{utterance}'")

        try:
            result = run_utterance(utterance, self.store, self.homey, run=True)
        except MappingError as exc:
            self.log.error(f"flow_mappings.json kon niet geladen worden: {exc}")
            self.speak(say(self.language, "settings_error"))
            return

        status = result["status"]
        if status == "no_match":
            self.log.error(f"Geen overeenkomende zin voor: '{utterance}'")
            self.speak(say(self.language, "no_match", utterance=utterance))
        elif status == "no_id":
            self.log.error(f"Geen id gevonden voor flow '{result['flow']}'")
            self.speak(say(self.language, "no_id", flow=result["title"]))
        elif status == "error":
            self.log.error(f"Flow '{result['flow']}' starten mislukt: {result.get('error')}")
            self.speak(say(self.language, "error", flow=result["title"]))
        else:
            self.log.info(f"Flow '{result['flow']}' gestart (score {result['score']}).")
            self.speak(say(self.language, "started", flow=result["title"]))

    # ------------------------------------------------- leren via de messagebus
    def _full_name(self, name):
        return f"{self.skill_id}:{name}"

    def _register_file(self, name):
        """Registreer één .intent-bestand (volledig pad + ingestelde taal) en koppel de handler eenmalig.

        Bewust niet via register_intent(): die zoekt het bestand via de OVOS-systeemtaal en slaat het
        bij een afwijkende taal stilletjes over.
        """
        full = self._full_name(name)
        self.intent_service.register_padatious_intent(full, str(self.intent_dir / name), self.language)
        if name not in self._registered:
            try:
                self.add_event(full, self.handle_start_flow, "mycroft.skill.handler",
                               activation=True, is_intent=True)
            except TypeError:  # oudere ovos-workshop zonder deze parameters
                self.add_event(full, self.handle_start_flow, "mycroft.skill.handler")
        self._registered.add(name)

    def _detach_file(self, name):
        """Koppel een intent los bij de intent-service (naam zonder skill-id, zoals ovos-workshop verwacht)."""
        remove = getattr(self.intent_service, "remove_intent", None)
        if callable(remove):
            remove(name)
        else:  # oudere versies: het bericht rechtstreeks sturen
            self.bus.emit(Message("detach_intent", {"intent_name": self._full_name(name)},
                                  {"skill_id": self.skill_id}))

    def _manifest(self, timeout=3.0):
        """Namen van de intents die Padatious nu kent, of None als de intent-service niet antwoordt."""
        reply = self.bus.wait_for_response(Message("intent.service.padatious.manifest.get"),
                                           "intent.service.padatious.manifest", timeout=timeout)
        if reply is None:
            return None
        names = set()
        for item in reply.data.get("intents", []):
            names.add(item if isinstance(item, str) else (item or {}).get("name"))
        return names

    def _wait_manifest(self, predicate, timeout):
        """Wacht tot predicate(namen) waar is. Geeft None als er geen overzicht beschikbaar is."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            names = self._manifest()
            if names is None:
                return None
            if predicate(names):
                return True
            time.sleep(0.3)
        return False

    def apply_intents(self, changes: SyncResult, progress):
        """Koppel alle intents los en registreer ze opnieuw; Padatious traint daarna zelf."""
        timeout = self.hf_settings.training_timeout
        wanted = list(changes.files)
        trained = threading.Event()
        last_trained = [0.0]

        def on_trained(_message):
            last_trained[0] = time.monotonic()
            trained.set()

        self.bus.on("mycroft.skills.trained", on_trained)
        try:
            with self._intent_lock:
                current = sorted(self._registered)
                progress(f"{len(current)} bestaande intent(s) loskoppelen")
                for name in current:
                    self._detach_file(name)
                if current:
                    gone = self._wait_manifest(
                        lambda names: not any(self._full_name(n) in names for n in current), 10)
                    if gone is None:
                        time.sleep(1.5)  # geen overzicht beschikbaar: even afwachten
                    elif gone is False:
                        raise BridgeError("De intent-service gaf de oude intents niet vrij (timeout).")

                for name in changes.removed:
                    self.remove_event(self._full_name(name))
                    self._registered.discard(name)

                for name in wanted:
                    progress(f"Intent registreren: {name}")
                    self._register_file(name)

            if not wanted:
                return "Er zijn geen zinnen om te leren."

            progress("Wachten tot de intent-service klaar is met leren")
            ready = self._wait_manifest(
                lambda names: all(self._full_name(n) in names for n in wanted), timeout)
            if ready is False:
                raise BridgeError("De intent-service heeft de nieuwe intents niet geregistreerd (timeout).")

            # Padatious traint per registratie; wacht tot het even stil is.
            end = time.monotonic() + timeout
            confirmed = False
            while time.monotonic() < end:
                if trained.is_set() and time.monotonic() - last_trained[0] > 1.5:
                    confirmed = True
                    break
                time.sleep(0.25)
        finally:
            self.bus.remove("mycroft.skills.trained", on_trained)

        text = f"{len(wanted)} intent(s) geleerd."
        if not confirmed:
            text += " De intent-service bevestigde het leren niet; test het even om zeker te zijn."
        return text

    def padatious_test(self, utterance):
        try:
            reply = self.bus.wait_for_response(
                Message("intent.service.padatious.get", {"utterance": utterance, "lang": self.language}),
                "intent.service.padatious.reply", timeout=4.0)
        except Exception as exc:
            self.log.warning(f"Padatious-test mislukt: {exc}")
            return {"available": False, "intent": None, "confidence": None}
        if reply is None:
            return {"available": False, "intent": None, "confidence": None}
        intent = reply.data.get("intent") or {}
        name = intent.get("name") or ""
        if not name.startswith(f"{self.skill_id}:"):
            return {"available": True, "intent": None, "confidence": None}
        return {"available": True, "intent": name, "confidence": intent.get("conf")}

    # ---------------------------------------------------------------- herstart
    def schedule_restart(self, delay=1.5):
        """Herstart na een korte pauze, zodat het HTTP-antwoord nog aankomt."""
        threading.Timer(delay, self.restart_service).start()

    def restart_service(self):  # wordt door de varianten ingevuld
        raise NotImplementedError
