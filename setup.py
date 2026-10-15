#!/usr/bin/env python3
import os
from os import path, walk

from setuptools import setup

URL = "https://github.com/MenneBos/ovos-skill-homeyflowtrigger-web"
SKILL_CLAZZ = "HomeyFlowSkill"  # moet overeenkomen met de klasse in __init__.py
PYPI_NAME = "ovos-skill-homeyflowtrigger-web"
SKILL_AUTHOR = "stemcom"
SKILL_PKG = "ovos_skill_homeyflowtrigger_web"
SKILL_ID = f"{PYPI_NAME}.{SKILL_AUTHOR}"  # dit id gebruikt ovos-skill-launcher
PLUGIN_ENTRY_POINT = f"{SKILL_ID}={SKILL_PKG}:{SKILL_CLAZZ}"

BASE_DIR = path.abspath(path.dirname(__file__))


def get_requirements(filename: str):
    with open(path.join(BASE_DIR, filename), "r", encoding="utf-8") as handle:
        requirements = [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]
    if "MYCROFT_LOOSE_REQUIREMENTS" in os.environ:
        requirements = [r.replace("==", ">=").replace("~=", ">=") for r in requirements]
    return requirements


def get_version():
    major = minor = build = alpha = None
    with open(path.join(BASE_DIR, "version.py")) as handle:
        for line in handle:
            if "VERSION_MAJOR" in line:
                major = line.split("=")[1].strip()
            elif "VERSION_MINOR" in line:
                minor = line.split("=")[1].strip()
            elif "VERSION_BUILD" in line:
                build = line.split("=")[1].strip()
            elif "VERSION_ALPHA" in line:
                alpha = line.split("=")[1].strip()
            if (major and minor and build and alpha) or "# END_VERSION_BLOCK" in line:
                break
    version = f"{major}.{minor}.{build}"
    if int(alpha):
        version += f"a{alpha}"
    return version


def find_locale_files():
    files = []
    locale = path.join(BASE_DIR, "locale")
    for directory, _, names in walk(locale):
        if names:
            files.append(path.join(path.relpath(directory, BASE_DIR), "*"))
    return files


with open(path.join(BASE_DIR, "README.md"), "r", encoding="utf-8") as handle:
    long_description = handle.read()

setup(
    name=PYPI_NAME,
    version=get_version(),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=URL,
    author=SKILL_AUTHOR,
    description="OVOS-skill die Homey-flows start met spraak, met een lokale webserver om de zinnen te beheren",
    license="Apache-2.0",
    install_requires=get_requirements("requirements.txt"),
    include_package_data=True,
    package_dir={
        SKILL_PKG: "",
        f"{SKILL_PKG}.homeyflow": "homeyflow",
        f"{SKILL_PKG}.homeyflow.web": "homeyflow/web",
    },
    packages=[SKILL_PKG, f"{SKILL_PKG}.homeyflow", f"{SKILL_PKG}.homeyflow.web"],
    package_data={
        SKILL_PKG: ["*.json", "nodejs/*.js", "nodejs/package.json"] + find_locale_files(),
        f"{SKILL_PKG}.homeyflow.web": ["templates/*.html", "static/css/*", "static/js/*", "static/img/*"],
    },
    keywords="ovos skill plugin homey",
    entry_points={"ovos.plugin.skill": PLUGIN_ENTRY_POINT},
)
