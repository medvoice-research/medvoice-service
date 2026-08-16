# Mobile App API Rewrite (MedVoice Flutter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Flutter app's API layer and screens around the new medvoice-service `/recordings` contract (multipart upload -> transcript + SOAP/ICD-10/PHI document; list/get/delete). Remove the GCS service-account upload path and old MedVoice-Core endpoints.

**Architecture:** Replace `lib/data/network/constants.dart` endpoint set, rewrite `AudioRepositoryImpl` (and the `AudioRepository` interface) against the 4 new endpoints, add new domain entities matching the contract, and rewire the Recording + Medical Archive screens to the new repository. Keep the MVP pattern (controller/presenter/view). Base URL stays configurable via constants.

**Tech Stack:** Flutter 3.19.5 (per README), http package (already used), existing MVP structure. Spec: docs/superpowers/specs/2026-08-16-mobile-api-contract-design.md (in the medvoice-service repo).

**Working copy:** this repo is checked out at a path like ~/Projects/medvoice-mobile or /tmp/MedVoice-mobile. Backend contract (ground truth):
- POST /recordings (multipart: file, patient_name?, language?) -> 201 {recording_id, status, created_at, patient_name, language, transcript:{full_text, segments:[{speaker,start,end,text}]}, medical_document:{soap:{subjective,objective,assessment,plan}, entities:[{name,code,category,speaker}], phi:{detected,entities}}}
- GET /recordings -> {recordings:[{recording_id, patient_name, created_at, status, has_medical_document}]}
- GET /recordings/{id} -> same shape as POST 201
- DELETE /recordings/{id} -> 204

---

### Task 1: New domain entities matching the contract

**Files:**
- Create: `lib/domain/entities/recording/transcript_segment.dart`
- Create: `lib/domain/entities/recording/soap_note.dart`
- Create: `lib/domain/entities/recording/medical_entity.dart`
- Create: `lib/domain/entities/recording/phi_result.dart`
- Create: `lib/domain/entities/recording/medical_document.dart`
- Create: `lib/domain/entities/recording/recording_transcript.dart`
- Create: `lib/domain/entities/recording/recording_detail.dart`
- Create: `lib/domain/entities/recording/recording_summary.dart`
- Create: `lib/domain/entities/recording/recording_list.dart`
- Create: `lib/domain/entities/recording/create_recording_response.dart`
- Test: `test/recording_entities_test.dart`

- [ ] **Step 1: Write the failing test**

```dart
// test/recording_entities_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:med_voice/domain/entities/recording/medical_document.dart';
import 'package:med_voice/domain/entities/recording/recording_detail.dart';
import 'package:med_voice/domain/entities/recording/recording_list.dart';
import 'package:med_voice/domain/entities/recording/create_recording_response.dart';

void main() {
  test('RecordingDetail.fromJson parses full contract response', () {
    final detail = RecordingDetail.fromJson({
      'recording_id': 'rec_1',
      'status': 'completed',
      'created_at': '2026-08-16T03:31:12Z',
      'patient_name': 'Jane Doe',
      'language': 'en',
      'transcript': {
        'full_text': 'Hello doctor',
        'segments': [
          {'speaker': 'SPEAKER_01', 'start': 0.0, 'end': 1.0, 'text': 'Hello doctor'}
        ],
      },
      'medical_document': {
        'soap': {'subjective': 's', 'objective': 'o', 'assessment': 'a', 'plan': 'p'},
        'entities': [
          {'name': 'Hypertension', 'code': 'I10', 'category': 'diagnosis', 'speaker': 'SPEAKER_00'}
        ],
        'phi': {'detected': false, 'entities': []},
      },
    });
    expect(detail.recordingId, 'rec_1');
    expect(detail.transcript.fullText, 'Hello doctor');
    expect(detail.transcript.segments.length, 1);
    expect(detail.medicalDocument.soap.assessment, 'a');
    expect(detail.medicalDocument.entities.length, 1);
    expect(detail.medicalDocument.entities.first.code, 'I10');
    expect(detail.medicalDocument.phi.detected, false);
  });

  test('RecordingList.fromJson parses list response', () {
    final list = RecordingList.fromJson({
      'recordings': [
        {'recording_id': 'rec_1', 'patient_name': 'Jane Doe', 'created_at': '2026-08-16T03:31:12Z', 'status': 'completed', 'has_medical_document': true}
      ],
    });
    expect(list.recordings.length, 1);
    expect(list.recordings.first.hasMedicalDocument, true);
  });

  test('CreateRecordingResponse.fromJson parses POST response', () {
    final resp = CreateRecordingResponse.fromJson({
      'recording_id': 'rec_1', 'status': 'completed', 'created_at': 't', 'patient_name': null, 'language': 'en',
      'transcript': {'full_text': '', 'segments': []},
      'medical_document': {'soap': {}, 'entities': [], 'phi': {'detected': false, 'entities': []}},
    });
    expect(resp.recordingId, 'rec_1');
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/recording_entities_test.dart`
Expected: FAIL (files don't exist)

- [ ] **Step 3: Implement the entities**

```dart
// lib/domain/entities/recording/transcript_segment.dart
class TranscriptSegment {
  final String speaker;
  final double start;
  final double end;
  final String text;

  TranscriptSegment({required this.speaker, required this.start, required this.end, required this.text});

  factory TranscriptSegment.fromJson(Map<String, dynamic> json) => TranscriptSegment(
        speaker: json['speaker'] as String? ?? '',
        start: (json['start'] as num?)?.toDouble() ?? 0,
        end: (json['end'] as num?)?.toDouble() ?? 0,
        text: json['text'] as String? ?? '',
      );
}
```

```dart
// lib/domain/entities/recording/soap_note.dart
class SoapNote {
  final String subjective;
  final String objective;
  final String assessment;
  final String plan;

  SoapNote({required this.subjective, required this.objective, required this.assessment, required this.plan});

  factory SoapNote.fromJson(Map<String, dynamic> json) => SoapNote(
        subjective: json['subjective'] as String? ?? '',
        objective: json['objective'] as String? ?? '',
        assessment: json['assessment'] as String? ?? '',
        plan: json['plan'] as String? ?? '',
      );

  bool get isEmpty => subjective.isEmpty && objective.isEmpty && assessment.isEmpty && plan.isEmpty;
}
```

```dart
// lib/domain/entities/recording/medical_entity.dart
class MedicalEntity {
  final String name;
  final String code;
  final String category;
  final String speaker;

  MedicalEntity({required this.name, required this.code, required this.category, required this.speaker});

  factory MedicalEntity.fromJson(Map<String, dynamic> json) => MedicalEntity(
        name: json['name'] as String? ?? '',
        code: json['code'] as String? ?? '',
        category: json['category'] as String? ?? '',
        speaker: json['speaker'] as String? ?? '',
      );
}
```

```dart
// lib/domain/entities/recording/phi_result.dart
class PhiResult {
  final bool detected;
  final List<dynamic> entities;

  PhiResult({required this.detected, required this.entities});

  factory PhiResult.fromJson(Map<String, dynamic> json) => PhiResult(
        detected: json['detected'] as bool? ?? false,
        entities: json['entities'] as List? ?? [],
      );
}
```

```dart
// lib/domain/entities/recording/medical_document.dart
import 'medical_entity.dart';
import 'phi_result.dart';
import 'soap_note.dart';

class MedicalDocument {
  final SoapNote soap;
  final List<MedicalEntity> entities;
  final PhiResult phi;

  MedicalDocument({required this.soap, required this.entities, required this.phi});

  factory MedicalDocument.fromJson(Map<String, dynamic> json) => MedicalDocument(
        soap: SoapNote.fromJson(json['soap'] as Map<String, dynamic>? ?? {}),
        entities: ((json['entities'] as List?) ?? [])
            .map((e) => MedicalEntity.fromJson(e as Map<String, dynamic>))
            .toList(),
        phi: PhiResult.fromJson(json['phi'] as Map<String, dynamic>? ?? {}),
      );
}
```

```dart
// lib/domain/entities/recording/recording_transcript.dart
import 'transcript_segment.dart';

class RecordingTranscript {
  final String fullText;
  final List<TranscriptSegment> segments;

  RecordingTranscript({required this.fullText, required this.segments});

  factory RecordingTranscript.fromJson(Map<String, dynamic> json) => RecordingTranscript(
        fullText: json['full_text'] as String? ?? '',
        segments: ((json['segments'] as List?) ?? [])
            .map((s) => TranscriptSegment.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}
```

```dart
// lib/domain/entities/recording/recording_detail.dart
import 'medical_document.dart';
import 'recording_transcript.dart';

class RecordingDetail {
  final String recordingId;
  final String status;
  final String createdAt;
  final String? patientName;
  final String language;
  final RecordingTranscript transcript;
  final MedicalDocument medicalDocument;

  RecordingDetail({
    required this.recordingId,
    required this.status,
    required this.createdAt,
    required this.patientName,
    required this.language,
    required this.transcript,
    required this.medicalDocument,
  });

  factory RecordingDetail.fromJson(Map<String, dynamic> json) => RecordingDetail(
        recordingId: json['recording_id'] as String? ?? '',
        status: json['status'] as String? ?? '',
        createdAt: json['created_at'] as String? ?? '',
        patientName: json['patient_name'] as String?,
        language: json['language'] as String? ?? 'en',
        transcript: RecordingTranscript.fromJson(json['transcript'] as Map<String, dynamic>? ?? {}),
        medicalDocument: MedicalDocument.fromJson(json['medical_document'] as Map<String, dynamic>? ?? {}),
      );
}
```

```dart
// lib/domain/entities/recording/recording_summary.dart
class RecordingSummary {
  final String recordingId;
  final String? patientName;
  final String createdAt;
  final String status;
  final bool hasMedicalDocument;

  RecordingSummary({
    required this.recordingId,
    required this.patientName,
    required this.createdAt,
    required this.status,
    required this.hasMedicalDocument,
  });

  factory RecordingSummary.fromJson(Map<String, dynamic> json) => RecordingSummary(
        recordingId: json['recording_id'] as String? ?? '',
        patientName: json['patient_name'] as String?,
        createdAt: json['created_at'] as String? ?? '',
        status: json['status'] as String? ?? '',
        hasMedicalDocument: json['has_medical_document'] as bool? ?? false,
      );
}
```

```dart
// lib/domain/entities/recording/recording_list.dart
import 'recording_summary.dart';

class RecordingList {
  final List<RecordingSummary> recordings;

  RecordingList({required this.recordings});

  factory RecordingList.fromJson(Map<String, dynamic> json) => RecordingList(
        recordings: ((json['recordings'] as List?) ?? [])
            .map((r) => RecordingSummary.fromJson(r as Map<String, dynamic>))
            .toList(),
      );
}
```

```dart
// lib/domain/entities/recording/create_recording_response.dart
import 'recording_detail.dart';

class CreateRecordingResponse extends RecordingDetail {
  CreateRecordingResponse({
    required super.recordingId,
    required super.status,
    required super.createdAt,
    required super.patientName,
    required super.language,
    required super.transcript,
    required super.medicalDocument,
  });

  factory CreateRecordingResponse.fromJson(Map<String, dynamic> json) =>
      CreateRecordingResponse(
        recordingId: json['recording_id'] as String? ?? '',
        status: json['status'] as String? ?? '',
        createdAt: json['created_at'] as String? ?? '',
        patientName: json['patient_name'] as String?,
        language: json['language'] as String? ?? 'en',
        transcript: RecordingTranscript.fromJson(json['transcript'] as Map<String, dynamic>? ?? {}),
        medicalDocument: MedicalDocument.fromJson(json['medical_document'] as Map<String, dynamic>? ?? {}),
      );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test test/recording_entities_test.dart`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/domain/entities/recording/ test/recording_entities_test.dart
git commit -m "feat: add recording domain entities matching API contract"
```

---

### Task 2: Rewrite the API layer (constants + repository)

**Files:**
- Modify: `lib/data/network/constants.dart`
- Modify: `lib/data/repository_impl/audio_repository_impl.dart`
- Modify: `lib/domain/repositories/audio_repository/audio_repository.dart`
- Test: `test/audio_repository_test.dart`

- [ ] **Step 1: Write the failing test (repository against new contract)**

```dart
// test/audio_repository_test.dart
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:med_voice/data/network/constants.dart';
import 'package:med_voice/data/repository_impl/audio_repository_impl.dart';

void main() {
  Constants.baseUrl = 'http://test.local:8000/';

  test('uploadRecording posts multipart and parses response', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/recordings');
      expect(request.headers['content-type'], contains('multipart/form-data'));
      return http.Response(
        jsonEncode({
          'recording_id': 'rec_1', 'status': 'completed', 'created_at': 't',
          'patient_name': 'Jane', 'language': 'en',
          'transcript': {'full_text': 'Hello', 'segments': []},
          'medical_document': {'soap': {}, 'entities': [], 'phi': {'detected': false, 'entities': []}},
        }),
        201,
        headers: {'content-type': 'application/json'},
      );
    });
    final repo = AudioRepositoryImpl.withClient(mock);
    final result = await repo.uploadRecording(
      fileBytes: Uint8List.fromList([1, 2, 3]),
      fileName: 'a.m4a',
      patientName: 'Jane',
    );
    expect(result.recordingId, 'rec_1');
    expect(result.transcript.fullText, 'Hello');
  });

  test('listRecordings parses list', () async {
    final mock = MockClient((request) async {
      expect(request.url.path, '/recordings');
      return http.Response(
        jsonEncode({'recordings': [
          {'recording_id': 'rec_1', 'patient_name': null, 'created_at': 't', 'status': 'completed', 'has_medical_document': true}
        ]}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final repo = AudioRepositoryImpl.withClient(mock);
    final list = await repo.listRecordings();
    expect(list.recordings.length, 1);
    expect(list.recordings.first.recordingId, 'rec_1');
  });

  test('getRecordingDetail fetches by id', () async {
    final mock = MockClient((request) async {
      expect(request.url.path, '/recordings/rec_1');
      return http.Response(
        jsonEncode({'recording_id': 'rec_1', 'status': 'completed', 'created_at': 't', 'patient_name': null, 'language': 'en',
          'transcript': {'full_text': 'X', 'segments': []},
          'medical_document': {'soap': {}, 'entities': [], 'phi': {'detected': false, 'entities': []}}}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final repo = AudioRepositoryImpl.withClient(mock);
    final detail = await repo.getRecordingDetail('rec_1');
    expect(detail.recordingId, 'rec_1');
  });

  test('deleteRecording expects 204', () async {
    final mock = MockClient((request) async {
      expect(request.method, 'DELETE');
      return http.Response('', 204);
    });
    final repo = AudioRepositoryImpl.withClient(mock);
    await repo.deleteRecording('rec_1'); // should not throw
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test test/audio_repository_test.dart`
Expected: FAIL (no uploadRecording/listRecordings/getRecordingDetail/deleteRecording methods; AudioRepositoryImpl has no `client` constructor param)

- [ ] **Step 3: Update constants**

```dart
// lib/data/network/constants.dart (full rewrite)
class Constants {
  static String baseUrl = "http://localhost:8000/";

  // Recordings API (medvoice-service contract v1)
  static String get recordings => "${baseUrl}recordings";
  static String recordingDetail(String id) => "${baseUrl}recordings/$id";
}
```

- [ ] **Step 4: Rewrite the repository interface**

```dart
// lib/domain/repositories/audio_repository/audio_repository.dart (full rewrite)
import 'dart:typed_data';

import '../../entities/recording/recording_detail.dart';
import '../../entities/recording/recording_list.dart';

abstract class AudioRepository {
  Future<RecordingDetail> uploadRecording({
    required Uint8List fileBytes,
    required String fileName,
    String? patientName,
    String language,
  });
  Future<RecordingList> listRecordings();
  Future<RecordingDetail> getRecordingDetail(String recordingId);
  Future<void> deleteRecording(String recordingId);
}
```

- [ ] **Step 5: Rewrite the repository implementation**

```dart
// lib/data/repository_impl/audio_repository_impl.dart (full rewrite)
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../../domain/entities/recording/recording_detail.dart';
import '../../domain/entities/recording/recording_list.dart';
import '../../domain/repositories/audio_repository/audio_repository.dart';
import '../network/constants.dart';

class AudioRepositoryImpl implements AudioRepository {
  static final AudioRepositoryImpl _instance = AudioRepositoryImpl._internal();

  AudioRepositoryImpl._internal() : _client = http.Client();

  factory AudioRepositoryImpl() => _instance;

  // Injectable client for tests; defaults to the real http package.
  @visibleForTesting
  AudioRepositoryImpl.withClient(this._client);

  final http.Client _client;

  @override
  Future<RecordingDetail> uploadRecording({
    required Uint8List fileBytes,
    required String fileName,
    String? patientName,
    String language = 'en',
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse(Constants.recordings))
      ..files.add(http.MultipartFile.fromBytes('file', fileBytes,
          filename: fileName, contentType: MediaType('application', 'octet-stream')))
      ..fields['language'] = language;
    if (patientName != null) {
      request.fields['patient_name'] = patientName;
    }
    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);
    if (response.statusCode != 201) {
      throw Exception('Upload failed: ${response.statusCode} ${response.body}');
    }
    return RecordingDetail.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  @override
  Future<RecordingList> listRecordings() async {
    final response = await _client.get(Uri.parse(Constants.recordings));
    if (response.statusCode != 200) {
      throw Exception('List failed: ${response.statusCode}');
    }
    return RecordingList.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  @override
  Future<RecordingDetail> getRecordingDetail(String recordingId) async {
    final response = await _client.get(Uri.parse(Constants.recordingDetail(recordingId)));
    if (response.statusCode != 200) {
      throw Exception('Get failed: ${response.statusCode}');
    }
    return RecordingDetail.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  @override
  Future<void> deleteRecording(String recordingId) async {
    final response = await _client.delete(Uri.parse(Constants.recordingDetail(recordingId)));
    if (response.statusCode != 204) {
      throw Exception('Delete failed: ${response.statusCode}');
    }
  }
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `flutter test test/audio_repository_test.dart`
Expected: PASS (4 tests)

- [ ] **Step 7: Remove now-dead code**

Delete these files (no longer referenced after repository rewrite — verify with `grep -rn` first that nothing imports them):
- `lib/domain/entities/recording/audio_transcript_info.dart`
- `lib/domain/entities/recording/audio_transcript_response.dart`
- `lib/domain/entities/recording/upload_recording_request.dart`
- `lib/domain/entities/recording/recording_archive_info.dart`
- `lib/domain/entities/recording/recording_archive_response.dart`
- `lib/domain/entities/recording/library_transcript/*` (all files in that dir)
- `lib/domain/entities/recording/local_recording_entity/recording_upload_info.dart`
- `lib/domain/entities/recording/sentences_info.dart`
- `lib/domain/entities/recording/sentences_response.dart`
- `lib/data/repository_impl/ask_repository_impl.dart` (Q&A deferred)

For each file: `grep -rn "import.*<filename_without_ext>" lib/ test/` — if zero references, `git rm` it. If referenced, fix the importer first. Run `flutter analyze` after; expect zero errors.

- [ ] **Step 8: Commit**

```bash
git add lib/data/network/constants.dart lib/domain/repositories/audio_repository/audio_repository.dart lib/data/repository_impl/audio_repository_impl.dart test/audio_repository_test.dart
git commit -m "feat: rewrite audio repository for recordings API contract"
git rm <each dead file confirmed in Step 7>
git commit -m "refactor: remove dead MedVoice-Core API layer"
```

---

### Task 3: Rewire the recording screen to upload via the new repository

**Files:**
- Modify: `lib/app/pages/home/recording/recording/recording_presenter.dart`
- Modify: `lib/app/pages/home/recording/recording/recording_controller.dart`
- Modify: `lib/app/pages/home/recording/recording/recording_view.dart`
- Modify: `lib/app/pages/home/main/main_presenter.dart` (if it references old archive methods)

- [ ] **Step 1: Inspect the current recording flow**

Run: `grep -rn "uploadAudioFile\|uploadAudioInfo\|uploadLibraryTranscript\|AudioRepository" lib/app/pages/home/recording/ lib/app/pages/home/main/`
Read each file that references the old repository methods. The goal: after recording finishes, the view/controller should call `AudioRepositoryImpl().uploadRecording(fileBytes: ..., fileName: ..., patientName: ...)` and navigate to a detail/result display.

- [ ] **Step 2: Update the presenter to expose upload**

In `recording_presenter.dart`, replace any calls to the old repository methods with:
```dart
final result = await AudioRepositoryImpl().uploadRecording(
  fileBytes: bytes,
  fileName: fileName,
  patientName: patientName,
);
```
where `bytes` is a `Uint8List` of the recorded file and `fileName` is e.g. `rec_<timestamp>.m4a`. Keep the presenter's existing loading/error state pattern; on success, store `result` for the view.

- [ ] **Step 3: Update the view to show the result**

In `recording_view.dart`, after successful upload show a simple result summary: transcript full text, SOAP sections (S/O/A/P), entity names, and a PHI warning banner if `medicalDocument.phi.detected`. Keep it minimal — full detail rendering is Task 5. Use `flutter analyze` to catch unused imports.

- [ ] **Step 4: Run analyze + tests**

Run: `flutter analyze`
Expected: no errors.
Run: `flutter test`
Expected: existing tests pass (update `test/widget_test.dart` if it pings old flows — keep the smoke test compiling).

- [ ] **Step 5: Commit**

```bash
git add lib/app/pages/home/recording/ test/
git commit -m "feat: wire recording screen to new upload API"
```

---

### Task 4: Medical archive screen -> recordings list

**Files:**
- Modify: `lib/app/pages/home/medical_archive/medical_archive_presenter.dart`
- Modify: `lib/app/pages/home/medical_archive/medical_archive_controller.dart`
- Modify: `lib/app/pages/home/medical_archive/medical_archive_view.dart`

- [ ] **Step 1: Inspect the current archive flow**

Run: `grep -rn "getAudioArchive\|getLibraryTranscript\|RecordingArchive" lib/app/pages/home/medical_archive/`
Read the presenter/controller/view. The archive screen currently lists audio URLs from the old `get_audios_from_user` endpoint.

- [ ] **Step 2: Rewire to listRecordings**

Replace old repository calls with:
```dart
final list = await AudioRepositoryImpl().listRecordings();
```
Display each `RecordingSummary` as a list tile: patient name (or recording id), created date, and a badge for `hasMedicalDocument`. Tap navigates to the detail screen (Task 5).

- [ ] **Step 3: Run analyze + tests**

Run: `flutter analyze` and `flutter test`
Expected: no errors, tests pass.

- [ ] **Step 4: Commit**

```bash
git add lib/app/pages/home/medical_archive/
git commit -m "feat: rewire medical archive to recordings list"
```

---

### Task 5: Recording detail screen

**Files:**
- Create: `lib/app/pages/home/medical_archive/recording_detail/recording_detail_controller.dart`
- Create: `lib/app/pages/home/medical_archive/recording_detail/recording_detail_presenter.dart`
- Create: `lib/app/pages/home/medical_archive/recording_detail/recording_detail_view.dart`
- Modify: `lib/app/utils/router.dart` (register route) and `lib/app/utils/pages.dart`

- [ ] **Step 1: Create the detail page (MVP triad)**

Follow the existing triad pattern in `lib/app/pages/home/medical_archive/audio_playback/` as the template. The controller takes a `recordingId`; the presenter calls `AudioRepositoryImpl().getRecordingDetail(recordingId)`; the view renders:

- Header: patient name, created_at, language
- Transcript: full_text in a scrollable card
- SOAP: four labeled sections (Subjective/Objective/Assessment/Plan) — hide a section if empty
- Entities: list of `name` (`code`) with `category` chip
- PHI: red banner "PHI detected" listing entity texts when `phi.detected` is true; green "No PHI detected" otherwise
- Delete button -> `AudioRepositoryImpl().deleteRecording(id)` -> pop back with a refresh signal

Use `Scaffold`, `AppBar(title: Text('Recording'))`, `ListView` children. No new packages.

- [ ] **Step 2: Register the route**

In `lib/app/utils/router.dart` (and `pages.dart`), register the new page following the existing route registration pattern (read the file first).

- [ ] **Step 3: Run analyze + tests**

Run: `flutter analyze` and `flutter test`
Expected: no errors, tests pass.

- [ ] **Step 4: Commit**

```bash
git add lib/app/pages/home/medical_archive/recording_detail/ lib/app/utils/router.dart lib/app/utils/pages.dart
git commit -m "feat: add recording detail screen"
```

---

### Task 6: Config, cleanup, verification

**Files:**
- Modify: `README.md`
- Modify: `lib/data/network/constants.dart` (base URL documentation comment)

- [ ] **Step 1: Update README**

In README.md, replace the old backend/endpoint references with a short section: "Backend: medvoice-service (github.com/medvoice-research/medvoice-service). Set `Constants.baseUrl` in lib/data/network/constants.dart to your server (localhost:8000 for emulator, LAN IP or ngrok URL for physical device)."

- [ ] **Step 2: Final verification**

Run: `flutter analyze` — zero errors.
Run: `flutter test` — all pass.
Run: `grep -rn "get_audios_from_user\|process_audio_v2\|process_transcript\|get_transcript\|googleapis\|askEndpoint" lib/`
Expected: no matches (dead old-contract code fully removed).

- [ ] **Step 3: Commit**

```bash
git add README.md lib/data/network/constants.dart
git commit -m "docs: update app README for medvoice-service backend"
```
