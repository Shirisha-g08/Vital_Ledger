import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(database_path=tmp_path / "patients.db"))) as test_client:
        yield test_client


@pytest.fixture
def patient():
    return {
        "full_name": "Robyn Pears",
        "date_of_birth": "28/01/1960",
        "email": "robyn@gmail.com",
        "glucose": 232,
        "haemoglobin": 13.5,
        "cholesterol": 180,
    }


def test_crud_and_persistence(client, patient):
    created = client.post("/api/patients", json=patient)
    assert created.status_code == 201
    record = created.json()
    assert record["prediction_source"] == "local"
    assert record["risk"] == "review"
    patient_id = record["id"]
    assert client.get(f"/api/patients/{patient_id}").json()["full_name"] == "Robyn Pears"
    patient["email"] = "gokul@infocare.com"
    updated = client.put(f"/api/patients/{patient_id}", json=patient)
    assert updated.status_code == 200
    assert updated.json()["email"] == "gokul@infocare.com"
    assert updated.json()["remarks"] == record["remarks"]
    assert len(client.get("/api/patients").json()) == 1
    assert client.delete(f"/api/patients/{patient_id}").status_code == 204
    assert client.get("/api/patients").json() == []
    assert client.get(f"/api/patients/{patient_id}").status_code == 404
    assert client.delete(f"/api/patients/{patient_id}").status_code == 404


def test_database_survives_restart(tmp_path, patient):
    settings = Settings(database_path=tmp_path / "persistent.db")
    with TestClient(create_app(settings)) as first:
        first.post("/api/patients", json=patient)
    with TestClient(create_app(settings)) as second:
        assert len(second.get("/api/patients").json()) == 1


def test_invalid_input_never_calls_predictor(client, patient, monkeypatch):
    def unexpected_call(data):
        pytest.fail("Invalid input must never reach prediction")

    monkeypatch.setattr(client.app.state.predictor, "predict", unexpected_call)
    patient["email"] = "hunter@gmail"
    response = client.post("/api/patients", json=patient)
    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "email"
    assert client.get("/api/patients").json() == []


def test_assessment_errors_and_idempotence(client):
    assert client.post("/api/assessment/run", json={}).status_code == 422
    response = client.post("/api/assessment/run", json={"confirm_mapping": True})
    results = response.json()["results"]
    assert [row["test_number"] for row in results if row["status"] == "rejected"] == [2, 4, 8]
    assert len(results[7]["errors"]) == 2
    assert len(client.get("/api/patients").json()) == 7
    second = client.post("/api/assessment/run", json={"confirm_mapping": True}).json()
    assert sum(row["status"] == "already_imported" for row in second["results"]) == 7
    assert len(client.get("/api/patients").json()) == 7


def test_unconfigured_ai_is_not_presented_as_ai(client, patient):
    patient["ai_consent"] = True
    record = client.post("/api/patients", json=patient).json()
    assert record["prediction_status"] == "not_configured"
    assert record["prediction_source"] == "local"


def test_consent_required_for_retry(client, patient):
    record = client.post("/api/patients", json=patient).json()
    assert client.post(f"/api/patients/{record['id']}/predict").status_code == 409


def test_cross_origin_write_is_rejected(client, patient):
    response = client.post("/api/patients", json=patient, headers={"Origin": "https://other.test"})
    assert response.status_code == 403


def test_ui_and_api_reference_are_served_locally(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "Vital Ledger API"
    for asset in (
        "app.js",
        "styles.css",
        "lucide.min.js",
        "docs.js",
        "swagger-ui-bundle.js",
        "swagger-ui.css",
    ):
        response = client.get(f"/static/{asset}")
        assert response.status_code == 200
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_invalid_update_leaves_existing_record_unchanged(client, patient):
    record = client.post("/api/patients", json=patient).json()
    patient["email"] = "hunter@gmail"
    assert client.put(f"/api/patients/{record['id']}", json=patient).status_code == 422
    assert client.get(f"/api/patients/{record['id']}").json() == record


def test_client_cannot_supply_generated_remarks(client, patient):
    patient["remarks"] = "A client must not control generated remarks."
    assert client.post("/api/patients", json=patient).status_code == 422
    assert client.get("/api/patients").json() == []


def test_changed_blood_values_regenerate_screening(client, patient):
    record = client.post("/api/patients", json=patient).json()
    patient["glucose"] = 90
    updated = client.put(f"/api/patients/{record['id']}", json=patient).json()
    assert updated["risk"] == "context"
    assert updated["remarks"] != record["remarks"]


def test_withdrawing_consent_replaces_ai_remarks_with_local(client, patient, monkeypatch):
    from app.schemas import Prediction

    patient["ai_consent"] = True
    predictor = client.app.state.predictor
    original_predict = predictor.predict
    monkeypatch.setattr(
        predictor,
        "predict",
        lambda data: Prediction(
            remarks="AI screening for this test.",
            source="openai",
            status="completed",
            risk="review",
        ),
    )
    record = client.post("/api/patients", json=patient).json()
    monkeypatch.setattr(predictor, "predict", original_predict)
    patient["ai_consent"] = False
    updated = client.put(f"/api/patients/{record['id']}", json=patient).json()
    assert updated["prediction_source"] == "local"
    assert updated["prediction_status"] == "local_only"
