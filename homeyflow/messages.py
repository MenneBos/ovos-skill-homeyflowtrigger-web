"""Gesproken antwoorden van de skill (Nederlands en Engels)."""

MESSAGES = {
    "nl-nl": {
        "settings_error": "Er ging iets mis bij het openen van de instellingen.",
        "no_match": "Ik weet niet welke actie ik moet uitvoeren voor '{utterance}'.",
        "no_id": "Ik weet niet welke actie ik moet uitvoeren voor '{flow}'.",
        "started": "De actie '{flow}' is gestart.",
        "error": "Er ging iets mis bij het starten van '{flow}'.",
    },
    "en-us": {
        "settings_error": "Something went wrong while opening the settings.",
        "no_match": "Not sure which flow to start for '{utterance}'.",
        "no_id": "Not sure which flow to start for '{flow}'.",
        "started": "The flow '{flow}' has been started.",
        "error": "Something went wrong while starting the flow '{flow}'.",
    },
}


def say(language: str, key: str, **values) -> str:
    table = MESSAGES.get(language.lower(), MESSAGES["nl-nl"])
    return table[key].format(**values)
