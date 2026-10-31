import sqlite3

import pytest

from support.builders import USER_A, bodywork, conclude


def test_history_records_decisions_and_tools_and_detects_tampering(harness) -> None:
    """Every decision and tool call is chained, and tampering is detected."""
    result = harness.submit([bodywork(), conclude()])
    names = [event["name"] for event in result["events"]]

    assert names == [
        "received",
        "orchestrator",
        "analyze_bodywork",
        "orchestrator",
        "submit_conclusion",
        "validated",
        "dossier_issued",
    ]

    assert result["events"][1]["output"]["reasoning"] == "Vou acionar a funilaria."
    assert result["historyIntact"] is True
    connection = sqlite3.connect(harness.path)

    with pytest.raises(sqlite3.DatabaseError):
        connection.execute("UPDATE events SET name = 'x'")

    connection.execute("DROP TRIGGER events_no_update")
    connection.execute("UPDATE events SET output = '{}' WHERE name = 'validated'")
    connection.commit()
    connection.close()
    tampered = harness.client.get(f"/api/v1/assessments/{result['id']}", headers=USER_A).json()
    assert tampered["historyIntact"] is False
