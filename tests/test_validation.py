from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import PatientInput


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


def test_valid_patient(patient):
    assert PatientInput(**patient).glucose == 232


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "hunter@gmail"),
        ("email", "Kris.wu.gmail.com"),
        ("date_of_birth", "31/11/2001"),
        ("date_of_birth", "28.01.1960"),
        ("date_of_birth", "1/01/1960"),
        ("glucose", "not numeric"),
        ("glucose", -1),
        ("glucose", True),
        ("haemoglobin", float("nan")),
        ("cholesterol", float("inf")),
        ("full_name", "12"),
    ],
)
def test_invalid_patient_is_rejected(patient, field, value):
    patient[field] = value
    with pytest.raises(ValidationError):
        PatientInput(**patient)


def test_future_birth_date_is_rejected(patient):
    patient["date_of_birth"] = (date.today() + timedelta(days=1)).strftime("%d/%m/%Y")
    with pytest.raises(ValidationError, match="future"):
        PatientInput(**patient)


def test_leap_day(patient):
    patient["date_of_birth"] = "29/02/2000"
    assert PatientInput(**patient).date_of_birth == "29/02/2000"
    patient["date_of_birth"] = "29/02/2001"
    with pytest.raises(ValidationError, match="calendar"):
        PatientInput(**patient)
