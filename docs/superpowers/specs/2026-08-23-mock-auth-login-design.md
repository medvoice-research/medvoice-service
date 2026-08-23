# Mock Auth for MedVoice Login — Design

Date: 2026-08-23
Status: Approved (unattended execution authorized)
Scope: medvoice-service (backend) + medvoice-mobile (Flutter app)

## 1. Context & Goals

The mobile app has a Login screen (`lib/app/pages/onboarding/login/sign_in_view.dart`)
that validates input and navigates without any API call. The backend has no user
concept at all. The 2026-08-16 mobile-api-contract spec explicitly **reserved
`/auth/*` endpoints** for future work ("No auth in v1, but feature-flag hook
reserved for future user management").

Goal: let the user log into the MedVoice app with seeded mock accounts against a
real `POST /auth/login`, then run the full pipeline E2E with LM Studio models.

Decisions locked with the user (2026-08-23):
- Backend-backed mock accounts (SQLite users table + `/auth/login`), not client-side hardcoding.
- The mobile login screen is wired to call the endpoint; 401 shows an error, success navigates to Main.
- Full E2E including sg-1.WAV upload through transcript/SOAP/ICD-10/PHI via LM Studio.
- **`ENABLE_AUTHENTICATION` stays false**: login is additive; existing endpoints stay open so nothing breaks. Protecting endpoints behind tokens is a future step, out of scope.
- Mock accounts only — no signup/reset flows wired in this iteration (screens exist in-app but keep current behavior).

## 2. API Contract

### POST /auth/login
Request `application/json`:
```json
{ "email": "doctor@medvoice.local", "password": "MedVoice2026!" }
```

200 OK:
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": { "id": 1, "email": "doctor@medvoice.local", "full_name": "Dr. Demo", "role": "physician" }
}
```

401 (wrong email OR wrong password — same response, no user enumeration):
```json
{ "detail": "Invalid email or password", "error_code": "invalid_credentials" }
```

422: malformed body per FastAPI default validation envelope.

JWT: HS256, `sub` = user id, `exp` = now + 30 min (`Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES`).
Secret: `Config.JWT_SECRET_KEY` env var; if unset, a random secret is generated at startup
(dev-only convenience; a warning is logged). Passwords hashed with passlib bcrypt.

### Seeded mock accounts (created at API startup if users table empty)
| email | password | full_name | role |
|---|---|---|---|
| doctor@medvoice.local | MedVoice2026! | Dr. Demo | physician |
| nurse@medvoice.local | MedVoice2026! | Nurse Demo | nurse |
| admin@medvoice.local | Admin2026! | Admin Demo | admin |

## 3. Backend Implementation (medvoice-service)

### New file: app/services/user_store.py
- Own SQLite DB at `data/users.db` (path from `Config.USERS_DB_PATH`, yaml-configurable,
  default `./data/users.db`). Separate file from patient_mappings.db so `DB_FRESH_START`
  / init_database(fresh_start=True) can never wipe accounts.
- Table:
```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'physician',
    created_at TEXT NOT NULL
);
```
- Functions: `init_user_store()`, `get_user_by_email(email) -> Optional[dict]`,
  `create_user(email, password_hash, full_name, role) -> int`,
  `count_users() -> int`.
- Module-level `MOCK_USERS` constant holding the three seed accounts above.

### New file: app/routers/auth.py
- `POST /auth/login`: pydantic models `LoginRequest(email, password)` /
  `LoginResponse(access_token, token_type, user)`; `UserPublic(id, email, full_name, role)`.
- Lookup by lowercase email → bcrypt verify → issue token via python-jose.
- 401 uses the repo's error envelope pattern (`RecordingError` style: HTTPException subclass
  carrying `error_code="invalid_credentials"`).
- Startup seeding: `lifespan`/startup hook in `app/main.py` calls `init_user_store()` and
  seeds the three accounts when the table is empty (idempotent).

### Wiring & config
- `app/main.py`: `app.include_router(auth.router)`.
- `app/config.py`: add `USERS_DB_PATH = _get_yaml("database", "users_db_path", "./data/users.db")`.
- `config.yaml`: add `users_db_path: ./data/users.db` under `database:` (optional; default covers it).
- No new dependencies (passlib[bcrypt] and python-jose[cryptography] already in pyproject).
- `.env`: `LM_STUDIO_MODEL=bio-medical-llama-3-8b` (matches currently loaded model).

## 4. Mobile Implementation (medvoice-mobile)

Follows the existing clean-arch layering used by recordings:

### New files
- `lib/domain/entities/auth/auth_user.dart` — `AuthUser` + `AuthResult` (token + user), `fromJson`.
- `lib/domain/repositories/auth_repository/auth_repository.dart` — abstract `login(String email, String password)`.
- `lib/data/repository_impl/auth_repository_impl.dart` — POST JSON to `Constants.authLogin`,
  200 → `AuthResult.fromJson`; 401 → throw typed `AuthException('invalid_credentials')`;
  other statuses/network errors → `AuthException('network_error')`. Injectable `http.Client`
  constructor mirroring `AudioRepositoryImpl.withClient`.

### Modified files
- `lib/data/network/constants.dart` — add `static String get authLogin => "${baseUrl}auth/login";`.
- `lib/app/pages/onboarding/login/sign_in_controller.dart` — `submitForm()` becomes async:
  sets `isLoading=true`, calls `AuthRepositoryImpl().login(...)`, on success pushes Main,
  on `AuthException` surfaces message. Exposes `isLoading` state for the button.
- `lib/app/pages/onboarding/login/sign_in_view.dart` — disable button + progress indicator while loading;
  SnackBar on failure ("Invalid email or password." / "Cannot reach server.").

### Tests (medvoice-mobile/test/)
`auth_repository_test.dart` with MockClient: success parses token+user; 401 throws invalid_credentials;
500/timeout throws network_error. Controller-level widget test optional if cheap.

## 5. Testing & E2E plan (executed by Hermes, not omp)
1. Backend unit/integration pytest green (`tests/` suite incl. new auth tests).
2. `docker compose up -d --build` → readiness loop → curl login: 3 accounts 200, wrong pw 401.
3. Pipeline E2E: `POST /recordings` with `datasets/audios/sg/sg-1.WAV` → transcript +
   SOAP subjective/objective/assessment/plan non-empty + ICD-10 entities + PHI section present.
4. Flutter: unit tests + `recordings_api_integration_test.dart --run-skipped` vs live backend.
5. UI E2E on iOS simulator (Chrome fallback): drive login screen with mock creds, verify Main loads.

## 6. Out of scope
- Protecting `/recordings` etc. behind bearer tokens (ENABLE_AUTHENTICATION stays false).
- Signup/password-reset wiring, refresh tokens, logout persistence.
- Multi-user scoping of recordings (user_id column) — reserved as in original spec.
