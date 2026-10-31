# Demonstration and Interview Guide

## Recording Sequence

1. Start on an empty workspace. Show the data units and the screening-not-diagnosis notice.
2. Open Assessment cases. Compare all ten rows to the original document. Confirm the mapping and units. Keep external AI disabled unless you have permission and a working key.
3. Select Validate & import. Show seven created and three rejected; do not repair rejected source data.
4. Explain John Hunter: `hunter@gmail` has no public email domain. `EmailStr` rejects it before SQLite or AI.
5. Explain Peter Larry: November has only 30 days. Strict format parsing followed by calendar validation rejects `31/11/2001`.
6. Explain Kris Wu: invalid email without `@` and a DOB later than the current server date. The API reports both errors. This future-date result changes naturally after 19 October 2030.
7. Return to Patient records. Show seven entries, including both Robyn Pears records. Open one to read its measurements, generated remarks, prediction source and status.
8. Add John Hunter manually with his unchanged source values to show inline form validation. Cancel without correcting or saving the invalid record.
9. Edit Prem Kumar: change only email to `gokul@infocare.com`. Show it saved in the list. Explain that an email-only edit reuses existing remarks because no medical input changed.
10. Delete Tenille Singh, confirm the warning, and show six remaining records.
11. Open API reference. Explain GET, POST, PUT, DELETE, response models and 422 field errors.
12. Walk through `PatientInput`, `create_patient`, the database transaction and `HealthPredictor.predict`. Explain consent, payload minimisation, timeout, provider-response validation and honest fallback.
13. State whether a live AI request was demonstrated. If not configured, do not claim local remarks came from OpenAI. Configure a real server-side key and record a consented save/retry to demonstrate the external response before submitting if this is mandatory.

`scripts/record_demo.py` automates this sequence as a silent captioned WebM video and browser checks. It is not a substitute for understanding the code or for recording your own explanation if the reviewer expects spoken narration.

## Questions You Should Be Able to Answer

- Why does validation live on the server even though the UI has numeric and email fields? Clients can bypass HTML constraints; the same schema protects forms and API requests.
- Why SQLite? It provides simple persistent transactions without a separate service for a small local assessment. A multi-user production application would need stronger concurrency, migrations, authentication and auditing.
- Why are duplicate Robyn entries allowed? The assessment explicitly supplies two rows. Neither email nor name is a unique blood-test encounter identifier.
- Is this a medical prediction model? No. External AI supplies uncertain educational remarks, and the local rules are transparent screening flags. Neither is clinically validated or sufficient for diagnosis.
- What happens if AI fails? The record remains valid and is saved with explicitly labelled local remarks, source `local`, and status `failed` or `not_configured`. A consented retry is available.
- Can users inject a prompt through the full name? Names are never sent. The external payload contains only validated numeric blood values, computed age and fixed context strings.
- How are keys protected? Server-side environment configuration; no key in browser requests, health responses, source, screenshots or database. `.env` is ignored. Still review Git history and rotate any credential accidentally exposed.
- Why no automatically corrected email or date? The task says not to modify the source test data. Rejected rows are displayed with explanations rather than repaired.

## Submission Checklist

- Confirm the assessment dataset is permitted in the repository.
- Run tests and lint in a clean virtual environment.
- Review source, staged changes and Git history for secrets and real patient information.
- Publish source to your GitHub repository using your authenticated account.
- Watch the entire video. Add spoken narration/live API evidence if required. Use the captions as the explanation script.
- Upload the video to a share location you control when it is too large to attach. Check the recipient's access without your logged-in session before sending.
- Send candidate information requested on the first page of the original brief, repository URL, and video/link to `jobs@gokulinfocare.com`. That first page was not provided here, so candidate fields cannot be inferred.
- Send email only after personally checking recipients, permissions and attachments. No account credentials are needed in this repository.