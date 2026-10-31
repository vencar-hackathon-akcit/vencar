import os
import sqlite3
import subprocess
import sys

from vencar.adapters.database.sqlite_assessment_repository import SqliteAssessmentRepository
from vencar.domain.models import AssessmentStatus, VehicleData


def assign_runner(path, assessment_id: str, pid: int | None) -> None:
    """Record which process is working on an assessment."""
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE assessments SET runner_pid = ? WHERE id = ?", (pid, assessment_id)
        )


def finished_process_pid() -> int:
    """Run a process to its end and return its id."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()

    return process.pid


def test_startup_keeps_runs_of_live_servers_and_fails_the_others(tmp_path) -> None:
    """Only runs whose server has stopped are marked as failed."""
    path = tmp_path / "vencar.db"
    repository = SqliteAssessmentRepository(path)
    ids = {name: repository.create("o", VehicleData(), "x").id for name in range(4)}
    assign_runner(path, ids[0], os.getppid())
    assign_runner(path, ids[1], finished_process_pid())
    assign_runner(path, ids[2], None)

    repository.fail_interrupted()

    statuses = {name: repository.get(ids[name], "o").status for name in ids}

    assert statuses[0] == AssessmentStatus.PROCESSING
    assert statuses[1] == AssessmentStatus.FAILED
    assert statuses[2] == AssessmentStatus.FAILED
    assert statuses[3] == AssessmentStatus.FAILED


def test_existing_database_gains_the_runner_column(tmp_path) -> None:
    """A database created before this change is upgraded when opened."""
    path = tmp_path / "vencar.db"

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE assessments (id TEXT PRIMARY KEY, owner TEXT, plate TEXT, "
            "vehicle TEXT, description TEXT, status TEXT, dossier TEXT, error TEXT, "
            "created_at TEXT, updated_at TEXT)"
        )
        connection.execute("INSERT INTO assessments (id, status) VALUES ('a', 'processing')")

    repository = SqliteAssessmentRepository(path)
    repository.fail_interrupted()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT status FROM assessments").fetchone()[0] == "failed"
