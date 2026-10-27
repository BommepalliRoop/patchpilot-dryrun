def test_health_contract_shape(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "llm_mode": "mock", "boomi_mode": "mock", "github_mode": "mock"}


def test_health_reflects_modes(client, monkeypatch):
    from app.core.config import reset_settings_cache

    monkeypatch.setenv("BOOMI_MODE", "live")
    reset_settings_cache()
    assert client.get("/api/health").json()["boomi_mode"] == "live"
