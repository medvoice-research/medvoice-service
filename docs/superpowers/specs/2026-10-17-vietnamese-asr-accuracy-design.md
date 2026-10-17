# Vietnamese ASR Accuracy — Design Spec

**Date:** 2026-10-17
**Status:** Approved (brainstorming), pending implementation plan
**Target setting:** Vietnamese outpatient clinics, CPU-only clinic server
**Approach:** A (benchmark + model swap) then B (medical vocabulary biasing)

## Problem

MedVoice's real-world target is Vietnamese outpatient care: Vietnamese speech with
English/French medical terms and brand-name drugs code-switched in, 5–10 minute visits,
on-prem CPU hardware. Today the `/recordings` path cannot serve it:

- `run_stt` hardcodes `model="base"` (`app/services/recording_pipeline.py:74`), ignoring
  `config.yaml`; `base` is weak on Vietnamese.
- Mobile always uploads `language=en` (`recording_presenter.dart` never passes it).
- There is no Vietnamese evaluation data with references: `datasets/audios/vn/` holds two
  clips (`vn-1.mp3` 74 s, `vn-2.mp3` 37 s) and no transcripts.

Every downstream feature (Vietnamese note templates, ICD-10 coding, review/sign-off) depends
on transcript quality, so accuracy is the first milestone.

## Data sources (verified 2026-10-17 on Hugging Face)

| Source | Use | License |
|---|---|---|
| `leduckhai/VietMed` | 16 h labeled Vietnamese medical speech; test split = benchmark | MIT, ungated |
| `leduckhai/VietMed-NER` | Spoken medical entity spans → medical-term recall references, vocab seed | per dataset card (check before redistribution; we only download locally) |
| `datasets/audios/vn/vn-{1,2}.mp3` | Only real doctor–patient dialogue we have | own |
| `vinai/PhoWhisper-{small,medium,large}` | Vietnamese-fine-tuned Whisper candidates | BSD-3-Clause |

PhoWhisper must run under faster-whisper (CTranslate2). Community conversions exist
(e.g. `mad1999/pho-whisper-large-ct2`); the implementation either vets one or converts
locally with `ct2-transformers-converter --quantization int8` and records the exact source.

## 1. Benchmark set

- **VietMed subset:** fixed, seeded (`seed=17`) sample of ~300 test utterances (~1 h) so a
  CPU run finishes in hours. Sample IDs are written to `benchmarks/asr/vietmed_subset.json`
  and reused by every run. Full-split runs are opt-in (`--full`).
- **Own clips:** `datasets/transcripts/vn/vn-{1,2}.txt`, hand-written references.
  **Dependency:** the user transcribes these two clips (~2 min audio); the script skips them
  with a warning until the files exist. Reported as a separate row, never averaged into
  VietMed numbers.
- **Term references:** VietMed-NER entity strings for utterances that overlap the subset.
  If overlap is too small (< 100 utterances), term recall is computed on VietMed-NER's own
  test audio instead, as a separate row.
- Downloaded audio lives in `datasets/vietmed/` (gitignored). Benchmark result JSON is committed.

## 2. Benchmark script

`scripts/asr_benchmark.py` — one file, no Temporal, no API. It calls the production
`app.whisperx_services.transcribe_with_whisper` so measured behavior equals shipped behavior.

```
uv run python scripts/asr_benchmark.py --models base,phowhisper-medium --language vi [--full] [--hotwords data/vocab/vi_medical.txt]
```

Output: `benchmarks/asr/<YYYY-MM-DD>-<model>[-<variant>].json` (per-utterance hypothesis +
metrics + run metadata: model source, compute type, CPU model, thread count) and a stdout
summary table.

### Metrics

| Metric | Definition |
|---|---|
| WER | `jiwer` word error rate after normalization: lowercase, strip punctuation, Unicode NFC. Tone marks preserved. |
| CER | Character error rate on the same normalized text. |
| Medical-term recall | Fraction of reference entity strings found as a substring of the normalized hypothesis (NFC, lowercase, tones preserved). |
| RTF | Wall-clock transcription time ÷ audio duration, transcription stage only (alignment/diarization excluded and reported separately). |
| Peak RSS | Max resident memory during the run (`resource.getrusage`). |

### Candidates (all `device=cpu`, `compute_type=int8`)

`base` (baseline), `small`, `medium`, `large-v3-turbo`, PhoWhisper small, medium, large.

## 3. Shipping the winner

- `config.yaml`: `whisperx.models_by_language: {en: base, vi: <winner>}`; `Config` exposes it.
- `run_stt(audio_path, language)` picks `models_by_language.get(language, default)` instead of
  the hardcoded `"base"`. Unknown languages fall back to the existing default.
- `WhisperModel` enum (`app/schemas.py:161`) gains the chosen PhoWhisper CT2 repo ID,
  following the existing `nyrahealth/faster_CrisperWhisper` precedent.
- Alignment for `vi` uses WhisperX's default Vietnamese wav2vec2 align model; the benchmark
  run confirms it loads (alignment is not scored, only checked for not failing).
- **Mobile:** recording screen gets a `vi`/`en` toggle (default `vi`), passed through
  `RecordingPresenter` → `AudioRepository.uploadRecording(language:)`. The multipart field
  `language` already exists in the contract; no backend contract change.

## 4. Phase B — medical vocabulary biasing

- `data/vocab/vi_medical.txt`: one term per line, ordered by frequency, seeded from
  VietMed-NER entity strings plus common outpatient drugs/diagnoses.
- Passed via existing `ASROptions.hotwords` and `initial_prompt` (`app/schemas.py:242,260`).
  faster-whisper's prompt budget is ~224 tokens, so the top-N terms that fit are used; N is
  recorded in the result JSON.
- Optional LLM post-correction (LM Studio): ships **only** if, on the benchmark, term recall
  rises **and** WER does not rise. Fabricated terms (in hypothesis, absent from reference
  and audio) are counted and reported.

## 5. Success bar

On the VietMed subset, with the chosen `vi` model:

1. WER ≥ 30 % relative improvement over `base`.
2. Medical-term recall ≥ 80 %.
3. RTF ≤ 0.4 on CPU (a 5-min visit transcribes in ≤ 2 min). Measured on the dev Mac (Apple
   Silicon, CPU only) and labeled as such; clinic x86 CPUs will be slower, so the chosen model
   must leave headroom or the next-smaller model is shipped.

If no candidate meets all three, ship the best WER that meets RTF, record the gap, and
revisit approach C (fine-tuning) as a separate spec.

## 6. Testing

- Unit test: model selection in `run_stt` — `vi` → configured model, unknown language →
  default.
- Unit test: benchmark text normalization + term-recall matching (tone-preserving, NFC).
- Mobile: repository test asserts the `language` field carries the toggle value.
- The benchmark itself is the acceptance evidence; results JSON committed.

## Out of scope

Fine-tuning (approach C), streaming ASR, diarization changes, Vietnamese note templates /
ICD-10, auth/consent, carrying over the `dev`-branch Vietnamese localization.
