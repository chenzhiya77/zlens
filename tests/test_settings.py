"""VLM settings endpoints: read, save, keep-key-on-empty, test connection, and
screenshot price extraction (VLM calls mocked — no real external requests)."""


def test_get_vlm_settings_defaults_unconfigured(client_factory):
    body = client_factory(rows=[]).get("/api/settings/vlm").json()

    assert body == {"base_url": "", "model": "", "api_key_configured": False}


def test_put_vlm_settings_persists_and_never_echoes_key(client_factory):
    client = client_factory(rows=[])

    client.put(
        "/api/settings/vlm",
        json={
            "base_url": "https://api.siliconflow.cn/v1",
            "model": "Qwen/Qwen3-VL-30B-A3B-Instruct",
            "api_key": "sk-test-secret",
        },
    )
    body = client.get("/api/settings/vlm").json()

    assert body["base_url"] == "https://api.siliconflow.cn/v1"
    assert body["model"] == "Qwen/Qwen3-VL-30B-A3B-Instruct"
    assert body["api_key_configured"] is True
    assert "api_key" not in body  # never echo the secret


def test_put_vlm_empty_key_keeps_stored_one(client_factory):
    client = client_factory(rows=[])
    client.put("/api/settings/vlm", json={"api_key": "sk-keep-me"})

    client.put("/api/settings/vlm", json={"model": "other-model", "api_key": ""})
    body = client.get("/api/settings/vlm").json()

    assert body["model"] == "other-model"
    assert body["api_key_configured"] is True


def test_vlm_test_without_config_returns_503(client_factory):
    response = client_factory(rows=[]).post("/api/settings/vlm/test")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vlm_unconfigured"


def test_vlm_test_with_config_calls_model(client_factory, monkeypatch):
    from zlens.api.routers import settings as settings_router

    calls: list[str] = []

    def fake_chat(settings, *, text=None, image_base64=None):
        calls.append(text or "")
        return "OK"

    monkeypatch.setattr(settings_router, "chat", fake_chat)

    client = client_factory(rows=[])
    client.put(
        "/api/settings/vlm",
        json={"base_url": "http://vlm.test/v1", "model": "m", "api_key": "sk-x"},
    )

    body = client.post("/api/settings/vlm/test").json()

    assert body["ok"] is True
    assert body["reply"] == "OK"
    assert calls  # the model path was reached


def test_pricing_extract_unconfigured_returns_503(client_factory):
    response = client_factory(rows=[]).post("/api/pricing/extract", json={"image_base64": "AAAA"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vlm_unconfigured"


def test_pricing_extract_parses_vlm_json(client_factory, monkeypatch):
    from zlens.core import vlm as vlm_mod

    def fake_chat(settings, *, text=None, image_base64=None):
        return (
            '```json\n{"currency":"USD","unit":"per_1M_tokens","models":['
            '{"model_id":"MiniMax-M3","input":1.5,"output":6.0,'
            '"cache_read":0.15,"cache_write":0}]}\n```'
        )

    monkeypatch.setattr(vlm_mod, "chat", fake_chat)

    client = client_factory(rows=[])
    client.put(
        "/api/settings/vlm",
        json={"base_url": "http://vlm.test/v1", "model": "m", "api_key": "sk-x"},
    )

    body = client.post("/api/pricing/extract", json={"image_base64": "AAAA"}).json()

    assert body["currency"] == "USD"
    assert body["unit"] == "per_1M_tokens"
    assert body["models"] == [
        {
            "model_id": "MiniMax-M3",
            "input": 1.5,
            "output": 6.0,
            "cache_read": 0.15,
            "cache_write": 0,
        }
    ]


def test_pricing_extract_forwards_focus_model(client_factory, monkeypatch):
    from zlens.core import vlm as vlm_mod

    prompts: list[str] = []

    def fake_chat(settings, *, text=None, image_base64=None):
        prompts.append(text or "")
        return (
            '{"currency":"USD","unit":"per_1M_tokens","models":['
            '{"model_id":"demo-model","input":2.5,"output":10.0,"'
            'cache_read":null,"cache_write":null}]}'
        )

    monkeypatch.setattr(vlm_mod, "chat", fake_chat)

    client = client_factory(rows=[])
    client.put(
        "/api/settings/vlm",
        json={"base_url": "http://vlm.test/v1", "model": "m", "api_key": "sk-x"},
    )

    body = client.post(
        "/api/pricing/extract",
        json={"image_base64": "AAAA", "focus_model": "demo-model"},
    ).json()
    client.post("/api/pricing/extract", json={"image_base64": "AAAA"})

    assert body["models"][0]["model_id"] == "demo-model"
    # The targeting hint appears only when focus_model is explicit; a plain
    # request keeps the original prompt (backward compatible).
    assert "demo-model" in prompts[0]
    assert "demo-model" not in prompts[1]


def test_pricing_extract_unparsable_returns_422(client_factory, monkeypatch):
    from zlens.core import vlm as vlm_mod

    monkeypatch.setattr(
        vlm_mod, "chat", lambda settings, *, text=None, image_base64=None: "no json here"
    )

    client = client_factory(rows=[])
    client.put(
        "/api/settings/vlm",
        json={"base_url": "http://vlm.test/v1", "model": "m", "api_key": "sk-x"},
    )

    response = client.post("/api/pricing/extract", json={"image_base64": "AAAA"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "vlm_unparsable"
