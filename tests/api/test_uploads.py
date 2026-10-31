from support.builders import UNO, USER_A


def test_invalid_upload_creates_nothing(harness) -> None:
    """A file that is not an image is rejected before anything is stored."""
    bad = [("photos", ("x.jpg", b"nope", "image/jpeg"))]

    assert (
        harness.client.post("/api/v1/assessments", data=UNO, files=bad, headers=USER_A).status_code
        == 415
    )

    assert harness.client.get("/api/v1/assessments", headers=USER_A).json() == []
