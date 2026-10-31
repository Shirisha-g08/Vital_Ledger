"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { patients: [], cases: [], outcomes: new Map(), editing: null, selected: null, ai: false };
let toastTimer;
const fieldLabels = { full_name: "Full name", date_of_birth: "Date of birth", email: "Email", glucose: "Glucose", haemoglobin: "Haemoglobin", cholesterol: "Cholesterol" };

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function icons() {
  if (window.lucide) window.lucide.createIcons();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  if (response.status === 204) return null;
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(typeof body.detail === "string" ? body.detail : "Please check the highlighted fields.");
    error.details = Array.isArray(body.detail) ? body.detail : [];
    throw error;
  }
  return body;
}

function toast(message) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 5000);
}

function badge(patient) {
  if (patient.prediction_source === "openai") return '<span class="badge ai"><i data-lucide="sparkles"></i>AI screening</span>';
  if (patient.prediction_status === "failed") return '<span class="badge failed"><i data-lucide="circle-alert"></i>AI unavailable</span>';
  return patient.risk === "review"
    ? '<span class="badge"><i data-lucide="circle-alert"></i>Review suggested</span>'
    : '<span class="badge context"><i data-lucide="circle-dashed"></i>Context needed</span>';
}

function renderPatients() {
  const query = $("#search").value.trim().toLowerCase();
  const filter = $("#risk-filter").value;
  const filtered = state.patients.filter((patient) => {
    const match = `${patient.full_name} ${patient.email}`.toLowerCase().includes(query);
    return match && (filter === "all" || (filter === "ai" ? patient.prediction_source === "openai" : patient.risk === filter));
  });
  const count = state.patients.length;
  $("#total-records").textContent = count;
  $("#nav-count").textContent = count;
  $("#table-count").textContent = count;
  $("#review-records").textContent = state.patients.filter((patient) => patient.risk === "review").length;
  $("#ai-records").textContent = state.patients.filter((patient) => patient.prediction_source === "openai").length;
  $("#empty-state").hidden = count !== 0;
  $("#no-results").hidden = count === 0 || filtered.length !== 0;
  $("#showing-count").textContent = `Showing ${filtered.length} of ${count} records`;
  $("#patient-rows").innerHTML = filtered.map((patient) => {
    const initials = patient.full_name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
    const name = escapeHtml(patient.full_name);
    const glucoseFlag = patient.glucose >= 200 || patient.glucose < 70;
    const hbFlag = patient.haemoglobin < 12 || patient.haemoglobin > 17.5;
    const cholesterolFlag = patient.cholesterol >= 240;
    return `<tr>
      <td><div class="patient-cell"><span class="patient-avatar tone-${patient.id % 4}">${escapeHtml(initials)}</span><div><button class="patient-name" data-action="view" data-id="${patient.id}">${name}</button><span class="patient-email">${escapeHtml(patient.email)}</span></div></div></td>
      <td>${escapeHtml(patient.date_of_birth)}</td>
      <td><span class="blood-number ${glucoseFlag ? "flagged-value" : ""}">${patient.glucose}</span></td>
      <td><span class="blood-number ${hbFlag ? "flagged-value" : ""}">${patient.haemoglobin}</span></td>
      <td><span class="blood-number ${cholesterolFlag ? "flagged-value" : ""}">${patient.cholesterol}</span></td>
      <td class="remark-cell">${badge(patient)}<button class="remark-preview" data-action="view" data-id="${patient.id}">${patient.prediction_source === "openai" ? "View AI remarks" : "View local screening"} &rarr;</button></td>
      <td><div class="actions"><button class="icon-button" title="Edit ${name}" aria-label="Edit ${name}" data-action="edit" data-id="${patient.id}"><i data-lucide="pencil"></i></button><button class="icon-button delete" title="Delete ${name}" aria-label="Delete ${name}" data-action="delete" data-id="${patient.id}"><i data-lucide="trash-2"></i></button></div></td>
    </tr>`;
  }).join("");
  icons();
}

async function loadPatients() {
  $("#refresh").disabled = true;
  $("#load-error").hidden = true;
  try {
    state.patients = await api("/api/patients");
    renderPatients();
  } catch (error) {
    $("#load-error").textContent = `Could not load records. ${error.message}`;
    $("#load-error").hidden = false;
    $("#showing-count").textContent = "Records unavailable";
  } finally {
    $("#refresh").disabled = false;
  }
}

function clearErrors() {
  document.querySelectorAll(".field-error").forEach((element) => { element.textContent = ""; });
  document.querySelectorAll("[aria-invalid]").forEach((element) => element.removeAttribute("aria-invalid"));
  $("#form-errors").hidden = true;
}

function openForm(patient = null) {
  state.editing = patient?.id ?? null;
  $("#patient-form").reset();
  clearErrors();
  $("#form-title").textContent = patient ? "Edit patient" : "Add patient";
  if (patient) {
    Object.keys(fieldLabels).forEach((field) => { document.getElementById(field).value = patient[field]; });
    $("#ai_consent").checked = patient.ai_consent;
  }
  $("#form-ai-status").textContent = state.ai
    ? "OpenAI is configured. External screening requires permission."
    : "OpenAI is not configured. Clearly labelled local screening will be saved.";
  $("#patient-dialog").showModal();
  $("#full_name").focus();
}

function showDetails(patient) {
  state.selected = patient.id;
  $("#detail-name").textContent = patient.full_name;
  $("#detail-content").innerHTML = `
    <div class="details-grid"><div><span class="detail-label">Email address</span><span class="detail-value">${escapeHtml(patient.email)}</span></div><div><span class="detail-label">Date of birth</span><span class="detail-value">${escapeHtml(patient.date_of_birth)}</span></div></div>
    <div class="detail-labs"><div><span class="detail-label">Glucose</span><strong>${patient.glucose}</strong><small>mg/dL</small></div><div><span class="detail-label">Haemoglobin</span><strong>${patient.haemoglobin}</strong><small>g/dL</small></div><div><span class="detail-label">Cholesterol</span><strong>${patient.cholesterol}</strong><small>mg/dL</small></div></div>
    <div class="form-section-title"><i data-lucide="clipboard-list"></i>Remarks</div>${badge(patient)}
    <p class="remarks-text">${escapeHtml(patient.remarks)}</p>
    <div class="detail-meta"><span>Source: ${patient.prediction_source === "openai" ? "OpenAI" : "Local rules (not AI)"}</span><span>Status: ${escapeHtml(patient.prediction_status.replaceAll("_", " "))}</span><span>External AI consent: ${patient.ai_consent ? "Granted" : "Not granted"}</span><span>Updated: ${escapeHtml(new Date(patient.updated_at).toLocaleString("en-AU"))}</span></div>`;
  $("#retry-ai").hidden = !patient.ai_consent;
  icons();
  if (!$("#detail-dialog").open) $("#detail-dialog").showModal();
}

function openDelete(patient) {
  state.selected = patient.id;
  $("#delete-description").textContent = `Delete the record for ${patient.full_name} (${patient.email})?`;
  $("#delete-error").hidden = true;
  $("#delete-dialog").showModal();
}

async function savePatient(event) {
  event.preventDefault();
  clearErrors();
  const data = Object.fromEntries(new FormData(event.currentTarget).entries());
  data.ai_consent = $("#ai_consent").checked;
  $("#save-patient").disabled = true;
  $("#save-patient").textContent = data.ai_consent && state.ai ? "Screening & saving..." : "Saving...";
  try {
    await api(state.editing ? `/api/patients/${state.editing}` : "/api/patients", {
      method: state.editing ? "PUT" : "POST", body: JSON.stringify(data),
    });
    $("#patient-dialog").close();
    toast(state.editing ? "Patient record updated." : "Patient record saved.");
    await loadPatients();
  } catch (error) {
    let firstField;
    for (const detail of error.details || []) {
      const errorElement = document.getElementById(`error-${detail.field}`);
      if (errorElement) {
        errorElement.textContent = detail.message;
        const input = document.getElementById(detail.field);
        input.setAttribute("aria-invalid", "true");
        firstField ??= input;
      }
    }
    $("#form-errors").textContent = error.message;
    $("#form-errors").hidden = false;
    firstField?.focus();
  } finally {
    $("#save-patient").disabled = false;
    $("#save-patient").innerHTML = '<i data-lucide="check"></i>Save patient';
    icons();
  }
}

function renderAssessment() {
  $("#assessment-rows").innerHTML = state.cases.map((patient) => {
    const outcome = state.outcomes.get(patient.test_number);
    let result = '<span class="muted">Not run</span>';
    if (outcome) {
      if (outcome.status === "rejected") {
        result = '<span class="badge failed">Rejected</span>' + outcome.errors.map((error) => `<p class="assessment-error"><strong>${escapeHtml(fieldLabels[error.field] || error.field)}:</strong> ${escapeHtml(error.message)}</p>`).join("");
      } else {
        result = `<span class="badge context">${outcome.status === "created" ? "Created" : "Already imported"}</span>`;
      }
    }
    return `<tr><td>${patient.test_number}</td><td>${escapeHtml(patient.full_name)}</td><td>${escapeHtml(patient.date_of_birth)}</td><td>${escapeHtml(patient.email)}</td><td>${patient.glucose}</td><td>${patient.haemoglobin}</td><td>${patient.cholesterol}</td><td>${result}</td></tr>`;
  }).join("");
}

async function switchView(view) {
  $("#patients-view").hidden = view !== "patients";
  $("#assessment-view").hidden = view !== "assessment";
  $("#breadcrumb-current").textContent = view === "patients" ? "Patient records" : "Assessment cases";
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
    button.setAttribute("aria-current", button.dataset.view === view ? "page" : "false");
  });
  if (view === "assessment" && !state.cases.length) {
    try {
      const data = await api("/api/assessment/cases");
      state.cases = data.cases;
      $("#mapping-notice").textContent = data.mapping_notice;
      renderAssessment();
    } catch (error) { toast(`Could not load assessment cases. ${error.message}`); }
  }
}

document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => document.getElementById(button.dataset.close).close()));
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("cancel", (event) => {
    if ([...dialog.querySelectorAll("button")].some((button) => button.disabled)) event.preventDefault();
  });
});
document.querySelectorAll("[data-view]").forEach((button) => {
  const label = button.dataset.view === "patients" ? "Patient records" : "Assessment cases";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", () => switchView(button.dataset.view));
});
$("#new-patient").addEventListener("click", () => openForm());
$("#empty-add").addEventListener("click", () => openForm());
$("#patient-form").addEventListener("submit", savePatient);
$("#search").addEventListener("input", renderPatients);
$("#risk-filter").addEventListener("change", renderPatients);
$("#refresh").addEventListener("click", loadPatients);
$("#clear-filters").addEventListener("click", () => { $("#search").value = ""; $("#risk-filter").value = "all"; renderPatients(); });
$("#patient-rows").addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const patient = state.patients.find((record) => record.id === Number(button.dataset.id));
  if (button.dataset.action === "view") showDetails(patient);
  if (button.dataset.action === "edit") openForm(patient);
  if (button.dataset.action === "delete") openDelete(patient);
});
$("#detail-edit").addEventListener("click", () => {
  $("#detail-dialog").close();
  openForm(state.patients.find((patient) => patient.id === state.selected));
});
$("#retry-ai").addEventListener("click", async () => {
  $("#retry-ai").disabled = true;
  try {
    const patient = await api(`/api/patients/${state.selected}/predict`, { method: "POST" });
    await loadPatients();
    showDetails(patient);
    toast(patient.prediction_status === "completed" ? "AI remarks updated." : "External AI unavailable. Local screening retained.");
  } catch (error) { toast(error.message); }
  finally { $("#retry-ai").disabled = false; }
});
$("#confirm-delete").addEventListener("click", async () => {
  $("#confirm-delete").disabled = true;
  try {
    await api(`/api/patients/${state.selected}`, { method: "DELETE" });
    $("#delete-dialog").close();
    toast("Patient record deleted.");
    await loadPatients();
  } catch (error) {
    $("#delete-error").textContent = error.message;
    $("#delete-error").hidden = false;
  } finally { $("#confirm-delete").disabled = false; }
});
$("#mapping-confirmed").addEventListener("change", (event) => { $("#run-assessment").disabled = !event.target.checked; });
$("#run-assessment").addEventListener("click", async () => {
  $("#run-assessment").disabled = true;
  $("#run-assessment").textContent = "Validating & importing...";
  try {
    const data = await api("/api/assessment/run", { method: "POST", body: JSON.stringify({ confirm_mapping: $("#mapping-confirmed").checked, ai_consent: $("#assessment-consent").checked }) });
    state.outcomes = new Map(data.results.map((result) => [result.test_number, result]));
    renderAssessment();
    const created = data.results.filter((result) => result.status === "created").length;
    const rejected = data.results.filter((result) => result.status === "rejected").length;
    const existing = data.results.length - created - rejected;
    $("#assessment-summary").textContent = `${created} created / ${rejected} rejected / ${existing} already imported. Source values have not been corrected or replaced.`;
    $("#assessment-summary").hidden = false;
    await loadPatients();
  } catch (error) { toast(error.message); }
  finally {
    $("#run-assessment").disabled = !$("#mapping-confirmed").checked;
    $("#run-assessment").innerHTML = '<i data-lucide="play"></i>Validate &amp; import';
    icons();
  }
});

async function initialize() {
  icons();
  $("#today-label").textContent = new Intl.DateTimeFormat("en-AU", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
  try {
    const health = await api("/api/health");
    state.ai = health.ai_configured;
    $("#connection-status").innerHTML = '<span class="status-dot"></span>Workspace online';
    $("#ai-caption").textContent = state.ai ? "OpenAI configured; consent required" : "External AI not configured";
  } catch {
    $("#connection-status").textContent = "Server unavailable";
    $("#ai-caption").textContent = "Connection unavailable";
  }
  await loadPatients();
}

initialize();