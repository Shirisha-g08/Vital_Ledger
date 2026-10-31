import json

import httpx
import pytest

from app.config import Settings
from app.prediction import HealthPredictor
from app.schemas import PatientInput


@pytest.fixture
def patient():
    return PatientInput(
        full_name="Robyn Pears",
        date_of_birth="28/01/1960",
        email="robyn@gmail.com",
        glucose=232,
        haemoglobin=13.5,
        cholesterol=180,
        ai_consent=True,
    )


def test_external_ai_request_and_privacy(tmp_path, monkeypatch, patient):
    captured = {}

    def post(client, url, **kwargs):
        captured.update(kwargs)
        assert url == "https://api.openai.com/v1/chat/completions"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                "Elevated glucose may indicate diabetes risk. "
                                "Confirm with a clinician."
                            )
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    predictor = HealthPredictor(Settings(tmp_path / "db", openai_api_key="test-only-key"))
    result = predictor.predict(patient)
    assert result.source == "openai"
    assert result.status == "completed"
    assert "Not a diagnosis" in result.remarks
    sent = json.dumps(captured["json"])
    assert "Robyn" not in sent
    assert "robyn@gmail.com" not in sent
    assert "28/01/1960" not in sent
    assert "232" in sent


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_errors_are_honest_local_fallbacks(tmp_path, monkeypatch, patient, status):
    def post(client, url, **kwargs):
        return httpx.Response(status, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", post)
    result = HealthPredictor(Settings(tmp_path / "db", openai_api_key="test-only-key")).predict(
        patient
    )
    assert result.source == "local"
    assert result.status == "failed"
    assert "AI request failed" in result.remarks


def test_no_consent_never_calls_external_service(tmp_path, monkeypatch, patient):
    def post(*args, **kwargs):
        pytest.fail("No request without consent")

    patient.ai_consent = False
    monkeypatch.setattr(httpx.Client, "post", post)
    result = HealthPredictor(Settings(tmp_path / "db", openai_api_key="test-only-key")).predict(
        patient
    )
    assert result.status == "local_only"


def test_timeout_and_malformed_response(tmp_path, monkeypatch, patient):
    predictor = HealthPredictor(Settings(tmp_path / "db", openai_api_key="test-only-key"))

    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Timeout")

    monkeypatch.setattr(httpx.Client, "post", timeout)
    assert predictor.predict(patient).status == "failed"

    def malformed(client, url, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": []})

    monkeypatch.setattr(httpx.Client, "post", malformed)
    assert predictor.predict(patient).status == "failed"
