import time

JSON_HEADERS = {"Content-Type": "application/json"}


def put(client, url, body, **kw):
    return client.put(url, json=body, headers=kw.get("headers", JSON_HEADERS))


def test_pages_render(client):
    for url in ["/", "/flows", "/healthz", "/static/css/app.css", "/static/js/flows.js", "/static/img/logo.png"]:
        assert client.get(url).status_code == 200, url
    assert b"HomeyFlowTrigger" in client.get("/").data
    assert client.get("/bestaat-niet").status_code == 404
    assert client.get("/api/bestaat-niet").get_json()["error"]


def test_flows_list_and_edit(client):
    data = client.get("/api/flows").get_json()
    assert [f["key"] for f in data["flows"]] == ["kantoor_check_in", "kantoor_check_out"]
    assert data["flows"][0]["title"] == "Kantoor: check in"
    assert data["flows"][1]["title"] == "kantoor check out"

    reply = put(client, "/api/flows/kantoor_check_in", {"sentences": ["  hallo ", "HALLO", "wereld"]}).get_json()
    assert reply["flow"]["sentences"] == ["hallo", "wereld"]
    assert reply["dirty"] is True

    assert put(client, "/api/flows/kantoor_check_in", {"sentences": ["x{y}"]}).status_code == 400
    assert put(client, "/api/flows/onbekend", {"sentences": []}).status_code == 404
    assert put(client, "/api/flows/kantoor_check_in", {"nope": 1}).status_code == 400


def test_add_and_delete_flow(client):
    reply = client.post("/api/flows", json={"flows": [{"id": "f3-koffie", "name": "Koffie zetten"}]}, headers=JSON_HEADERS)
    assert reply.status_code == 201 and reply.get_json()["added"] == ["koffie_zetten"]
    again = client.post("/api/flows", json={"flows": [{"id": "f3-koffie", "name": "Koffie zetten"}]}, headers=JSON_HEADERS)
    assert again.status_code == 200 and again.get_json()["added"] == []
    assert client.post("/api/flows", json={"nope": 1}, headers=JSON_HEADERS).status_code == 400

    deleted = client.delete("/api/flows/koffie_zetten", headers=JSON_HEADERS).get_json()
    assert "koffie_zetten" not in [f["key"] for f in deleted["flows"]]


def test_homey_search_marks_added(client):
    data = client.get("/api/homey/flows?q=kantoor").get_json()
    assert [f["name"] for f in data["flows"]] == ["Kantoor: check in", "Kantoor: check out"]
    assert all(f["added"] for f in data["flows"])
    data = client.get("/api/homey/flows?q=koffie").get_json()
    assert data["flows"][0]["added"] is False


def test_homey_errors_are_reported(client, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    reply = client.get("/api/homey/flows?q=x")
    assert reply.status_code == 502 and "nep-fout" in reply.get_json()["error"]


def test_learn_flow(client, bridge, store):
    assert client.get("/api/status").get_json()["training"]["dirty"] is True
    assert client.post("/api/learn", json={}, headers=JSON_HEADERS).status_code == 400  # geen bevestiging

    started = client.post("/api/learn", json={"confirm": True}, headers=JSON_HEADERS)
    assert started.status_code == 202
    for _ in range(100):
        status = client.get("/api/learn").get_json()
        if status["state"] not in ("running", "idle"):
            break
        time.sleep(0.05)
    assert status["state"] == "done", status
    assert status["dirty"] is False and "2 intent(s) geleerd" in status["message"]
    assert bridge.registered == 2

    put(client, "/api/flows/kantoor_check_in", {"sentences": ["iets anders"]})
    assert client.get("/api/status").get_json()["training"]["dirty"] is True


def test_learn_failure_is_shown_and_keeps_dirty(client, bridge):
    bridge.fail = "De intent-service reageert niet."
    client.post("/api/learn", json={"confirm": True}, headers=JSON_HEADERS)
    for _ in range(100):
        status = client.get("/api/learn").get_json()
        if status["state"] != "running":
            break
        time.sleep(0.05)
    assert status["state"] == "error" and "reageert niet" in status["message"]
    assert status["dirty"] is True


def test_test_endpoint_and_confirmation(client, tmp_path, monkeypatch):
    log = tmp_path / "started.log"
    monkeypatch.setenv("FAKE_LOG", str(log))
    result = client.post("/api/test", json={"utterance": "terug op kantoor"}, headers=JSON_HEADERS).get_json()
    assert result["fuzzy"]["status"] == "matched" and result["fuzzy"]["flow"] == "kantoor_check_in"
    assert result["padatious"]["flow"] == "kantoor_check_in"
    assert not log.exists()  # alleen zoeken start niets

    assert client.post("/api/test", json={"utterance": "terug op kantoor", "run": True}, headers=JSON_HEADERS).status_code == 400
    assert not log.exists()
    run = client.post("/api/test", json={"utterance": "terug op kantoor", "run": True, "confirm": True}, headers=JSON_HEADERS).get_json()
    assert run["fuzzy"]["status"] == "started" and log.read_text().strip() == "f1-kantoor-in"

    nothing = client.post("/api/test", json={"utterance": "bananen en appels"}, headers=JSON_HEADERS).get_json()
    assert nothing["fuzzy"]["status"] == "no_match"
    assert client.post("/api/test", json={"utterance": "  "}, headers=JSON_HEADERS).status_code == 400


def test_padatious_unavailable(client, bridge):
    bridge.padatious_available = False
    result = client.post("/api/test", json={"utterance": "terug op kantoor"}, headers=JSON_HEADERS).get_json()
    assert result["padatious"]["available"] is False


def test_restart_needs_confirmation(client, bridge):
    assert client.post("/api/restart", json={}, headers=JSON_HEADERS).status_code == 400
    assert bridge.restarted is False
    assert client.post("/api/restart", json={"confirm": True}, headers=JSON_HEADERS).status_code == 200
    assert bridge.restarted is True


# ---- beveiliging zonder wachtwoord ----
def test_cross_site_requests_are_refused(client):
    url = "/api/flows/kantoor_check_in"
    body = {"sentences": ["hack"]}
    assert client.put(url, json=body, headers={**JSON_HEADERS, "Origin": "https://evil.example"}).status_code == 403
    assert client.put(url, json=body, headers={**JSON_HEADERS, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    # formulier-achtige verzoeken (geen JSON) worden geweigerd
    assert client.put(url, data="sentences=hack", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 415
    # zelfde herkomst mag wel
    ok = client.put(url, json=body, headers={**JSON_HEADERS, "Origin": "http://localhost"})
    assert ok.status_code == 200


def test_dns_rebinding_hosts_are_refused(client):
    assert client.get("/api/flows", headers={"Host": "evil.example.com"}).status_code == 403
    for host in ["localhost:8200", "192.168.1.20:8200", "[::1]:8200", "jarvis", "jarvis.local", "ovos.tail1234.ts.net",
                 "100.64.0.5"]:
        assert client.get("/api/flows", headers={"Host": host}).status_code == 200, host


def test_allowed_hosts_setting(settings, store, bridge, tmp_path):
    from homeyflow.homey import HomeyClient
    from homeyflow.web import create_app
    settings.allowed_hosts = ["jarvis.mijnnaam.nl"]
    app = create_app(settings, bridge=bridge, homey=HomeyClient(settings), store=store, intent_dir=tmp_path / "i")
    assert app.test_client().get("/api/flows", headers={"Host": "jarvis.mijnnaam.nl"}).status_code == 200


def test_security_headers_and_no_token_leak(client, settings):
    response = client.get("/api/status")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    for url in ["/api/status", "/api/flows", "/", "/flows"]:
        assert settings.homey_token.encode() not in client.get(url).data
