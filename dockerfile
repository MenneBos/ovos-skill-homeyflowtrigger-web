# Container voor ovos-skill-homeyflowtrigger-web (skill + beheerwebserver op poort 8200)
ARG TAG=latest
FROM docker.io/smartgic/ovos-skill-base:${TAG}

ARG OVOS_USER=ovos
ARG SKILL_DIR=/home/${OVOS_USER}/ovos-skill-homeyflowtrigger-web

USER root

# De basis-image is niet altijd Alpine: ondersteun zowel apk als apt-get.
RUN if command -v apk >/dev/null 2>&1; then \
      apk update && apk add --no-cache nodejs npm curl bash ca-certificates; \
    elif command -v apt-get >/dev/null 2>&1; then \
      apt-get update \
      && apt-get install -y --no-install-recommends nodejs npm curl bash ca-certificates \
      && rm -rf /var/lib/apt/lists/*; \
    else \
      echo "Geen apk of apt-get gevonden in de basis-image" >&2; exit 1; \
    fi

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/usr/local/bin:$PATH"

WORKDIR ${SKILL_DIR}
COPY . .

# In de container hoort de containervariant van de skill de entry-point te zijn.
RUN cp __init__container.py __init__.py

# Python-afhankelijkheden (zelfde werkwijze als de originele skill) en de Node.js-module
RUN pip install --upgrade pip \
 && pip install -e . \
 && uv pip install -U ovos-workshop \
 && cd nodejs && npm install --omit=dev --no-audit --no-fund

RUN chown -R ${OVOS_USER}:${OVOS_USER} ${SKILL_DIR}

USER ${OVOS_USER}

EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8200/healthz || exit 1

WORKDIR ${SKILL_DIR}
CMD ["ovos-skill-launcher", "ovos-skill-homeyflowtrigger-web.stemcom"]
