from support.builders import USER_A, USER_B, bodywork, conclude


def test_users_are_isolated(harness) -> None:
    """Another user cannot reach an assessment, its photos or its plate's history."""
    result = harness.submit([bodywork(), conclude()])
    url = f"/api/v1/assessments/{result['id']}"
    photo_id = result["photos"][0]["id"]
    assert harness.client.get(f"{url}/photos/{photo_id}", headers=USER_A).status_code == 200
    assert harness.client.get(url, headers=USER_B).status_code == 404
    assert harness.client.get(f"{url}/photos/{photo_id}", headers=USER_B).status_code == 404
    assert (
        harness.client.post(f"{url}/answers", data={"answer": "x"}, headers=USER_B).status_code
        == 404
    )
    assert harness.client.get("/api/v1/assessments", headers=USER_B).json() == []
    assert harness.client.get("/api/v1/assessments").status_code == 401
    assert "owner" not in result and "path" not in result["photos"][0]
