"""Variant voor de container. Het dockerfile kopieert dit bestand over __init__.py."""
import os
import signal
import threading

from . import skill_base as _base


class HomeyFlowSkill(_base.HomeyFlowBaseSkill):
    deploy_mode = "container"

    def restart_service(self):
        # De container herstart zichzelf via `restart: unless-stopped` (geen Docker-socket nodig).
        self.log.info("Skill stopt; Docker start de container opnieuw.")
        threading.Timer(10, lambda: os._exit(1)).start()  # vangnet als SIGTERM wordt genegeerd
        os.kill(os.getpid(), signal.SIGTERM)
