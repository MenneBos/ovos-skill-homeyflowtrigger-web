import pytest

from homeyflow.homey import HomeyClient, HomeyError


def test_get_flows_filters_and_sorts(settings):
    flows = HomeyClient(settings).get_flows("kantoor")
    assert [f["name"] for f in flows] == ["Kantoor: check in", "Kantoor: check out"]
    assert all(set(f) == {"id", "name", "enabled"} for f in flows)


def test_get_flows_survives_noise_and_old_format(settings, monkeypatch):
    client = HomeyClient(settings)
    monkeypatch.setenv("FAKE_MODE", "noise")
    assert len(client.get_flows("koffie")) == 1
    monkeypatch.setenv("FAKE_MODE", "old")
    assert client.get_flows("koffie")[0]["id"] == "f3-koffie"


def test_script_failure_becomes_homey_error_without_token(settings, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    with pytest.raises(HomeyError) as info:
        HomeyClient(settings).get_flows("")
    assert "nep-fout" in str(info.value)
    assert settings.homey_token not in str(info.value)


def test_start_flow(settings, tmp_path, monkeypatch):
    log = tmp_path / "started.log"
    monkeypatch.setenv("FAKE_LOG", str(log))
    HomeyClient(settings).start_flow("f3-koffie")
    assert log.read_text().strip() == "f3-koffie"
    with pytest.raises(HomeyError):
        HomeyClient(settings).start_flow("fail")
    with pytest.raises(HomeyError):
        HomeyClient(settings).start_flow("")


def test_timeout(settings, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "hang")
    client = HomeyClient(settings)
    client.START_TIMEOUT = 1
    with pytest.raises(HomeyError, match="timeout"):
        client.start_flow("x")


def test_not_configured(settings):
    settings.homey_token = ""
    with pytest.raises(HomeyError, match="ontbreekt"):
        HomeyClient(settings).get_flows("")
    assert HomeyClient(settings).reachable(ttl=0) == {"configured": False, "reachable": False}


def test_reachable_reports_unreachable(settings):
    result = HomeyClient(settings).reachable(ttl=0)
    assert result == {"configured": True, "reachable": False}
