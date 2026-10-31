from fastapi.testclient import TestClient

from support.builders import USER_A, USER_B


def test_expected_errors_share_one_format(harness) -> None:
    """Application errors return a stable code and a readable message."""
    missing = harness.client.get("/api/v1/assessments/nao-existe", headers=USER_A)
    unauthorized = harness.client.get("/api/v1/assessments")

    assert missing.status_code == 404
    assert missing.json() == {
        "code": "assessment_not_found",
        "message": "Avaliacao nao encontrada.",
    }

    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "unauthorized"


def test_other_users_get_the_same_error_as_a_missing_assessment(harness) -> None:
    """The error does not reveal whether another user's assessment exists."""
    created = harness.submit([], data={"description": "x"}, files=[])

    other_user = harness.client.get(f"/api/v1/assessments/{created['id']}", headers=USER_B)
    nonexistent = harness.client.get("/api/v1/assessments/nao-existe", headers=USER_B)

    assert other_user.status_code == nonexistent.status_code == 404
    assert other_user.json() == nonexistent.json()


def test_validation_errors_name_fields_without_echoing_values(harness) -> None:
    """A malformed request reports the field, not what was sent."""
    response = harness.client.post(
        "/api/v1/assessments", data={"photos": "valor-secreto"}, headers=USER_A
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["fields"]
    assert "valor-secreto" not in response.text


def test_framework_errors_use_the_same_format(harness) -> None:
    """An unknown route is reported in the common format."""
    response = harness.client.get("/rota-inexistente")

    assert response.status_code == 404
    assert response.json()["code"] == "http_error"


def test_unexpected_errors_hide_their_details(harness) -> None:
    """An unexpected failure answers 500 without leaking internals."""
    app = harness.client.app

    @app.get("/falha")
    def fail() -> None:
        """Simulate a bug in the application."""
        raise RuntimeError("detalhe-interno")

    response = TestClient(app, raise_server_exceptions=False).get("/falha")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "detalhe-interno" not in response.text
