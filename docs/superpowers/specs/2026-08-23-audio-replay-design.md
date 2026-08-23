# Audio Replay for Recordings — Design

Date: 2026-08-23
Status: Approved (unattended execution authorized)
Scope: medvoice-service (backend) + medvoice-mobile (Flutter app)

## 1. Context & Goals

The capstone-era app had a re-listen feature: `AudioPlaybackView` (just_audio) that
plays a recording URL passed via `Pages.audioPlayback` route. In the modern rewrite
this screen still exists but is **orphaned** — nothing navigates to it, the
`RecordingDetail` entity carries no audio URL, and the backend never serves the
stored audio back (audio goes in, gets transcribed, and is only reachable on disk).

Goal: restore re-listening end-to-end. Backend exposes the stored audio; mobile
entity carries the URL; recording detail screen gets a "Play recording" button.

## 2. Backend (medvoice-service)

### GET /recordings/{recording_id} — add `audio_url`
Response gains a top-level field alongside the existing keys:
```json
{
  "recording_id": "rec_...",
  "status": "completed",
  "audio_url": "/recordings/rec_.../audio",
  ...
}
```
- `audio_url` = relative path string; null/omitted if the audio file is missing on disk.
- The audio file already lives at `RecordingStore.audio_path(recording_id)`
  (`data/recordings/{id}/audio.<ext>`), so only meta plumbing is needed.

### GET /recordings/{recording_id}/audio — serve the file
- `FileResponse` on `store.audio_path(recording_id)`.
- 404 with the existing envelope (`{"detail": ..., "error_code": "recording_not_found"}`)
  for invalid/missing ids; 404 also if the audio file itself is missing.
- Content-Type from the stored extension (e.g. audio/wav). FastAPI's FileResponse
  handles this via filename inference; pass media_type explicitly if needed.

### Envelope
Follow the existing `RecordingError` pattern from `app/routers/recordings.py`
(HTTPException subclass with `error_code`, flattened by `app.main`'s
`flat_error_handler`).

## 3. Mobile (medvoice-mobile)

### Entity: `RecordingDetail` gets `audioUrl`
- Add `final String? audioUrl;` + parse from `json['audio_url']` in `fromJson`
  (nullable; old payloads / recordings without audio keep working).

### Wire the button: `recording_detail_view.dart`
- Above the "Delete recording" button, add a play button:
  `FilledButton.tonalIcon(icon: Icon(Icons.play_arrow), label: Text('Play recording'))`.
- `onPressed` → if `detail.audioUrl != null`:
  `pushScreen(Pages.audioPlayback, arguments: {recordingInfo: _absoluteUrl(detail.audioUrl!)})`
  where `_absoluteUrl` prefixes `Constants.baseUrl` when the value is relative
  (it is, per the backend contract). If `audioUrl == null`, show a SnackBar
  ("Audio unavailable for this recording.").
- `AudioPlaybackView` needs no changes — it already `setUrl(recordingInfo)` + plays.

### Tests
- Extend `test/audio_repository_test.dart` (or entity test) to cover
  `RecordingDetail.fromJson` with and without `audio_url`.
- Widget test for the detail view play button: renders button when audioUrl present,
  shows snackbar when null (optional if cheap; match existing test style).

## 4. Out of scope
- Streaming/progress endpoints, waveform UI, server-side playback analytics.
- Re-listen for old capstone-era recordings (not in the new store).
