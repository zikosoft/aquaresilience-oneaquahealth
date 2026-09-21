def test_ai_provider_secret_is_never_returned(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    put_resp = client.put(
        "/api/v1/settings/ai-provider/config",
        headers=headers,
        json={
            "provider": "anthropic",
            "model": "claude-3-5-haiku-latest",
            "api_key": "super-secret-value-should-never-leak",
            "max_output_tokens": 512,
            "scheduled_analysis_interval_minutes": 240,
            "daily_request_ceiling": 6,
            "event_triggered_enabled": False,
            "cooldown_seconds": 900,
        },
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["is_configured"] is True
    assert "api_key" not in put_resp.text
    assert "super-secret-value-should-never-leak" not in put_resp.text

    get_resp = client.get("/api/v1/settings/ai-provider/config", headers=headers)
    assert get_resp.status_code == 200
    assert "api_key" not in get_resp.text
    assert "super-secret-value-should-never-leak" not in get_resp.text
    assert get_resp.json()["is_configured"] is True


def test_ai_provider_config_has_a_valid_default_model_out_of_the_box(client, admin_token):
    """Regression test: the lazily-created AIProviderConfig row used to default
    `model` to an empty string, which then failed AIProviderConfigUpdate's own
    `min_length=1` validation — so simply opening Settings > AI Provider on a
    fresh install and saving an API key (the obvious first action, without
    also typing a model name) would 422 on a completely unmodified platform."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    get_resp = client.get("/api/v1/settings/ai-provider/config", headers=headers)
    assert get_resp.status_code == 200
    default_model = get_resp.json()["model"]
    assert default_model != ""

    put_resp = client.put(
        "/api/v1/settings/ai-provider/config",
        headers=headers,
        json={
            "provider": get_resp.json()["provider"],
            "model": default_model,
            "api_key": "another-secret-value",
        },
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["is_configured"] is True


def test_generic_settings_roundtrip(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.put(
        "/api/v1/settings/risk_engine/risk_engine",
        headers=headers,
        json={"value": {"weights": {"rainfall": 0.4}, "thresholds": {"low": 20}}},
    )
    assert resp.status_code == 200
    assert resp.json()["value"]["weights"]["rainfall"] == 0.4
