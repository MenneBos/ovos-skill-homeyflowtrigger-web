import json

import pytest

from homeyflow.mappings import ValidationError
from homeyflow.messages import MessageStore, clean_message, say


def make(tmp_path, language="nl-nl"):
    return MessageStore(tmp_path / "cfg" / "spoken_messages.json", language)


def test_default_started_message_is_short(tmp_path):
    store = make(tmp_path)
    assert store.render("started", flow="Licht") == "Gedaan."
    assert make(tmp_path, "en-us").render("started", flow="Light") == "Done."
    assert say("nl-nl", "started", flow="x") == "Gedaan."


def test_custom_text_and_placeholder(tmp_path):
    store = make(tmp_path)
    store.update({"started": "Oké, {flow} is aan"})
    assert store.render("started", flow="Licht") == "Oké, Licht is aan"
    # andere meldingen blijven standaard
    assert store.render("no_match", utterance="blabla") == "Ik weet niet welke actie ik moet uitvoeren voor 'blabla'."


def test_empty_started_is_silent_but_other_keys_cannot_be_empty(tmp_path):
    store = make(tmp_path)
    store.update({"started": ""})
    assert store.render("started", flow="x") == ""
    with pytest.raises(ValidationError):
        store.update({"error": "   "})


def test_reset_with_none_and_same_as_default_removes_entry(tmp_path):
    store = make(tmp_path)
    store.update({"started": "Klaar"})
    assert store.path.exists() and "Klaar" in store.path.read_text(encoding="utf-8")
    store.update({"started": None})
    assert json.loads(store.path.read_text(encoding="utf-8")) == {}
    store.update({"started": "Gedaan."})  # gelijk aan standaard
    assert json.loads(store.path.read_text(encoding="utf-8")) == {}
    assert [m for m in store.overview() if m["key"] == "started"][0]["custom"] is False


@pytest.mark.parametrize("key,text", [
    ("started", "Hallo {naam}"),            # onbekend invulveld
    ("started", "Hallo {flow!r}"),          # conversie
    ("started", "Hallo {flow:>10}"),        # opmaak
    ("started", "Hallo {0}"),               # positioneel
    ("started", "Hallo {flow.__class__}"),  # attribuut
    ("started", "Hallo {flow"),             # onvolledig
    ("started", "Hallo }"),
    ("started", "Hallo {{flow}}"),          # escape wordt niet toegestaan
    ("settings_error", "Fout {flow}"),      # geen invulvelden bij deze melding
    ("started", "regel1\nregel2"),
    ("started", "x" * 201),
    ("bestaat_niet", "x"),
])
def test_invalid_messages_are_rejected_and_nothing_is_saved(tmp_path, key, text):
    store = make(tmp_path)
    with pytest.raises(ValidationError):
        store.update({"no_match": "geldig {utterance}", key: text})
    assert not store.path.exists()


def test_whitespace_is_normalised():
    assert clean_message("started", "  Gedaan   hoor  ") == "Gedaan hoor"


def test_broken_or_invalid_file_falls_back_to_defaults(tmp_path):
    store = make(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{kapot", encoding="utf-8")
    assert store.render("started", flow="x") == "Gedaan."
    store.path.write_text(json.dumps({"started": "Hoi {onbekend}", "error": "Mis met {flow}"}), encoding="utf-8")
    assert store.render("started", flow="x") == "Gedaan."          # ongeldige tekst genegeerd
    assert store.render("error", flow="Licht") == "Mis met Licht"  # geldige blijft


def test_overview_lists_all_keys_in_order(tmp_path):
    keys = [m["key"] for m in make(tmp_path).overview()]
    assert keys == ["started", "no_match", "no_id", "error", "settings_error"]
