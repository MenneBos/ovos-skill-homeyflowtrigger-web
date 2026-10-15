import json

import pytest

from homeyflow.mappings import (MappingError, MappingStore, NotFoundError, ValidationError,
                                clean_sentences, intent_stems, slugify, training_fingerprint)


def test_slugify_is_stable_and_safe():
    assert slugify("Kantoor: check in") == "kantoor_check_in"
    assert slugify("Gordijnen open (slaapkamer)") == "gordijnen_open_slaapkamer"
    assert slugify("../../etc/passwd") == "etcpasswd"
    assert slugify("Café Ünïcode") == "cafe_unicode"
    assert slugify("!!!") == "flow"
    for name in ["Kantoor: check in", "a  b", "x-y_z", "Ünï"]:
        assert slugify(slugify(name)) == slugify(name)


def test_intent_stems_are_unique():
    stems = intent_stems({"a b": {}, "a_b": {}, "A-B": {}, "a!b": {}})
    assert len(set(stems.values())) == 4


def test_clean_sentences():
    assert clean_sentences(["  Ja  ", "ja", "", "Nee"]) == ["Ja", "Nee"]
    with pytest.raises(ValidationError):
        clean_sentences(["met {accolade}"])
    with pytest.raises(ValidationError):
        clean_sentences(["# commentaar"])
    with pytest.raises(ValidationError):
        clean_sentences(["x" * 201])
    with pytest.raises(ValidationError):
        clean_sentences("geen lijst")


def test_set_sentences_keeps_extra_fields(store):
    store.set_sentences("kantoor_check_in", ["nieuw"])
    data = json.loads(store.path.read_text())
    assert data["kantoor_check_in"]["favorite_flow"] == "yes"
    assert data["kantoor_check_in"]["title"] == "Kantoor: check in"
    assert data["kantoor_check_in"]["sentences"] == ["nieuw"]


def test_unknown_flow(store):
    with pytest.raises(NotFoundError):
        store.set_sentences("bestaat_niet", ["x"])
    with pytest.raises(NotFoundError):
        store.delete_flow("bestaat_niet")


def test_add_flows_skips_known_ids_and_makes_unique_keys(store):
    added = store.add_flows([
        {"id": "f1-kantoor-in", "name": "Kantoor: check in"},      # bestaat al (zelfde id)
        {"id": "nieuw-1", "name": "Koffie zetten"},
        {"id": "nieuw-2", "name": "Koffie zetten"},                # zelfde naam, ander id
    ])
    assert added == ["koffie_zetten", "koffie_zetten_2"]
    assert store.load()["koffie_zetten"]["title"] == "Koffie zetten"
    with pytest.raises(ValidationError):
        store.add_flows([{"id": "", "name": "x"}])


def test_save_is_atomic_and_keeps_pruned_backups(tmp_path):
    store = MappingStore(tmp_path / "m.json", tmp_path / "b", keep_backups=3)
    store.save({"a": {"id": "1", "sentences": []}})
    for i in range(8):
        store.save({"a": {"id": "1", "sentences": [f"zin {i}"]}})
    assert len(store.list_backups()) == 3
    assert not list(tmp_path.glob("*.tmp"))
    assert store.save({"a": {"id": "1", "sentences": ["zin 7"]}}) is False  # niets veranderd


def test_corrupt_file_gives_clear_error(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{kapot")
    with pytest.raises(MappingError):
        MappingStore(path).load()
    path.write_text("[]")
    with pytest.raises(MappingError):
        MappingStore(path).load()


def test_fingerprint_changes_with_sentences_only(store):
    base = training_fingerprint(store.load())
    store.add_flows([{"id": "x", "name": "Leeg"}])  # flow zonder zinnen telt niet mee
    assert training_fingerprint(store.load()) == base
    store.set_sentences("kantoor_check_in", ["anders"])
    assert training_fingerprint(store.load()) != base
