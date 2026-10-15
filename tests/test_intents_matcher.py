import random
from difflib import get_close_matches

from homeyflow.intents import desired_intent_files, sync_intent_files
from homeyflow.matcher import best_match


def test_sync_creates_updates_removes(tmp_path, store):
    mappings = store.load()
    first = sync_intent_files(tmp_path, mappings)
    assert sorted(first.created) == ["kantoor_check_in.intent", "kantoor_check_out.intent"]
    assert (tmp_path / "kantoor_check_in.intent").read_text() == "Ik ben aanwezig op kantoor\nterug op kantoor\n"

    again = sync_intent_files(tmp_path, mappings)
    assert not again.changed and len(again.unchanged) == 2

    mappings["kantoor_check_in"]["sentences"] = ["nieuw"]
    del mappings["kantoor_check_out"]
    (tmp_path / "ouderwets.intent").write_text("oud\n")
    third = sync_intent_files(tmp_path, mappings)
    assert third.updated == ["kantoor_check_in.intent"]
    assert sorted(third.removed) == ["kantoor_check_out.intent", "ouderwets.intent"]
    assert [p.name for p in tmp_path.glob("*.intent")] == ["kantoor_check_in.intent"]


def test_flows_without_sentences_get_no_file(tmp_path):
    mappings = {"leeg": {"id": "1", "sentences": []}, "vol": {"id": "2", "sentences": ["x"]}}
    assert list(desired_intent_files(mappings)) == ["vol.intent"]
    sync_intent_files(tmp_path, mappings)
    assert [p.name for p in tmp_path.glob("*.intent")] == ["vol.intent"]


def test_best_match_basic(store):
    mappings = store.load()
    match = best_match("terug op kantoor", mappings)
    assert match.key == "kantoor_check_in" and match.score == 1.0
    assert best_match("volstrekt iets anders over bananen", mappings) is None
    assert best_match("", mappings) is None


def test_best_match_equals_difflib_original_behaviour():
    rng = random.Random(7)
    words = ["kantoor", "koffie", "licht", "aan", "uit", "gordijnen", "open", "dicht", "ik", "ben", "weg", "terug"]
    for _ in range(200):
        mappings = {}
        for i in range(rng.randint(1, 5)):
            mappings[f"f{i}"] = {"sentences": [" ".join(rng.sample(words, rng.randint(1, 4)))
                                               for _ in range(rng.randint(1, 3))]}
        utterance = " ".join(rng.sample(words, rng.randint(1, 4)))
        sentence_to_flow = {}
        for key, entry in mappings.items():
            for sentence in entry["sentences"]:
                sentence_to_flow[sentence.lower()] = key
        expected = get_close_matches(utterance, list(sentence_to_flow), n=1, cutoff=0.6)
        got = best_match(utterance, mappings)
        assert (got.sentence if got else None) == (expected[0] if expected else None)
