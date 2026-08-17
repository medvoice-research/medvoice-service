# Local Setup & Testing Guide (backend + mobile app)

How to run medvoice-service and the MedVoice Flutter app locally, verify the
recordings API end-to-end, and view the app in a browser. Written 2026-08-16
after the recordings API contract work (PR #5 backend, PR #45 app).

## TL;DR

```bash
# 1. Backend up (Docker Desktop must be running)
cd ~/Projects/medvoice
cp .env.example .env          # add HF_TOKEN (gated diarization models; optional for smoke tests)
make install                  # uv sync + deps (whisperx 3.3.4)
docker compose up -d --build whisperx-api whisperx-worker   # first build takes a while
curl -s http://localhost:8000/recordings                     # expect 200

# 2. Backend integration test (real audio through the whole pipeline)
uv run pytest tests/integration/test_recordings_api.py -v   # ~30s

# 3. App unit tests (no backend needed)
cd ~/Projects/medvoice-mobile
fvm flutter pub get
fvm flutter test              # 9 tests, offline (integration tests are tag-skipped)

# 4. App integration test against the REAL backend
fvm flutter test test/recordings_api_integration_test.dart --run-skipped   # ~30s

# 5. View the app in Chrome
fvm flutter run -d chrome     # backend must be up
```

## Prerequisites

| Tool | Why | Version used |
|---|---|---|
| Docker Desktop | Backend stack (API, Temporal, Postgres) | running daemon |
| uv | Python deps (uv-managed repo) | 0.6.x |
| Python 3.11 | backend runtime | 3.11 |
| fvm + Flutter | mobile app (SDK pinned by .fvmrc) | Flutter 3.19.5 (Dart <3.3.4) |
| ffmpeg | audio processing (installed via `make install`/Dockerfile) | — |
| Chrome | view the app on web | — |

Notes:
- The app pins Flutter 3.19.5 in `.fvmrc`; brew's current Flutter (3.47.x)
  violates the pubspec SDK constraint (`<3.3.4`), so use `fvm flutter`, never
  bare `flutter`, inside `~/Projects/medvoice-mobile`.
- `HF_TOKEN` in `.env` is only needed at runtime when WhisperX must download
  the gated pyannote diarization models. The base pipeline (transcribe/align/
  diarize via fast-whisper path) works without it — smoke tests pass with a
  dead token.

## Repos

- Backend:  `~/Projects/medvoice`         (github.com/medvoice-research/medvoice-service)
- App:      `~/Projects/medvoice-mobile`  (github.com/medvoice-research/MedVoice)

## 1. Backend bring-up

```bash
cd ~/Projects/medvoice
git checkout main && git pull

# config
cp .env.example .env
# edit .env: set HF_TOKEN=<your token>  (optional for smoke tests)

# python env
make install

# stack (first build compiles whisperx image — several minutes)
docker compose up -d --build whisperx-api whisperx-worker

# wait for health, then check the API is live
for i in $(seq 1 12); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/recordings 2>/dev/null)
  [ "$code" = "200" ] && echo "api ready ($code)" && break
  sleep 5
done
```

Services (docker compose):

| Service | Port | Notes |
|---|---|---|
| whisperx-api | :8000 | FastAPI — `/docs` for OpenAPI |
| whisperx-worker | — | Temporal worker |
| temporal / temporal-ui | :7233 / :8233 | workflow orchestration + UI |
| postgres | :5432 | Temporal DB |
| streamlit-ui | :8501 | admin UI |

### Verify the recordings API manually

```bash
# list (empty on fresh install)
curl -s http://localhost:8000/recordings

# upload a real sample audio and process synchronously (~60s on CPU)
curl -s -X POST http://localhost:8000/recordings \
  -F "file=@datasets/audios/sg/sg-1.WAV" \
  -F "patient_name=Smoke Test" | python3 -m json.tool
# -> recording_id, status "completed", transcript.full_text + segments,
#    medical_document.soap/entities/phi (empty unless LM Studio is running)

# detail / delete
curl -s http://localhost:8000/recordings/<recording_id>
curl -s -X DELETE http://localhost:8000/recordings/<recording_id>   # 204
```

Medical fields (SOAP/entities/PHI) populate only when LM Studio is running
(see repo README "Medical RAG with LM Studio"). Without it they degrade to
empty — by design.

## 2. Backend integration test

```bash
cd ~/Projects/medvoice
uv run pytest tests/integration/test_recordings_api.py -v
```

What it does: POST `datasets/audios/sg/sg-1.WAV` (English, ~49s) ->
201 with completed transcript -> GET list contains it -> GET detail ->
DELETE 204 -> GET 404. Expect ~30s (WhisperX on CPU).

The full unit suite: `uv run pytest tests/` (229 tests). Lint:
`uv run ruff check app/ tests/ streamlit_app/ --config pyproject.toml`.

## 3. Mobile app — unit tests (offline)

```bash
cd ~/Projects/medvoice-mobile
fvm flutter pub get
fvm flutter test
```

9 tests: domain-entity JSON parsing, AudioRepository against MockClient,
result-view widget. `dart_test.yaml` tags the real-backend test `integration`
so it is SKIPPED by default (that is expected — see step 4 to run it live).

## 4. Mobile app — integration test against the real backend

```bash
cd ~/Projects/medvoice-mobile
fvm flutter test test/recordings_api_integration_test.dart --run-skipped
```

`--run-skipped` overrides the dart_test.yaml tag filter so the test actually
runs. It uses a real `http.Client` (no mock) against
`http://localhost:8000`, driving the app's own `AudioRepository`:

1. POST a real WAV (`~/Projects/medvoice/datasets/audios/sg/sg-1.WAV`) ->
   expects `status: completed` with non-empty `transcript.fullText`
2. GET /recordings -> the new recording appears
3. GET /recordings/{id} -> detail round-trips
4. DELETE /recordings/{id} -> cleanup (also in tearDown so failures don't
   leave rows behind)

If the backend is down the test SKIPS with:
`backend not running — start docker compose in medvoice-service first`.

## 5. View the app in Chrome

```bash
cd ~/Projects/medvoice-mobile
fvm flutter run -d chrome      # backend must be up (step 1)
```

- `web/` platform support was added with `fvm flutter create --platforms web .`
- vosk offline speech recognition has no web support: a conditional-import
  web stub lets the app build/load on web while Android/iOS keep the real
  vosk. The recording screen shows a notice that offline recognition is
  unavailable on web.
- Hot reload works in Chrome; the app talks to localhost:8000 directly.

### Running on a phone/emulator instead

Not set up on this machine (no Android SDK / Xcode). To do it:
- Android: install Android Studio, accept SDK licenses, `fvm flutter doctor`,
  then `fvm flutter run` with a device connected.
- The API base URL is `lib/data/network/constants.dart`
  (`Constants.baseUrl`); for a physical phone, change it to your Mac's LAN
  IP (e.g. `http://192.168.x.x:8000/`) and ensure the API container listens
  on 0.0.0.0 (it does).

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop not running — open it, wait for the whale, retry |
| `curl ... 000` right after `docker compose up` | API still booting; use the readiness loop above (step 1) |
| `GET /recordings` 500 on fresh install | fixed in code (list returns [] if storage dir missing); pull latest main |
| Integration test prints `Skip: backend integration...` | expected — run with `--run-skipped` (step 4) |
| WhisperX SIGSEGV (exit 139) when running `make server` on macOS | libomp conflict (torch/faiss/sklearn). Workaround: `OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE`. Docker/Linux unaffected |
| SOAP/entities/PHI empty in results | LM Studio not running — expected degradation |
| `flutter` command fails in app repo | use `fvm flutter` (SDK pin 3.19.5) |
| `requirements/dev.txt: File not found` in CI | stale workflow — fixed; uv-managed repo uses `uv sync --group dev` |
| Upload >200 MB rejected | 413 — streamed cap in the API (by design) |

## API contract (recordings) — quick reference

```
POST   /recordings              multipart: file, patient_name?, language?
GET    /recordings              -> {recordings: [{recording_id, patient_name, created_at, status, has_medical_document}]}
GET    /recordings/{id}         -> full detail (transcript + medical_document)
DELETE /recordings/{id}         -> 204
```

Errors: flat `{"detail": ..., "error_code": ...}` envelope
(e.g. 415 `unsupported_format`, 413 upload too large, 504 processing timeout).
Spec: `docs/superpowers/specs/2026-08-16-mobile-api-contract-design.md` (local).
