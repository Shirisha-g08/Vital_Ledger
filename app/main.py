import json
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app.config import ROOT, Settings
from app.database import Database
from app.prediction import HealthPredictor
from app.schemas import PatientInput, PatientRecord, Prediction


class AssessmentRequest(BaseModel):
    confirm_mapping: bool = False
    ai_consent: bool = False


def validation_details(errors: list[dict]) -> list[dict]:
    return [
        {"field": str(error["loc"][-1]), "message": error["msg"].removeprefix("Value error, ")}
        for error in errors
    ]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_path)
    predictor = HealthPredictor(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database.initialize()
        yield

    application = FastAPI(
        title="Vital Ledger API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    application.state.database = database
    application.state.predictor = predictor

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse(
                    status_code=403, content={"detail": "Cross-origin write denied."}
                )
            if request.method in {"POST", "PUT"} and (
                request.headers.get("content-length", "0") != "0"
                or "transfer-encoding" in request.headers
            ):
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    return JSONResponse(
                        status_code=415, content={"detail": "Send application/json."}
                    )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": validation_details(error.errors())})

    @application.get("/api/health")
    def health():
        return {
            "status": "ok",
            "ai_configured": bool(settings.openai_api_key),
            "ai_model": settings.openai_model,
            "units": {"glucose": "mg/dL", "haemoglobin": "g/dL", "cholesterol": "mg/dL"},
        }

    @application.get("/api/patients", response_model=list[PatientRecord])
    def list_patients():
        return database.list_patients()

    @application.get("/api/patients/{patient_id}", response_model=PatientRecord)
    def get_patient(patient_id: int):
        record = database.get_patient(patient_id)
        if record is None:
            raise HTTPException(404, "Patient record not found.")
        return record

    @application.post("/api/patients", response_model=PatientRecord, status_code=201)
    def create_patient(patient: PatientInput):
        return database.save(patient, predictor.predict(patient))

    @application.put("/api/patients/{patient_id}", response_model=PatientRecord)
    def update_patient(patient_id: int, patient: PatientInput):
        existing = get_patient(patient_id)
        previous = PatientInput(**existing.model_dump(include=set(PatientInput.model_fields)))
        prediction_fields = {"date_of_birth", "glucose", "haemoglobin", "cholesterol", "ai_consent"}
        changed = any(getattr(previous, key) != getattr(patient, key) for key in prediction_fields)
        if changed:
            prediction = predictor.predict(patient)
        else:
            prediction = Prediction(
                remarks=existing.remarks,
                source=existing.prediction_source,
                status=existing.prediction_status,
                risk=existing.risk,
            )
        record = database.save(patient, prediction, patient_id=patient_id)
        if record is None:
            raise HTTPException(404, "Patient record not found.")
        return record

    @application.post("/api/patients/{patient_id}/predict", response_model=PatientRecord)
    def retry_prediction(patient_id: int):
        existing = get_patient(patient_id)
        patient = PatientInput(**existing.model_dump(include=set(PatientInput.model_fields)))
        if not patient.ai_consent:
            raise HTTPException(
                409, "Edit this record and grant consent before requesting external AI."
            )
        record = database.save(patient, predictor.predict(patient), patient_id=patient_id)
        if record is None:
            raise HTTPException(404, "Patient record not found.")
        return record

    @application.delete("/api/patients/{patient_id}", status_code=204)
    def delete_patient(patient_id: int):
        if not database.delete(patient_id):
            raise HTTPException(404, "Patient record not found.")
        return Response(status_code=204)

    @application.get("/api/assessment/cases")
    def assessment_cases():
        return json.loads((ROOT / "assessment" / "cases.json").read_text(encoding="utf-8"))

    @application.post("/api/assessment/run")
    def run_assessment(options: AssessmentRequest):
        if not options.confirm_mapping:
            raise HTTPException(422, "Confirm the reconstructed source-table mapping first.")
        results = []
        for case in assessment_cases()["cases"]:
            raw = {key: value for key, value in case.items() if key != "test_number"}
            raw["date_of_birth"] = raw["date_of_birth"].replace(".", "/")
            raw["ai_consent"] = options.ai_consent
            try:
                patient = PatientInput(**raw)
            except ValidationError as error:
                results.append(
                    {
                        "test_number": case["test_number"],
                        "status": "rejected",
                        "errors": validation_details(error.errors()),
                    }
                )
                continue
            existing = database.get_source_patient(case["test_number"])
            if existing:
                results.append(
                    {
                        "test_number": case["test_number"],
                        "status": "already_imported",
                        "patient_id": existing.id,
                    }
                )
                continue
            try:
                record = database.save(
                    patient, predictor.predict(patient), source_test=case["test_number"]
                )
                results.append(
                    {
                        "test_number": case["test_number"],
                        "status": "created",
                        "patient_id": record.id,
                    }
                )
            except sqlite3.IntegrityError:
                results.append({"test_number": case["test_number"], "status": "already_imported"})
        return {"results": results}

    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "app" / "static" / "index.html")

    @application.get("/docs", include_in_schema=False)
    def api_reference():
        return FileResponse(ROOT / "app" / "static" / "docs.html")

    application.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
    return application


app = create_app()
