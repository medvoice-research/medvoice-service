# Audio Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore "re-listen the recording" — backend serves stored audio via a new endpoint + `audio_url` field; mobile entity carries the URL; recording detail screen gets a Play button.

**Architecture:** Backend: `FileResponse` route + `audio_url` in the existing GET detail payload (reuses `RecordingStore.audio_path`). Mobile: nullable `audioUrl` on `RecordingDetail`, play button on `recording_detail_view.dart` navigating to the existing `AudioPlaybackView` (just_audio, no changes needed).

**Tech Stack:** FastAPI (`FileResponse`), Flutter/fvm 3.19.5, existing just_audio screen, flutter_clean_architecture.

Spec: `docs/superpowers/specs/2026-08-23-audio-replay-design.md`

---

### Task 1: Backend — audio_url + audio endpoint

**Files:**
- Modify: `app/routers/recordings.py`
- Test: `tests/integration/test_recordings_api.py` (extend) or new `tests/integration/test_audio_replay.py`

- [ ] **Step 1: Write the failing test**

Follow the client-fixture pattern already used in `tests/integration/test_recordings_api.py`.
Add a test that creates a recording via POST (or uses an existing seeded fixture), then:

```python
def test_recording_detail_includes_audio_url(client):
    # POST /recordings with datasets/audios/sg/sg-1.WAV (mock the pipeline if the
    # existing suite does; otherwise use whatever create path the suite uses)
    ...
    detail = client.get(f"/recordings/{rid}").json()
    assert detail["audio_url"] == f"/recordings/{rid}/audio"

    response = client.get(detail["audio_url"])
    assert response.status_code == 200
    assert len(response.content) > 0  # audio bytes served
```

Also:
- `GET /recordings/{rid}/audio` with a bogus id → 404 with `error_code == "recording_not_found"`.
- A recording whose audio file was deleted → detail has `audio_url == None` (or key absent),
  and `GET .../audio` → 404.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_audio_replay.py -v`
Expected: FAIL — `audio_url` key missing / route 404.

- [ ] **Step 3: Implement**

In `app/routers/recordings.py`:

```python
from fastapi.responses import FileResponse  # add to existing fastapi imports

@router.get("/recordings/{recording_id}/audio", summary="Serve the stored audio file")
async def get_recording_audio(recording_id: str):
    if not is_valid_recording_id(recording_id):
        raise _not_found()
    store = get_store()
    try:
        path = store.audio_path(recording_id)
    except FileNotFoundError:
        raise _not_found()
    if not path.exists():
        raise _not_found()
    return FileResponse(path)
```

In the existing `get_recording` handler, add to the returned dict:

```python
    audio = store.audio_path(recording_id) if meta else None
    ...
    return {
        **meta,
        "audio_url": f"/recordings/{recording_id}/audio" if audio and audio.exists() else None,
        "transcript": ...,
        "medical_document": ...,
    }
```

NOTE: `store.audio_path` raises `FileNotFoundError` when meta is missing — handle it
(the id is already validated + meta loaded above the return, so guard accordingly).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_audio_replay.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/recordings.py tests/integration/test_audio_replay.py
git commit -m "feat(recordings): serve audio replay via GET /recordings/{id}/audio + audio_url"
```

---

### Task 2: Mobile — entity field + Play button

**Files:**
- Modify: `lib/domain/entities/recording/recording_detail.dart`
- Modify: `lib/app/pages/home/medical_archive/recording_detail/recording_detail_view.dart`
- Test: extend `test/audio_repository_test.dart` or the entities test file

- [ ] **Step 1: Write the failing test**

Add to the existing recording-entity test file (check `test/recording_entities_test.dart`
for the current fromJson fixture style):

```dart
test('RecordingDetail.fromJson parses audio_url', () {
  final withAudio = RecordingDetail.fromJson({
    ...minimalJson,
    'audio_url': '/recordings/rec_x/audio',
  });
  expect(withAudio.audioUrl, '/recordings/rec_x/audio');

  final without = RecordingDetail.fromJson(minimalJson);
  expect(without.audioUrl, isNull);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter test test/recording_entities_test.dart`
Expected: FAIL — `audioUrl` doesn't exist on RecordingDetail.

- [ ] **Step 3: Implement**

`lib/domain/entities/recording/recording_detail.dart` — add field + constructor param + parse:

```dart
  final String? audioUrl;
  // in fromJson:
  audioUrl: json['audio_url'] as String?,
```

`lib/app/pages/home/medical_archive/recording_detail/recording_detail_view.dart` —
insert before the Delete button (after `...buildRecordingResult(context, detail)`):

```dart
                FilledButton.tonalIcon(
                  onPressed: () => _playRecording(context, detail),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Play recording'),
                ),
                const SizedBox(height: 8),
```

Add helper (mirroring the delete-dialog style):

```dart
  void _playRecording(BuildContext context, RecordingDetail detail) {
    final url = detail.audioUrl;
    if (url == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Audio unavailable for this recording.')),
      );
      return;
    }
    final absolute = url.startsWith('http') ? url : '${Constants.baseUrl}$url';
    pushScreen(Pages.audioPlayback,
        arguments: {recordingInfo: absolute});
  }
```

Imports to add: `package:med_voice/data/network/constants.dart`,
`package:med_voice/app/utils/pages.dart`,
`package:med_voice/app/pages/home/medical_archive/audio_playback/audio_playback_view.dart`
(recordingInfo const lives there — reuse it, don't redefine).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter test test/recording_entities_test.dart`
Expected: PASS

- [ ] **Step 5: Analyze + full suite (no regressions)**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter analyze && fvm flutter test`
Expected: No NEW analyzer issues (baseline is 173 pre-existing); all tests green.

- [ ] **Step 6: Commit**

```bash
git add lib/domain/entities/recording/recording_detail.dart \
        lib/app/pages/home/medical_archive/recording_detail/recording_detail_view.dart \
        test/recording_entities_test.dart
git commit -m "feat(recording): re-listen — audioUrl entity field + Play button on detail screen"
```
