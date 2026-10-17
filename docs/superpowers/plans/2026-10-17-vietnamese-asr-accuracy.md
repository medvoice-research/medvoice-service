# Vietnamese ASR Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure Vietnamese ASR candidates on VietMed, ship the best CPU-feasible model for `vi`, add medical-vocabulary biasing if it measurably helps, and let mobile send `language=vi`.

**Architecture:** Pure metric functions in `app/services/asr_metrics.py`; one CLI `scripts/asr_benchmark.py` (`fetch` pulls a seeded subset through the HF datasets-server rows API using stdlib only; `run` transcribes via production `transcribe_with_whisper` and writes JSON). Winner goes into `config.yaml` `whisperx.models_by_language`, read by `run_stt`. Mobile adds a vi/en toggle passed to the existing `uploadRecording(language:)`.

**Tech Stack:** Python 3.11, WhisperX 3.3.4 / faster-whisper 1.1.1 / CTranslate2 4.4.0 (CPU int8), Flutter 3.19.5.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-17-vietnamese-asr-accuracy-design.md`.
- CPU only: `device=cpu`, `compute_type=int8`.
- No new Python dependencies (`datasets` is shadowed by the repo's `datasets/` dir; `pyarrow`/`jiwer` absent) → stdlib HTTP + own Levenshtein.
- Success bar: WER ≥ 30 % relative better than `base`; medical-term recall ≥ 80 %; RTF ≤ 0.4 (dev Mac M4 Pro CPU, labeled).
- Subset seed `17`: VietMed test 300 utterances; VietMed-NER test 200 utterances with ≥ 1 medical entity.
- Medical NER labels counted for term recall: every label except `DATETIME`, `UNITCALIBRATOR`, `PERSON`, `LOCATION`, `ORGANIZATION`, `GENDER`, `AGE`, `OCCUPATION` (non-clinical); the exact kept set is printed by `fetch` and stored in the manifest.
- Commit locally on feature branches; merge to local `main` with `--ff-only`; **never push**.
- Downloaded audio in `datasets/vietmed/` (gitignored); results in `benchmarks/asr/` (committed).

---

### Task 1: Metric functions

**Files:**
- Create: `app/services/asr_metrics.py`
- Test: `tests/unit/test_asr_metrics.py`

**Interfaces:**
- Produces: `normalize(text: str) -> str`, `wer(ref: str, hyp: str) -> tuple[int, int]` (edits, ref_words), `cer(ref, hyp) -> tuple[int, int]` (edits, ref_chars), `entity_spans(words: list[str], labels: list[str], keep: set[str]) -> list[str]`, `term_hits(terms: list[str], hyp: str) -> int`.

- [ ] Step 1: tests — NFC + lowercase + punctuation strip keeps tone marks (`"Đau  ĐẦU!"` → `"đau đầu"`); `wer("a b c", "a x c") == (1, 3)`; insertion/deletion counts; `cer` on tones (`"má"` vs `"mà"` → 1 edit); BIO span extraction joins `B-`/`I-` runs and drops non-kept labels; `term_hits` matches on word boundaries after normalize (`"đau"` not counted inside `"đau đầu"`? — **counted**: substring on space-padded text, so `" đau "` matches in `" đau đầu "`).
- [ ] Step 2: run → fail (module missing).
- [ ] Step 3: implement (Levenshtein over token lists, O(n·m) two-row DP).
- [ ] Step 4: run → pass. Step 5: commit `feat(asr): metric functions for Vietnamese ASR benchmark`.

### Task 2: PhoWhisper models selectable

**Files:** Modify `app/schemas.py:161-181` (WhisperModel enum).

- [ ] Add `phowhisper_small = "mad1999/pho-whisper-small-ct2"`, `phowhisper_medium = "mad1999/pho-whisper-medium-ct2"`, `phowhisper_large = "mad1999/pho-whisper-large-ct2"` following the `nyrahealth/faster_CrisperWhisper` precedent.
- [ ] Smoke: load `phowhisper_small` on CPU int8 via `transcribe_with_whisper` on `datasets/audios/vn/vn-2.mp3`, print text. Commit `feat(asr): PhoWhisper CT2 models in WhisperModel enum`.

### Task 3: Benchmark CLI

**Files:** Create `scripts/asr_benchmark.py`; modify `.gitignore` (add `datasets/vietmed/`).

**Interfaces:**
- Consumes: Task 1 functions; `app.whisperx_services.transcribe_with_whisper`, `app.whisperx_services._transcription_model_cache`; `whisperx.load_audio`.
- `fetch`: rows API `https://datasets-server.huggingface.co/rows?dataset=<ds>&config=default&split=test&offset=<i>&length=1`; downloads `row.audio[0].src` to `datasets/vietmed/<set>/<i>.<ext>`; writes `benchmarks/asr/manifest.json` `{seed, sets: {vietmed: [{id, path, text, duration}], ner: [{id, path, text, terms}], clips: [...]}, kept_labels}`. Idempotent (skips existing files).
- `run --model <enum value> [--hotwords FILE] [--tag NAME]`: for each set, transcribe each file (`language="vi"`, default ASR/VAD options, `+hotwords/initial_prompt` when given), time it, aggregate corpus WER/CER (sum edits ÷ sum ref), term recall (sum hits ÷ sum terms), RTF (sum time ÷ sum duration), peak RSS. Clears `_transcription_model_cache` before loading so variants never reuse a model built with other `asr_options`. Writes `benchmarks/asr/<date>-<model-slug>[-<tag>].json`; prints one summary row.
- `report`: reads all result JSONs → markdown table to stdout and `benchmarks/asr/README.md`.

- [ ] Step 1: implement; Step 2: `fetch`; Step 3: `run --model tiny` on 5 utterances (`--limit 5`) as smoke; Step 4: commit `feat(asr): VietMed benchmark CLI`.

### Task 4: Run approach A

- [ ] Run `base`, `small`, `medium`, `large-v3-turbo`, PhoWhisper small/medium/large sequentially in background; one process per model.
- [ ] Confirm vi alignment model loads once (`whisperx.load_align_model("vi", "cpu")`).
- [ ] `report`; pick winner: lowest VietMed WER among models with RTF ≤ 0.4. Commit results `bench(asr): approach A results`.

### Task 5: Ship model per language

**Files:** `config.yaml` (whisperx), `app/config.py` (+`WHISPER_MODELS_BY_LANGUAGE`), `app/services/recording_pipeline.py:74,144` ; test `tests/unit/test_recording_pipeline.py`.

- [ ] Test: `run_stt(path, language="vi")` calls `transcribe_with_whisper` with `model == WhisperModel(<vi model>)`; `language="fr"` → `Config.WHISPER_MODEL`.
- [ ] Implement `model: str | None = None` → `model or Config.WHISPER_MODELS_BY_LANGUAGE.get(language, Config.WHISPER_MODEL)`.
- [ ] Full unit suite; commit `feat(recordings): per-language Whisper model (vi → <winner>)`.

### Task 6: Approach B — vocabulary biasing

**Files:** `data/vocab/vi_medical.txt` (generated from VietMed-NER **train** split entity strings by frequency — never test, to avoid leakage); `scripts/asr_benchmark.py` `vocab` subcommand.

- [ ] Generate vocab; run winner with `--hotwords data/vocab/vi_medical.txt --tag vocab`.
- [ ] Ship in `config.yaml` `whisperx.hotwords_by_language.vi` only if term recall ↑ and WER not ↑; else record negative result.
- [ ] LLM post-correction: evaluate only if LM Studio responds at `LM_STUDIO_BASE_URL`; otherwise record "not evaluated (LM Studio offline)".
- [ ] Commit `bench(asr): vocabulary biasing results`.

### Task 7: Mobile language toggle

**Files:** `lib/app/pages/home/recording/recording/recording_presenter.dart`, both controllers + views; test `test/recording_presenter_test.dart`.

- [ ] Test: presenter passes `language` through to a fake repository.
- [ ] `executeUploadRecording(File file, String? patientName, String language)`; controllers hold `String uploadLanguage = 'vi'`; iOS `selectedLocaleId` follows it (`vi_VN`/`en_US`); views show a `vi`/`en` toggle near the record button.
- [ ] `flutter test`, `flutter analyze` (0 errors/warnings); commit `feat(recording): vi/en upload language toggle (default vi)`.

### Task 8: Finish

- [ ] Update `docs/local-setup-and-testing.md` (benchmark how-to) and spec status; results table in `benchmarks/asr/README.md`.
- [ ] Full backend + mobile suites; ff-merge both branches into local `main`; no push.
