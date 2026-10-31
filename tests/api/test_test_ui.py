def test_test_ui_is_served(harness) -> None:
    """The test page is available from the API, on the same origin."""
    response = harness.client.get("/test-ui/")

    assert response.status_code == 200
    assert "Teste do agente" in response.text
