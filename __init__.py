"""Variant voor een gewone OVOS-installatie (systemd). In de container wordt
__init__container.py hiervoor in de plaats gezet (zie dockerfile)."""
import subprocess

from . import skill_base as _base


class HomeyFlowSkill(_base.HomeyFlowBaseSkill):
    deploy_mode = "systemd"

    def restart_service(self):
        try:
            subprocess.run(["systemctl", "--user", "restart", "ovos.service"], check=True, timeout=60)
            self.log.info("OVOS-service herstart.")
        except Exception as exc:
            self.log.error(f"OVOS-service herstarten mislukt: {exc}")
