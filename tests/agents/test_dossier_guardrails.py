from support.builders import bodywork, conclude, findings


def test_missing_data_never_calls_any_agent(harness) -> None:
    """Without the vehicle's data and photos, the agents are not used."""
    result = harness.submit([], data={"description": "x"}, files=[])
    assert result["status"] == "needs_input"
    assert result["dossier"]["pendingInformation"] == ["make", "model", "year", "plate", "photos"]
    assert harness.model.received == []


def test_unusable_photo_discards_findings_and_requests_a_new_one(harness) -> None:
    """Findings tied only to a bad photo do not survive validation."""
    harness.bodywork.findings = findings(
        photo_assessments=[{"evidence_id": "P1", "usable": False, "reason": "desfocada"}]
    )

    result = harness.submit([bodywork(), conclude()])
    dossier = result["dossier"]
    assert result["status"] == "needs_input"
    assert dossier["damages"] == [] and dossier["score"] is None
    assert any("novas fotos" in question for question in dossier["questions"])


def test_conflict_is_surfaced_to_the_user(harness) -> None:
    """A conflict stops the conclusion instead of being silently resolved."""
    harness.bodywork.findings = findings(
        conflicts=[{"description": "Foto mostra um Onix", "evidence_ids": ["P1"]}]
    )

    result = harness.submit([bodywork(), conclude()])
    assert result["status"] == "needs_input"
    assert any("Onix" in question for question in result["dossier"]["questions"])
