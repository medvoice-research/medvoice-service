# Changelog

All notable changes to medvoice-service are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/). The version matches
`version` in `pyproject.toml`.

## [Unreleased]

## [0.1.0] - 2026-10-26

First release. Tested end to end with the MedVoice mobile app 1.0.0 on a physical
iPhone 15 Pro and on the iOS simulator. Covers the speech-to-text and medical-document
pipeline built since December 2025.

### Added
- WhisperX speech-to-text with alignment and speaker diarization (pyannote), with model
  caching.
- Medical document generation through LM Studio: SOAP note, ICD-10 entities with speaker
  attribution, and PHI detection. Each step degrades on its own if the LLM is unavailable.
- Recordings API for the mobile app: `POST /recordings` (multipart upload to transcript
  plus medical document), `GET /recordings`, `GET /recordings/{id}`,
  `GET /recordings/{id}/audio` (audio replay, returned as `audio_url`) and
  `DELETE /recordings/{id}`, with local-disk storage.
- Mock authentication: `POST /auth/login` returns a JWT. Doctor, nurse and admin
  accounts are seeded into a bcrypt SQLite store. `ENABLE_AUTHENTICATION` stays off, so
  the recordings endpoints are not protected.
- Vietnamese support: per-language Whisper model selection (PhoWhisper-small for `vi`)
  and Vietnamese number normalization.
- Vietnamese medical-term guard: suspect drug and disease names are rescored with
  Whisper and confirmed by the local SemIf server, then returned as
  `transcript.term_review`. Without SemIf the result is marked `unavailable`.
- VietMed ASR benchmark CLI (`scripts/asr_benchmark.py`): seeded subsets with
  WER/CER, term recall and RTF.
- Temporal workflows for patient STT and medical processing, an admin router, a
  vector store for consultation search, and a Streamlit UI with a medical chat.
- Docker Compose stack (API, worker, Temporal, Postgres) and unit and integration
  test suites with CI gates on pull requests into `main` and `dev`.

### Fixed
- Silent or near-empty uploads are rejected with `422 no_speech` before Whisper runs.
  Previously Whisper hallucinated filler ("Thank you very much.") and the LLM invented a
  full SOAP note from it. Thresholds: `recordings.min_peak_dbfs` (-45) and
  `recordings.min_seconds` (0.5).
- SOAP sections are parsed without stray markdown bold, including nested emphasis and
  Vietnamese section headings.
- Term scoring copies encoder output to the CPU, so it works with GPU encoders.

### Security
- Recording IDs and upload filenames are validated against path traversal; uploads are
  streamed against a size cap. Errors use a flat `{detail, error_code}` envelope, and
  failed uploads leave no orphan recording.
- Benchmark results that contain transcripts are kept out of git.
- Uploaded filenames are encrypted, and stored audio is served with `Cache-Control: no-store`.

### Known limitations
- Room noise without speech is not rejected and can still produce filler text.
- `GET /health/medical` returns 503 even when document generation works.

[Unreleased]: https://github.com/medvoice-research/medvoice-service/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/medvoice-research/medvoice-service/releases/tag/v0.1.0
