import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

BloodValue = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class PatientInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=2, max_length=120)
    date_of_birth: str
    email: EmailStr = Field(max_length=254)
    glucose: BloodValue = Field(le=2000)
    haemoglobin: BloodValue = Field(le=30)
    cholesterol: BloodValue = Field(le=2000)
    ai_consent: bool = False

    @field_validator("full_name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        if not any(character.isalpha() for character in value):
            raise ValueError("Full name must contain letters.")
        if any(ord(character) < 32 for character in value):
            raise ValueError("Full name cannot contain control characters.")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def valid_birth_date(cls, value: str) -> str:
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
            raise ValueError("Use dd/mm/yyyy, for example 28/01/1960.")
        try:
            birth_date = datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError as error:
            raise ValueError("Date of birth must be a real calendar date.") from error
        if birth_date > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return value

    @field_validator("glucose", "haemoglobin", "cholesterol", mode="before")
    @classmethod
    def numeric_blood_value(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Enter a numeric blood test value, not a boolean.")
        return value


class Prediction(BaseModel):
    remarks: str
    source: str
    status: str
    risk: str


class PatientRecord(PatientInput):
    id: int
    remarks: str
    prediction_source: str
    prediction_status: str
    risk: str
    created_at: str
    updated_at: str
