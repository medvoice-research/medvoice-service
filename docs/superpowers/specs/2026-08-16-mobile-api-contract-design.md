# MedVoice Mobile API Contract + Pipeline — Design

Date: 2026-08-16
Status: Approved (unattended execution authorized)
Scope: medvoice-service (backend) + MedVoice (Flutter mobile app)

## 1. Context & Goals

MedVoice-Core (2024 capstone) served the Flutter mobile app (github.com/medvoice-research/MedVoice)
but was messy and cloud-bound (Replicate, GCS upload, ngrok). medvoice-service is the
local-first rewrite (WhisperX + LM Studio + Temporal) but never regained mobile-app
compatibility. Goal: define one API contract both ends implement, prioritizing the
modern medvoice-service pipeline, with the app's API layer rebuilt to match.

Decisions locked with the user:
- Modern approach first; both ends are outdated, so both change.
- No auth in v1, but feature-flag hook reserved for future user management.
- Audio uploads straight to medvoice-service (multipart POST); GCS dependency killed.
- Temporal is a nice-to-have (tracing/monitoring), NOT the critical path.
- Medical document = modern shape (SOAP + ICD-10 entities + PHI flags); app UI rebuilt around it.
- Q&A / chat deferred to a later iteration.
- Synchronous pipeline (Approach A): POST blocks until processed, results inline.

## 2. API Contract (v1)

Base URL: `http://<host>:8000` (app config points at the service; ngrok optional for device testing)

### POST /recordings
multipart/form-data:
- `file` (required): audio (.oga .m4a .aac .wav .amr .wma .awb .mp3 .ogg) or video (.wmv .mkv .avi .mov .mp4)
- `patient_name` (optional): string
- `language` (optional): string, default "en" (en, vi, zh, yue)

201 Created:
```json
{
  "recording_id": "rec_20260816_abc123",
  "status": "completed",
  "created_at": "2026-08-16T03:31:12Z",
  "patient_name": "Jane Doe",
  "language": "en",
  "transcript": {
    "full_text": "Okay, what did you do during the vacation? I went over to KL...",
    "segments": [
      {"speaker": "SPEAKER_01", "start": 0.031, "end": 2.756, "text": "Okay, what did you do during the vacation?"}
    ]
  },
  "medical_document": {
    "soap": {"subjective": "...", "objective": "...", "assessment": "...", "plan": "..."},
    "entities": [
      {"name": "Hypertension", "code": "I10", "category": "diagnosis", "speaker": "SPEAKER_00"}
    ],
    "phi": {"detected": false, "entities": []}
  }
}
```
Errors: 413 (file too large), 415 (unsupported format), 422 (validation), 504 (processing timeout), 500 (pipeline failure).

### GET /recordings
200:
```json
{
  "recordings": [
    {"recording_id": "rec_...", "patient_name": "Jane Doe", "created_at": "...", "status": "completed", "has_medical_document": true}
  ]
}
```
Ordered newest-first.

### GET /recordings/{recording_id}
200: same shape as POST 201 body.
404: `{"detail": "Recording not found", "error_code": "recording_not_found"}`

### DELETE /recordings/{recording_id}
204 on success. 404 if missing.

### Error envelope (all 4xx/5xx)
```json
{"detail": "<human message>", "error_code": "<machine_code>"}
```

### Reserved (documented, not implemented)
- `/auth/*` endpoints and `user_id` scoping — to be added behind `ENABLE_AUTHENTICATION` config flag.
- Q&A chat endpoint (`/medical/chat` exists; contract addition deferred).

## 3. Backend Implementation (medvoice-service)

### New router: app/routers/recordings.py
- `POST /recordings`: accept multipart, save audio to disk, run pipeline synchronously, return full result.
- `GET /recordings`: list from storage metadata.
- `GET /recordings/{id}`, `DELETE /recordings/{id}`.
- Register in app/main.py (`app.include_router(recordings.router)`).

### Pipeline (synchronous, reusing existing services)
1. Save upload -> `./data/recordings/{recording_id}/audio.<ext>`
2. WhisperX transcribe/align/diarize (reuse app/whisperx_services.py / stt router logic; the smoke test proved the Temporal path works — extract the same activities into callable service functions).
3. Medical processing (reuse app/routers/medical.py `process_transcript` internals / app/llm/medical_llm_service.py):
   - PHI detection -> `phi: {detected, entities}`
   - Entity extraction with speaker attribution -> `entities: [{name, code, category, speaker}]`
   - SOAP generation -> `soap: {subjective, objective, assessment, plan}`
4. Persist transcript.json + medical.json + meta.json.
5. Return 201 with full body.

### Storage layout (local-first)
```
./data/recordings/{recording_id}/
  audio.<ext>       # original upload
  transcript.json   # segments + full_text
  medical.json      # soap + entities + phi
  meta.json         # patient_name, language, created_at, status, durations
```
A `RecordingStore` abstraction (app/services/recordings/ or app/recordings_store.py) so MinIO can
replace local disk later without touching the router. List = scan metadata dir; keep it simple.

### Timeout budget
Sync POST: overall cap (config: `recordings.sync_timeout_seconds`, default 300). On exceed, return
504 with error_code `processing_timeout`. (No async fallback in v1 — YAGNI; documented as future.)

### Temporal
Keep existing Temporal wiring untouched. Optionally emit a workflow/trace for monitoring, but the
recording pipeline does NOT depend on Temporal. (Nice-to-have, do not block on it.)

### Config
config.yaml additions under `recordings:` — storage_dir, sync_timeout_seconds, max_upload_mb.
`ENABLE_AUTHENTICATION` flag remains the reserved hook; no auth code added.

## 4. Mobile App Changes (MedVoice, Flutter)

### API layer rewrite (lib/data/)
- constants.dart: baseUrl -> medvoice-service (configurable; keep localhost default, note ngrok for device).
  Replace all 5 old endpoint constants with the 4 new ones (recordings list/get/post/delete).
- audio_repository_impl.dart: replace GCS upload + process_audio_v2 flow with single multipart POST /recordings;
  implement list/get/delete. Remove googleapis/auth_io imports and the service-account asset usage.
- ask_repository_impl.dart: leave file but mark deprecated/dead (Q&A deferred); do not call it from UI.
- New models matching the contract: Recording, TranscriptSegment, SoapNote, MedicalEntity, PhiResult,
  MedicalDocument, RecordingListResponse, RecordingDetailResponse (lib/domain/entities/recording/... new files).
- Repository interface updated accordingly (audio_repository.dart).

### UI (lib/app/pages/ — MVP triads: controller/presenter/view per page)
- Recording screen (home/recording/*): record or pick audio -> POST /recordings -> show result (transcript + SOAP + entities + PHI badge).
- Medical archive screen (home/medical_archive/*): GET /recordings list -> tap -> detail.
- Detail: render SOAP sections, entity list, PHI warning if detected (reuse/extend patient_doc/note renderers where sensible).
- Remove GCS upload UI flow; chat_bot entry point stays but hidden/dead until Q&A iteration (defer).
- Keep widget_test.dart passing (update mocks).

### App config
- baseUrl in constants.dart; document ngrok/dev-over-LAN for physical devices.

## 5. Error Handling
- Backend: consistent error envelope; PHI failures degrade gracefully (flag + continue), SOAP/entity
  failures per-step (skip + mark) — reuse existing step-result pattern from medical.py.
- App: map error_code -> user message; timeout shows retry; 404 on detail -> back to list.
- Unsupported format / oversize surfaced before upload where possible (client-side check) and via 413/415 server-side.

## 6. Testing
- Backend: unit tests for RecordingStore (write/read/delete/list), router tests with httpx
  AsyncClient against TestClient; integration test posting datasets/audios/sg/sg-1.WAV asserting
  201 + transcript non-empty + medical_document present (mark LLM-dependent parts skippable when LM Studio absent).
- App: model fromJson unit tests; repository tests with mocked HTTP (http helper injected);
  widget test updated for new history screen.
- Manual: `make up` + curl the 4 endpoints; Streamlit UI unaffected.

## 7. Out of Scope (this iteration)
- Auth / user management (reserved flag only)
- Q&A / chat in the mobile contract
- MinIO migration (interface in place only)
- Async/long-audio fallback
- Temporal as critical path

## 8. Explicitly NOT Gaps (deliberate)
- Cloud->local migration (GCS upload -> direct upload; Replicate -> WhisperX/LM Studio) is the stated purpose.
- Old endpoint names dropped in favor of the new contract — app is being updated to match (user-approved).
