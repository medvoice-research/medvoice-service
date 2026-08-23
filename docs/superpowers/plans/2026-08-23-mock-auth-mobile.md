# Mock Auth Mobile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The MedVoice Flutter login screen calls the real `POST /auth/login`, shows errors on 401/network failure, navigates to Main on success.

**Architecture:** Follows the existing clean-arch layering used for recordings: entity (`AuthResult`) → abstract repository → `AuthRepositoryImpl` (http) → controller consumes it. Injectable `http.Client` mirrors `AudioRepositoryImpl.withClient` for MockClient tests.

**Tech Stack:** Flutter (fvm, 3.19.5), flutter_clean_architecture, http + http_parser, provider. Backend contract: see `docs/superpowers/specs/2026-08-23-mock-auth-login-design.md` §2.

---

### Task 1: Constants + entities

**Files:**
- Modify: `lib/data/network/constants.dart`
- Create: `lib/domain/entities/auth/auth_user.dart`

- [ ] **Step 1: Add auth URL to constants**

In `lib/data/network/constants.dart`, after `recordingDetail`:

```dart
  /// POST /auth/login — mock-account login.
  static String get authLogin => "${baseUrl}auth/login";
```

- [ ] **Step 2: Create entities matching backend response**

```dart
class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.fullName,
    required this.role,
  });

  final int id;
  final String email;
  final String fullName;
  final String role;

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: json['id'] as int,
        email: json['email'] as String,
        fullName: (json['full_name'] ?? '') as String,
        role: (json['role'] ?? 'physician') as String,
      );
}

class AuthException implements Exception {
  const AuthException(this.code);

  /// 'invalid_credentials' (401) or 'network_error' (unreachable / 5xx).
  final String code;

  String get message =>
      code == 'invalid_credentials' ? 'Invalid email or password.' : 'Cannot reach server.';
}

class AuthResult {
  const AuthResult({required this.accessToken, required this.user});

  final String accessToken;
  final AuthUser user;

  factory AuthResult.fromJson(Map<String, dynamic> json) => AuthResult(
        accessToken: json['access_token'] as String,
        user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
      );
}
```

- [ ] **Step 3: Analyze**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter analyze lib/domain lib/data`
Expected: No issues in the new files.

---

### Task 2: Repository interface + impl

**Files:**
- Create: `lib/domain/repositories/auth_repository/auth_repository.dart`
- Create: `lib/data/repository_impl/auth_repository_impl.dart`
- Test: `test/auth_repository_test.dart`

- [ ] **Step 1: Abstract repository**

```dart
import '../../entities/auth/auth_user.dart';

abstract class AuthRepository {
  Future<AuthResult> login(String email, String password);
}
```

(Match the exact directory/file layout of `audio_repository` — check how
`lib/domain/repositories/audio_repository/audio_repository.dart` is structured first.)

- [ ] **Step 2: Write the failing test**

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:med_voice/data/repository_impl/auth_repository_impl.dart';
import 'package:med_voice/domain/entities/auth/auth_user.dart';

void main() {
  group('AuthRepositoryImpl.login', () {
    test('parses token and user on 200', () async {
      final client = _MockClient((request) async => http.Response(
            '{"access_token":"jwt123","token_type":"bearer","user":'
            '{"id":1,"email":"doctor@medvoice.local","full_name":"Dr. Demo","role":"physician"}}',
            200,
            headers: {'content-type': 'application/json'},
          ));
      final repo = AuthRepositoryImpl.withClient(client);

      final result = await repo.login('doctor@medvoice.local', 'pw');

      expect(result.accessToken, 'jwt123');
      expect(result.user.email, 'doctor@medvoice.local');
      expect(result.user.role, 'physician');
    });

    test('throws invalid_credentials on 401', () async {
      final client = _MockClient((request) async => http.Response(
            '{"detail":"Invalid email or password","error_code":"invalid_credentials"}',
            401,
            headers: {'content-type': 'application/json'},
          ));
      final repo = AuthRepositoryImpl.withClient(client);

      await expectLater(
        repo.login('doctor@medvoice.local', 'bad'),
        throwsA(isA<AuthException>().having((e) => e.code, 'code', 'invalid_credentials')),
      );
    });

    test('throws network_error on server error / bad JSON shape', () async {
      final client = _MockClient((request) async => http.Response('{"detail": "boom"}', 500));
      final repo = AuthRepositoryImpl.withClient(client);

      await expectLater(
        repo.login('a@b.co', 'pw'),
        throwsA(isA<AuthException>().having((e) => e.code, 'code', 'network_error')),
      );
    });
  });
}

class _MockClient extends http.BaseClient {
  _MockClient(this.handler);
  final Future<http.Response> Function(http.Request) handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final response = await handler(request as http.Request);
    return http.StreamedResponse(
      Stream.value(response.bodyBytes),
      response.statusCode,
      headers: response.headers,
    );
  }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter test test/auth_repository_test.dart`
Expected: FAIL — `AuthRepositoryImpl` doesn't exist yet.

- [ ] **Step 4: Implement**

```dart
import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:http/http.dart' as http;

import '../../domain/entities/auth/auth_user.dart';
import '../../domain/repositories/auth_repository/auth_repository.dart';
import '../network/constants.dart';

class AuthRepositoryImpl implements AuthRepository {
  static final AuthRepositoryImpl _instance = AuthRepositoryImpl._internal();

  AuthRepositoryImpl._internal() : _client = http.Client();

  factory AuthRepositoryImpl() => _instance;

  // Injectable client for tests; defaults to the real http package.
  @visibleForTesting
  AuthRepositoryImpl.withClient(this._client);

  final http.Client _client;

  @override
  Future<AuthResult> login(String email, String password) async {
    try {
      final response = await _client.post(
        Uri.parse(Constants.authLogin),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}),
      );
      if (response.statusCode == 200) {
        return AuthResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      }
      if (response.statusCode == 401) {
        throw const AuthException('invalid_credentials');
      }
      throw const AuthException('network_error');
    } on AuthException {
      rethrow;
    } catch (_) {
      throw const AuthException('network_error');
    }
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter test test/auth_repository_test.dart`
Expected: PASS (3 tests)

---

### Task 3: Wire the sign-in screen

**Files:**
- Modify: `lib/app/pages/onboarding/login/sign_in_controller.dart`
- Modify: `lib/app/pages/onboarding/login/sign_in_view.dart`

- [ ] **Step 1: Controller — async submit with loading + error state**

Replace the body of `_SignInController`/`SignInController.submitForm()` logic:

```dart
bool isLoading = false;
String? errorMessage;

Future<bool> submitForm() async {
  if (!formKey.currentState!.validate()) {
    return false;
  }
  isLoading = true;
  errorMessage = null;
  onStateChanged(); // notify listeners if the base class has an equivalent; else use setState via view
  try {
    await AuthRepositoryImpl().login(
      emailController.text.trim(),
      passwordController.text,
    );
    return true;
  } on AuthException catch (e) {
    errorMessage = e.message;
    return false;
  } finally {
    isLoading = false;
    onStateChanged();
  }
}
```

IMPORTANT: read `common/base_controller.dart` FIRST and use whatever notify/rebuild
mechanism the codebase already uses (flutter_clean_architecture controllers typically
call `refreshUI()` / have `onListener`). Do NOT invent a new state mechanism — adapt
the sketch to the existing pattern so the view rebuilds when `isLoading` flips.
Keep `submitForm()` returning bool=false on failure so navigation stays in the view.

- [ ] **Step 2: View — spinner + SnackBar, navigate only on success**

In `sign_in_view.dart` ElevatedButton:

```dart
onPressed: _controller.isLoading
    ? null
    : () async {
        FocusScope.of(context).unfocus();
        final ok = await _controller.submitForm();
        if (!mounted) return;
        if (ok) {
          pushScreen(Pages.main, isAllowBack: false);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(_controller.errorMessage ?? 'Login failed.')),
          );
        }
      },
child: _controller.isLoading
    ? SizedBox(
        width: toSize(20), height: toSize(20),
        child: CircularProgressIndicator(color: theme.colorScheme.surface, strokeWidth: 2),
      )
    : Text("Log in", /* existing style */),
```

- [ ] **Step 3: Analyze + existing tests**

Run: `cd ~/Projects/medvoice-mobile && fvm flutter analyze && fvm flutter test`
Expected: No NEW issues; all pre-existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add lib/data/network/constants.dart lib/domain/entities/auth lib/domain/repositories/auth_repository \
        lib/data/repository_impl/auth_repository_impl.dart test/auth_repository_test.dart \
        lib/app/pages/onboarding/login/sign_in_controller.dart lib/app/pages/onboarding/login/sign_in_view.dart
git commit -m "feat(login): wire sign-in screen to POST /auth/login with error handling"
```
