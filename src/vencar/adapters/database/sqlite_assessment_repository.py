import json
import os
import sqlite3
from pathlib import Path

from vencar.domain.models import (
    AgentEvent,
    Assessment,
    AssessmentStatus,
    Dossier,
    NewEvent,
    Photo,
    VehicleData,
)
from vencar.utils.hashing import sha256_hex
from vencar.utils.ids import new_id
from vencar.utils.serialization import to_json
from vencar.utils.time import utc_now

INTERRUPTED_MESSAGE = "Processamento interrompido; envie uma nova resposta para tentar de novo."
GENESIS_HASH = "0" * 64
IDLE_STATES = (
    AssessmentStatus.COMPLETED,
    AssessmentStatus.NEEDS_INPUT,
    AssessmentStatus.INCONCLUSIVE,
    AssessmentStatus.FAILED,
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    plate TEXT NOT NULL,
    vehicle TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    dossier TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS assessments_owner ON assessments(owner, created_at);
CREATE INDEX IF NOT EXISTS assessments_plate ON assessments(plate, owner);
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL REFERENCES assessments(id),
    position INTEGER NOT NULL,
    evidence_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id TEXT NOT NULL REFERENCES assessments(id),
    run INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    input TEXT NOT NULL,
    output TEXT NOT NULL,
    created_at TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;
"""


class SqliteAssessmentRepository:
    """Outbound adapter that implements the repository port with SQLite."""

    def __init__(self, path: Path) -> None:
        """Open the database file and create the schema when needed."""
        self.path = path

        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = [row["name"] for row in connection.execute("PRAGMA table_info(assessments)")]

            if "runner_pid" not in columns:
                connection.execute("ALTER TABLE assessments ADD COLUMN runner_pid INTEGER")

    def connect(self) -> sqlite3.Connection:
        """Open one connection per operation, since agents run in worker threads."""
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        return connection

    def to_assessment(self, row: sqlite3.Row) -> Assessment:
        """Convert a database row into a domain object."""
        return Assessment(
            id=row["id"],
            owner=row["owner"],
            vehicle=VehicleData.model_validate_json(row["vehicle"]),
            description=row["description"],
            status=row["status"],
            dossier=Dossier.model_validate_json(row["dossier"]) if row["dossier"] else None,
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, owner: str, vehicle: VehicleData, description: str) -> Assessment:
        """Create an assessment in the processing state."""
        assessment_id = new_id()
        now = utc_now()

        with self.connect() as connection:
            connection.execute(
                "INSERT INTO assessments "
                "(id, owner, plate, vehicle, description, status, runner_pid, created_at, "
                "updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assessment_id,
                    owner,
                    vehicle.plate,
                    vehicle.model_dump_json(),
                    description,
                    AssessmentStatus.PROCESSING,
                    os.getpid(),
                    now,
                    now,
                ),
            )

        return self.get(assessment_id, owner)

    def get(self, assessment_id: str, owner: str) -> Assessment | None:
        """Return an assessment only if it belongs to the owner."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assessments WHERE id = ? AND owner = ?", (assessment_id, owner)
            ).fetchone()

        return self.to_assessment(row) if row else None

    def list_by_owner(self, owner: str) -> list[Assessment]:
        """Return the owner's assessments, newest first."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM assessments WHERE owner = ? ORDER BY created_at DESC", (owner,)
            ).fetchall()

        return [self.to_assessment(row) for row in rows]

    def add_photo(self, assessment_id: str, photo: Photo) -> None:
        """Attach a stored photo to an assessment."""
        with self.connect() as connection:
            position = connection.execute(
                "SELECT COUNT(*) FROM photos WHERE assessment_id = ?", (assessment_id,)
            ).fetchone()[0]

            connection.execute(
                "INSERT INTO photos (id, assessment_id, position, evidence_id, filename, path) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (photo.id, assessment_id, position, photo.evidence_id, photo.filename, photo.path),
            )

    def list_photos(self, assessment_id: str) -> list[Photo]:
        """Return the photos of an assessment in upload order."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM photos WHERE assessment_id = ? ORDER BY position", (assessment_id,)
            ).fetchall()

        return [
            Photo(
                id=row["id"],
                evidence_id=row["evidence_id"],
                filename=row["filename"],
                path=row["path"],
            )
            for row in rows
        ]

    def append_event(self, assessment_id: str, run: int, event: NewEvent) -> None:
        """Append an event linked by hash to the previous event of the assessment."""
        input_json = to_json(event.input)
        output_json = to_json(event.output)
        created_at = utc_now()
        kind = event.kind.value
        name = str(event.name)
        connection = self.connect()

        try:
            connection.execute("BEGIN IMMEDIATE")

            last = connection.execute(
                "SELECT hash FROM events WHERE assessment_id = ? ORDER BY id DESC LIMIT 1",
                (assessment_id,),
            ).fetchone()

            previous = last["hash"] if last else GENESIS_HASH

            digest = self.event_hash(
                previous, assessment_id, run, kind, name, input_json, output_json, created_at
            )

            connection.execute(
                "INSERT INTO events "
                "(assessment_id, run, kind, name, input, output, created_at, previous_hash, hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assessment_id,
                    run,
                    kind,
                    name,
                    input_json,
                    output_json,
                    created_at,
                    previous,
                    digest,
                ),
            )

            connection.commit()
        finally:
            connection.close()

    def list_events(self, assessment_id: str) -> list[AgentEvent]:
        """Return the history of an assessment, oldest first."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE assessment_id = ? ORDER BY id", (assessment_id,)
            ).fetchall()

        return [
            AgentEvent(
                run=row["run"],
                kind=row["kind"],
                name=row["name"],
                input=json.loads(row["input"]),
                output=json.loads(row["output"]),
                created_at=row["created_at"],
                hash=row["hash"],
            )
            for row in rows
        ]

    def history_is_intact(self, assessment_id: str) -> bool:
        """Recalculate the hash chain to detect any change to the history."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE assessment_id = ? ORDER BY id", (assessment_id,)
            ).fetchall()

        previous = GENESIS_HASH

        for row in rows:
            expected = self.event_hash(
                previous,
                assessment_id,
                row["run"],
                row["kind"],
                row["name"],
                row["input"],
                row["output"],
                row["created_at"],
            )

            if row["previous_hash"] != previous or row["hash"] != expected:
                return False

            previous = row["hash"]

        return True

    def highest_run(self, assessment_id: str) -> int:
        """Return the highest run recorded, or zero when there is none."""
        with self.connect() as connection:
            return connection.execute(
                "SELECT COALESCE(MAX(run), 0) FROM events WHERE assessment_id = ?", (assessment_id,)
            ).fetchone()[0]

    def next_run(self, assessment_id: str) -> int:
        """Return the number of the next agent run."""
        return self.highest_run(assessment_id) + 1

    def latest_run(self, assessment_id: str) -> int:
        """Return the most recent run, treating a case with no runs as run one."""
        return max(self.highest_run(assessment_id), 1)

    def begin_rerun(self, assessment_id: str, vehicle: VehicleData) -> bool:
        """Atomically move an idle assessment back to processing."""
        marks = ", ".join("?" for _ in IDLE_STATES)

        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE assessments "
                "SET status = ?, plate = ?, vehicle = ?, error = NULL, runner_pid = ?, "
                "updated_at = ? "
                f"WHERE id = ? AND status IN ({marks})",
                (
                    AssessmentStatus.PROCESSING,
                    vehicle.plate,
                    vehicle.model_dump_json(),
                    os.getpid(),
                    utc_now(),
                    assessment_id,
                    *IDLE_STATES,
                ),
            )

        return cursor.rowcount == 1

    def finish(self, assessment_id: str, dossier: Dossier) -> None:
        """Store a dossier and move the assessment to its status."""
        with self.connect() as connection:
            connection.execute(
                "UPDATE assessments "
                "SET status = ?, dossier = ?, error = NULL, updated_at = ? "
                "WHERE id = ?",
                (dossier.status, dossier.model_dump_json(), utc_now(), assessment_id),
            )

    def fail(self, assessment_id: str, error: str) -> None:
        """Mark an assessment as failed."""
        with self.connect() as connection:
            connection.execute(
                "UPDATE assessments SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (AssessmentStatus.FAILED, error, utc_now(), assessment_id),
            )

    @staticmethod
    def process_is_running(pid: int | None) -> bool:
        """Tell whether another live process may still be working on a run."""
        if pid is None or pid == os.getpid():
            return False

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

        return True

    def fail_interrupted(self) -> None:
        """Fail only the runs whose server has stopped, leaving other live servers alone."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, runner_pid FROM assessments WHERE status = ?",
                (AssessmentStatus.PROCESSING,),
            ).fetchall()

            for row in rows:
                if not self.process_is_running(row["runner_pid"]):
                    connection.execute(
                        "UPDATE assessments SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                        (AssessmentStatus.FAILED, INTERRUPTED_MESSAGE, utc_now(), row["id"]),
                    )

    def previous_dossiers(self, plate: str, owner: str, exclude_id: str) -> list[Assessment]:
        """Return the owner's earlier finished assessments of the same plate."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM assessments "
                "WHERE plate = ? AND owner = ? AND id != ? AND status = ? "
                "ORDER BY created_at",
                (plate, owner, exclude_id, AssessmentStatus.COMPLETED),
            ).fetchall()

        return [self.to_assessment(row) for row in rows]

    @staticmethod
    def event_hash(
        previous_hash: str,
        assessment_id: str,
        run: int,
        kind: str,
        name: str,
        input_json: str,
        output_json: str,
        created_at: str,
    ) -> str:
        """Hash an event together with the previous one, forming a chain."""
        payload = json.dumps(
            [previous_hash, assessment_id, run, kind, name, input_json, output_json, created_at]
        )

        return sha256_hex(payload)
