import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.schemas import PatientInput, PatientRecord, Prediction


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    date_of_birth TEXT NOT NULL,
                    email TEXT NOT NULL,
                    glucose REAL NOT NULL,
                    haemoglobin REAL NOT NULL,
                    cholesterol REAL NOT NULL,
                    ai_consent INTEGER NOT NULL,
                    remarks TEXT NOT NULL,
                    prediction_source TEXT NOT NULL,
                    prediction_status TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_test INTEGER UNIQUE
                )"""
            )

    def list_patients(self) -> list[PatientRecord]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM patients ORDER BY id DESC").fetchall()
        return [self.to_record(row) for row in rows]

    @staticmethod
    def to_record(row: sqlite3.Row) -> PatientRecord:
        values = dict(row)
        values.pop("source_test", None)
        return PatientRecord(**values)

    def get_patient(self, patient_id: int) -> PatientRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM patients WHERE id = ?", (patient_id,)
            ).fetchone()
        return self.to_record(row) if row else None

    def get_source_patient(self, test_number: int) -> PatientRecord | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM patients WHERE source_test = ?", (test_number,)
            ).fetchone()
        return self.to_record(row) if row else None

    def save(
        self,
        patient: PatientInput,
        prediction: Prediction,
        patient_id: int | None = None,
        source_test: int | None = None,
    ) -> PatientRecord | None:
        timestamp = datetime.now(UTC).isoformat()
        values = patient.model_dump(mode="json")
        values.update(
            remarks=prediction.remarks,
            prediction_source=prediction.source,
            prediction_status=prediction.status,
            risk=prediction.risk,
            updated_at=timestamp,
        )
        with self.connection() as connection:
            if patient_id is None:
                values.update(created_at=timestamp, source_test=source_test)
                columns = ", ".join(values)
                placeholders = ", ".join("?" for _ in values)
                cursor = connection.execute(
                    f"INSERT INTO patients ({columns}) VALUES ({placeholders})",
                    tuple(values.values()),
                )
                patient_id = cursor.lastrowid
            else:
                assignments = ", ".join(f"{column} = ?" for column in values)
                cursor = connection.execute(
                    f"UPDATE patients SET {assignments} WHERE id = ?",
                    (*values.values(), patient_id),
                )
                if cursor.rowcount == 0:
                    return None
            row = connection.execute(
                "SELECT * FROM patients WHERE id = ?", (patient_id,)
            ).fetchone()
        return self.to_record(row)

    def delete(self, patient_id: int) -> bool:
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        return cursor.rowcount > 0
