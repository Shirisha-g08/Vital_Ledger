import argparse
import ast
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"


def caption(page, text: str, seconds: float = 5) -> None:
    page.evaluate(
        """(text) => {
            let caption = document.querySelector('.demo-caption');
            if (!caption) {
                caption = document.createElement('div');
                caption.className = 'demo-caption';
                document.body.append(caption);
            }
            caption.textContent = text;
        }""",
        text,
    )
    page.wait_for_timeout(seconds * 1000)


def remove_caption(page) -> None:
    page.evaluate("document.querySelector('.demo-caption')?.remove()")


def function_source(relative_path: str, function_name: str) -> str:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node)
    raise ValueError(f"Function not found: {function_name}")


def code_scene(page, title: str, filename: str, source: str, explanation: str) -> None:
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <title>{html.escape(title)}</title><style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 38px 65px 120px; background: #f5f7f5; color: #20332e;
      font: 16px 'Trebuchet MS', sans-serif; }}
    h1 {{ font-size: 30px; margin: 5px 0 12px; }}
    .label {{ color: #547561; font-size: 12px; }}
    .file {{ color: #738778; margin-bottom: 20px; font-size: 14px; }}
    pre {{ border-top: 1px solid #d5e0d6; padding-top: 20px; margin: 0;
      white-space: pre-wrap; overflow-wrap: anywhere; font: 15px/1.65 Consolas, monospace; }}
    .demo-caption {{ position: fixed; bottom: 12px; left: 20px; right: 20px; padding: 15px 25px;
      background: #19382f; color: white; text-align: center; border-radius: 6px;
      font-size: 17px; line-height: 1.5; }}
    </style></head><body><span class="label">IMPLEMENTATION WALKTHROUGH</span>
    <h1>{html.escape(title)}</h1><div class="file">{html.escape(filename)}</div>
    <pre>{html.escape(source)}</pre></body></html>"""
    page.goto("data:text/html;charset=utf-8," + quote(document))
    caption(page, explanation, 9)


def record(base_url: str, browser_channel: str = "chromium") -> None:
    with httpx.Client(base_url=base_url, timeout=10) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        patients = client.get("/api/patients")
        patients.raise_for_status()
        if patients.json():
            raise SystemExit("Refusing to modify a nonempty workspace. Use an empty disposable DB.")

    ARTIFACTS.mkdir(exist_ok=True)
    errors = []
    expected_validation = []

    def collect_console(message) -> None:
        if message.type != "error":
            return
        if message.location.get("url") == base_url + "/api/patients" and "422" in message.text:
            expected_validation.append(message.text)
            return
        errors.append(message.text)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=None if browser_channel == "chromium" else browser_channel
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 960},
            record_video_dir=str(ARTIFACTS / "raw-video"),
            record_video_size={"width": 1440, "height": 960},
            reduced_motion="reduce",
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", collect_console)
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#empty-state")).to_be_visible()
        caption(
            page,
            "Vital Ledger: Python / FastAPI, SQLite, and a local-first browser interface. "
            "Educational screening only, not a medical diagnosis.",
            6,
        )
        page.get_by_role("button", name="Assessment cases", exact=True).click()
        expect(page.locator("#assessment-rows tr")).to_have_count(10)
        caption(
            page,
            "The ten source rows retain their supplied values, including invalid data and "
            "the duplicate Robyn entry. The reconstructed mapping and units were user-confirmed.",
            7,
        )
        page.locator("#mapping-confirmed").check()
        page.locator("#run-assessment").click()
        expect(page.locator("#assessment-summary")).to_contain_text(
            "7 created / 3 rejected", timeout=30000
        )
        remove_caption(page)
        page.screenshot(path=str(ARTIFACTS / "assessment-results.png"), full_page=True)
        caption(
            page,
            "Seven records were saved. Three rows were rejected before storage or prediction. "
            "No invalid email or date has been silently corrected.",
            6,
        )
        page.locator("#assessment-rows tr").nth(1).scroll_into_view_if_needed()
        caption(
            page,
            "Test 2, John Hunter: hunter@gmail lacks a valid public email domain. "
            "Pydantic EmailStr detects the invalid address.",
            6,
        )
        page.locator("#assessment-rows tr").nth(3).scroll_into_view_if_needed()
        caption(
            page,
            "Test 4, Peter Larry: 31 November is not a real calendar date. "
            "Strict datetime parsing rejects it; the source value is unchanged.",
            6,
        )
        page.locator("#assessment-rows tr").nth(7).scroll_into_view_if_needed()
        caption(
            page,
            "Test 8, Kris Wu: the birth date is in the future at this run and the email lacks @. "
            "The API reports both errors on the same row.",
            7,
        )
        page.get_by_role("button", name="Patient records", exact=True).click()
        expect(page.locator("#patient-rows tr")).to_have_count(7)
        page.evaluate("scrollTo(0, 0)")
        caption(
            page,
            "READ: all seven accepted records are listed with units and screening flags. "
            "Both supplied Robyn Pears entries are intentionally retained.",
            6,
        )
        page.get_by_role("button", name="Robyn Pears", exact=True).first.click()
        expect(page.locator("#detail-content")).to_contain_text("Local rules (not AI)")
        caption(
            page,
            "Patient details show the generated Remarks and their source. "
            "This recording uses local rules; no successful live OpenAI call is claimed.",
            7,
        )
        page.locator('[data-close="detail-dialog"]').click()
        page.locator("#new-patient").click()
        invalid = {
            "full_name": "John Hunter",
            "date_of_birth": "10/12/1990",
            "email": "hunter@gmail",
            "glucose": "94",
            "haemoglobin": "15",
            "cholesterol": "200",
        }
        for field, value in invalid.items():
            page.locator(f"#{field}").fill(value)
        page.locator("#save-patient").click()
        expect(page.locator("#error-email")).not_to_be_empty()
        caption(
            page,
            "CREATE validation: the same invalid John Hunter entry is also rejected in the "
            "form. Server-side validation remains authoritative even if HTML checks are bypassed.",
            7,
        )
        page.locator('[data-close="patient-dialog"]').first.click()
        page.get_by_role("button", name="Edit Prem Kumar", exact=True).click()
        page.locator("#email").fill("gokul@infocare.com")
        caption(
            page,
            "UPDATE: change only Prem Kumar's email to gokul@infocare.com. "
            "Medical values and source fixtures remain unchanged.",
            5,
        )
        page.locator("#save-patient").click()
        expect(page.locator("#patient-dialog")).not_to_be_visible()
        expect(page.locator("#patient-rows")).to_contain_text("gokul@infocare.com")
        caption(
            page,
            "The updated email is persisted. An email-only edit reuses existing Remarks "
            "because the blood values, birth date and consent have not changed.",
            5,
        )
        page.get_by_role("button", name="Delete Tenille Singh", exact=True).click()
        expect(page.locator("#delete-dialog")).to_be_visible()
        caption(
            page,
            "DELETE: remove Tenille Singh's entry. Deletion requires explicit confirmation "
            "and permanently removes this record from the workspace.",
            5,
        )
        page.locator("#confirm-delete").click()
        expect(page.locator("#patient-rows tr")).to_have_count(6)
        caption(
            page,
            "READ after deletion: six records remain, including the updated email. "
            "SQLite retains these records across application restarts.",
            6,
        )
        remove_caption(page)
        page.screenshot(path=str(ARTIFACTS / "patients-desktop.png"), full_page=True)
        page.locator("#search").fill("gokul@infocare.com")
        expect(page.locator("#patient-rows tr")).to_have_count(1)
        page.locator("#search").fill("")
        page.locator("#risk-filter").select_option("review")
        expect(page.locator("#patient-rows tr")).to_have_count(6)
        page.locator("#risk-filter").select_option("all")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            "Mobile page overflows"
        )
        page.screenshot(path=str(ARTIFACTS / "patients-mobile.png"), full_page=True)
        page.locator("#new-patient").click()
        expect(page.locator("#patient-dialog")).to_be_visible()
        assert page.locator("#patient-dialog").bounding_box()["width"] <= 390
        page.screenshot(path=str(ARTIFACTS / "patient-form-mobile.png"), full_page=True)
        page.locator('[data-close="patient-dialog"]').first.click()
        page.set_viewport_size({"width": 1440, "height": 960})
        page.goto(base_url + "/docs", wait_until="networkidle")
        expect(page.locator(".swagger-ui .info .title")).to_contain_text("Vital Ledger API")
        caption(
            page,
            "The self-hosted OpenAPI reference documents GET, POST, PUT, DELETE and the "
            "AI retry endpoint. Invalid fields return 422; missing records return 404.",
            7,
        )
        code_scene(
            page,
            "Validate before storage or AI",
            "app/schemas.py",
            function_source("app/schemas.py", "valid_birth_date"),
            "The birth-date validator enforces dd/mm/yyyy, rejects impossible calendar dates, and "
            "compares with today's server date. EmailStr and numeric constraints cover "
            "other fields.",
        )
        code_scene(
            page,
            "A small, typed HTTP boundary",
            "app/main.py",
            function_source("app/main.py", "create_patient")
            + "\n\n"
            + function_source("app/main.py", "delete_patient"),
            "FastAPI validates PatientInput before entering the handler. Prediction runs only for "
            "valid data; parameterised SQLite operations persist it inside transactions.",
        )
        prediction = function_source("app/prediction.py", "predict").splitlines()
        code_scene(
            page,
            "Consent and data minimisation",
            "app/prediction.py (excerpt)",
            "\n".join(prediction[:23]),
            "Without permission, no provider request is made. Only completed age and numeric "
            "measurements are sent; name, email and exact birth date never enter the AI payload.",
        )
        request_line = next(index for index, line in enumerate(prediction) if "try:" in line)
        code_scene(
            page,
            "External API request and response checks",
            "app/prediction.py (excerpt)",
            "\n".join(prediction[request_line : request_line + 25]),
            "The server calls OpenAI over HTTPS using an environment key and a 20-second timeout. "
            "HTTP errors, missing content and incomplete responses cannot be presented "
            "as AI success.",
        )
        code_scene(
            page,
            "Honest failure handling",
            "app/prediction.py (excerpt)",
            "\n".join(prediction[-10:]),
            "An unavailable API retains clearly labelled local screening, never fabricated AI "
            "remarks. Configure your own key, restart, grant consent, and retry for a "
            "live API demo.",
        )
        page.goto(base_url, wait_until="networkidle")
        expect(page.locator("#patient-rows tr")).to_have_count(6)
        caption(
            page,
            "Demonstration complete: CRUD, rejected source rows, persistent storage, "
            "responsive UI and API integration code. Live provider verification remains required.",
            7,
        )
        video = page.video
        context.close()
        video.save_as(str(ARTIFACTS / "health-prediction-demo.webm"))
        browser.close()

    with httpx.Client(base_url=base_url) as client:
        final = client.get("/api/patients").json()
    assert len(final) == 6
    assert any(patient["email"] == "gokul@infocare.com" for patient in final)
    assert all(patient["full_name"] != "Tenille Singh" for patient in final)
    assert len(expected_validation) == 1, "Expected one intentional invalid-form response"
    assert not errors, "Browser errors: " + "; ".join(errors)
    report = {
        "result": "passed",
        "created": 7,
        "rejected": [2, 4, 8],
        "remaining": len(final),
        "email_update": "gokul@infocare.com",
        "deleted": "Tenille Singh",
        "desktop": "1440x960",
        "mobile": "390x844",
        "browser_errors": errors,
        "expected_validation_responses": len(expected_validation),
        "live_ai_verified": False,
        "recording": "health-prediction-demo.webm",
    }
    (ARTIFACTS / "browser-verification.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify and record the confirmed assessment workflow."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--browser-channel", choices=("chromium", "msedge", "chrome"), default="chromium"
    )
    parser.add_argument("--confirm-source-table", action="store_true", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):\d+", args.base_url):
        parser.error("Use a local development URL, for example http://127.0.0.1:8000")
    record(args.base_url.rstrip("/"), args.browser_channel)
