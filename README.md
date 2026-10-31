# Vital Ledger

A local-first health-screening assessment application built with Python 3.12+, FastAPI, SQLite, and plain HTML/CSS/JavaScript. It manages patient blood-test records and optionally requests educational screening remarks from OpenAI. It is not a diagnostic device.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Interactive API reference: http://127.0.0.1:8000/docs.

The app creates `data/patients.db` on startup. Keep that file to retain records across restarts. Stop the server before backing up or moving the database, including its WAL files. No frontend build, Node.js, Docker, or runtime CDN is needed.

## Enable External AI

1. Copy `.env.example` to `.env` locally.
2. Set `OPENAI_API_KEY` in `.env` using your editor. Never paste secrets into chat or commit this file. The default model is `gpt-4o-mini`; change `OPENAI_MODEL` if necessary for your account.
3. Restart the server. Open a patient form and grant permission for external screening.
4. Save the record. To retry a failed request, open its details and choose **Retry AI**. Consent must already be granted.

The adapter calls `POST https://api.openai.com/v1/chat/completions` with a server-side bearer key. Only age in completed years, blood values, units, and explicitly unknown clinical context are sent. Full name, email and exact DOB are excluded. Data is still health information: de-identification is not a guarantee of anonymity. Obtain appropriate consent and review the provider's data policy before sending real patient data.

With no consent, the provider is never called. A missing key, timeout, HTTP error, malformed response or truncated response produces an explicit local-screening fallback. These remarks are **not AI output**. Source and status are stored separately and shown in patient details. A configured key is not proof of working provider credentials or quota. Unit tests mock provider success and failure; a live call requires your account and is not claimed as verified.

## Assessment Data

The source table lost alignment when pasted into the brief. The reconstructed mapping in `assessment/cases.json` and the assumed units were confirmed by the user during implementation. Compare against your original document again before submission. The application always requires an explicit confirmation before import.

The original pasted table text is retained in `assessment/original-table.txt`, including its displaced values and numbering. The JSON is the explicitly confirmed interpretation, not a silent correction of that text.

Open **Assessment cases**, inspect all ten rows, confirm the mapping and units, and select **Validate & import**. Source date strings remain dotted in the fixture and preview. The importer changes only their separator to `/`; it does not repair invalid dates, email addresses, or numeric values. Both Robyn Pears entries are intentionally retained. Imports skip existing assessment entries; regular CRUD permits multiple test entries for a patient and does not infer a unique identity from a name or email.

Under the confirmed mapping, tests **1, 3, 5, 6, 7, 9 and 10** are accepted. Tests **2, 4 and 8** are rejected:

| Test | Rejection | Detection |
| --- | --- | --- |
| 2, John Hunter | `hunter@gmail` lacks a valid public email domain | Pydantic `EmailStr` / email-validator |
| 4, Peter Larry | November has only 30 days; `31.11.2001` is impossible | `datetime.strptime` calendar parsing |
| 8, Kris Wu | `19.10.2030` is in the future as of the assessment run; email has no `@` | Comparison with the server's current date and `EmailStr` |

The future-date outcome is date-dependent, not hardcoded to 2026. Invalid rows are never stored or sent to AI. Read, edit and delete only accepted records. The requested demonstration edits Prem Kumar's email to `gokul@infocare.com` and deletes Tenille Singh's entry, leaving six records. Source fixtures are not changed by CRUD operations. An assessment entry intentionally deleted can be imported again; existing IDs are not recreated or overwritten.

## Validation and Clinical Limits

- DOB: strict `dd/mm/yyyy`, real calendar date, not in the future.
- Email: validated syntax and domain structure, not mailbox existence or deliverability.
- Name: 2-120 characters, at least one letter, no control characters; international names are permitted.
- Blood results: numeric, finite, positive; glucose/cholesterol at most 2,000 mg/dL and haemoglobin at most 30 g/dL. These are input sanity bounds, not definitions of health. Booleans are rejected.
- Units: glucose and **total** cholesterol in mg/dL; haemoglobin in g/dL. Do not enter mmol/L values without conversion.
- Remarks cannot be supplied or overwritten by clients. They are generated server-side.

Local screening flags glucose below 70 or at least 200, haemoglobin below 12 or above 17.5, and total cholesterol at least 240. Intermediate glucose/cholesterol values are contextualised, not diagnosed. These are deliberately simplified educational adult thresholds. Haemoglobin ranges depend on sex, pregnancy, age and the laboratory. Fasting status is unknown. A result without flags is not a clean bill of health, and no validated probability or disease diagnosis is computed. The dashboard's review count always uses these transparent rules, including when AI remarks are present; it is not an AI risk score.

Clinical background: [NIDDK diabetes testing](https://www.niddk.nih.gov/health-information/diabetes/overview/tests-diagnosis), [MedlinePlus haemoglobin test](https://medlineplus.gov/lab-tests/hemoglobin-test/), [MedlinePlus cholesterol levels](https://medlineplus.gov/cholesterollevelswhatyouneedtoknow.html).

## Code Map

| File | Responsibility |
| --- | --- |
| `app/schemas.py` | Input validation and typed responses |
| `app/database.py` | Connection lifecycle, transactions, parameterised SQLite CRUD |
| `app/prediction.py` | Transparent local rules, consent gate, minimised AI request, response checks and fallback |
| `app/main.py` | App factory, HTTP endpoints, security headers and assessment import |
| `app/static/` | Responsive records UI, dialogs, assessment view and bundled API documentation |
| `tests/` | Validation, API, persistence and mocked external-provider regressions |
| `scripts/record_demo.py` | Browser verification and reproducible captioned WebM demonstration |

`create_app(settings)` enables isolated test databases. Each SQLite operation uses its own connection and transaction. SQL values are bound parameters; SQL column names are derived only from server-owned schema fields. Full updates revalidate all fields. Name/email-only edits retain existing remarks and do not spend another AI request. Blood values, DOB or consent changes regenerate remarks. External requests have a 20-second timeout and no automatic billable retries.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Server and AI-configuration status; no secret values |
| GET / POST | `/api/patients` | List / create |
| GET / PUT / DELETE | `/api/patients/{id}` | Read / full update / delete |
| POST | `/api/patients/{id}/predict` | Retry remarks with existing consent |
| GET | `/api/assessment/cases` | Preview exact fixture strings |
| POST | `/api/assessment/run` | Confirmed import with per-row validation outcomes |

JSON requests return 201 for creation, 204 for deletion, 404 for missing records, 409 for a retry without consent, and 422 for field validation. Responses omit invalid input values and exception internals. The OpenAPI schema is at `/openapi.json`.

## Verify and Record

```powershell
python -m pytest -q
python -m ruff check app tests scripts
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python scripts/record_demo.py --base-url http://127.0.0.1:8000 --confirm-source-table
```

Run the recording on an **empty, disposable database**; it intentionally creates the seven valid assessment records, edits one, and deletes one. It refuses to modify a nonempty workspace. To record again without losing existing work, start a separate server with `DATABASE_PATH` set to a new disposable database and choose a different port. The confirmation flag is an assertion that you verified the source mapping and units. Do not use it without doing so.

The recording is silent, with readable explanatory captions. It covers rejected records, list/read, create validation, email update, deletion and the remaining list, API documentation, and actual validation/API/AI-adapter source. It also checks desktop/mobile layout and saves screenshots. Outputs are under ignored `artifacts/`. It does **not** fabricate a successful live AI call. Add a live, consented API demonstration after configuring your key if required for the interview.

If Chromium is not installed but Microsoft Edge is available, append `--browser-channel msedge` to the recording command. Playwright's FFmpeg recording component must still be installed. The supplied recording used this option.

If an unrelated globally installed pytest plugin fails, use a fresh `.venv` or set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` before running tests. Test databases are isolated temporary files.

## Security and Submission

This is a **single-user local assessment application**, not a production clinical system. Bind it to `127.0.0.1`. It has no login, access-control roles, TLS, encryption at rest, audit history, or verified clinical model. Cross-origin browser writes are rejected and same-origin assets have a restrictive content-security policy, but these are not substitutes for authentication or authorisation. Do not expose it publicly or enter real patient data. Production deployment requires appropriate privacy/security review, identity management and clinical governance.

`.gitignore` excludes environment files, databases, recordings, caches and local settings. `.env.example` contains no key. Review the staged diff and repository history before publishing. The assessment fixture contains the supplied names, emails and test values: publish it only if you are authorised to share that assessment dataset. Do not include real patient data or credentials in a public repository.

See `docs/DEMONSTRATION.md` for the interview walkthrough and submission checklist. GitHub publishing and email/Drive delivery require your authenticated accounts and candidate details; they are not automatically performed by the application.

## Third-Party Assets

Lucide icons 0.468.0 (ISC), Swagger UI 5.17.14 (Apache-2.0), and Python packages retain their respective upstream licences. Bundled JavaScript and CSS are upstream assets, not application-authored source. See `THIRD_PARTY_NOTICES.md`.