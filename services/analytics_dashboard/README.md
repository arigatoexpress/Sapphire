# sapphire-analytics

Cloud Run service backing `https://sapphirealpha.xyz`. Reads BigQuery,
serves the unified dashboard, and gates a small set of admin pages
behind a WebAuthn passkey.

## Layout

```
services/analytics_dashboard/
├── app.py            Flask app + /api/* JSON endpoints + probe sink
├── auth/             WebAuthn passkey scaffold (this section)
│   ├── routes.py     /api/admin/* + /admin/* blueprint
│   ├── session.py    SessionManager (signed cookie + challenge handles)
│   ├── decorator.py  @requires_admin
│   └── store.py      Firestore + in-memory credential stores
├── templates/
│   ├── index.html
│   ├── admin_login.html
│   └── admin.html
├── requirements.txt
└── Dockerfile
```

## WebAuthn passkey admin scaffold

The dashboard exposes admin pages at `/admin` and `/admin/login`. They are
gated by a single passkey — no passwords. The scaffold is reusable: drop
the `auth/` package into another Flask service and call
`auth.register_blueprint(app)` to get the same flow.

### How it works

```
            /admin/login (HTML)
                  │
        register ─┴─ sign-in
            │           │
   navigator.          navigator.
   credentials.        credentials.
   create()            get()
            │           │
   POST /api/admin/    POST /api/admin/
   register/begin      login/begin
            │           │      → returns { options, handle }   (handle = signed challenge)
            ▼           ▼
   POST /api/admin/    POST /api/admin/
   register/complete   login/complete   → verifies attestation/assertion,
                                          stores or updates the credential,
                                          mints `sapphire_admin` cookie (4h TTL).
            │           │
            └────┬──────┘
                 ▼
              /admin  (gated by @requires_admin)
```

- **Challenges** are 32-byte `secrets.token_bytes(32)` nonces. They are
  *not* sent to the client raw — they're wrapped in a `URLSafeTimedSerializer`
  handle (5-min TTL, salted with the flow tag) so a `register` challenge
  can never be replayed against `/login/complete`.
- **Session cookie** is `sapphire_admin`, HttpOnly, SameSite=Lax,
  `Secure` in prod (RP_ID != localhost), 4-hour TTL.
- **Single-user lockout**: once any credential exists for `user_id="admin"`,
  `/api/admin/register/begin` requires a valid session. This prevents an
  attacker from registering their own passkey before the operator does.
- **Storage**: Firestore collection `admin_credentials` in project
  `tho-ai-agent`, document id = base64url(credential_id). Schema:
  `{credential_id, public_key, sign_count, user_id, aaguid, created_at,
  last_used_at}`. Falls back to an in-memory store when the Firestore SDK
  or ADC are unavailable (dev / CI).

### Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET`  | `/admin/login` | public | Login + register UI |
| `GET`  | `/admin` | session | Operator landing page |
| `GET`  | `/api/admin/status` | public/session | Public: `{mode, registered}`. Session: adds `{rp_id, credentials}` |
| `POST` | `/api/admin/register/begin` | gated* | Returns options + handle |
| `POST` | `/api/admin/register/complete` | public | Verifies attestation, stores credential, mints session |
| `POST` | `/api/admin/login/begin` | public | Returns options + handle (404 if no creds) |
| `POST` | `/api/admin/login/complete` | public | Verifies assertion, mints session |
| `POST` | `/api/admin/logout` | public | Clears the session cookie |
| `GET`  | `/api/admin/whoami` | session | `{user_id, issued_at}` |

\* `register/begin` is unauthenticated only when zero credentials exist.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RP_ID` | `localhost` | WebAuthn relying-party id. Set to `sapphirealpha.xyz` in prod. |
| `RP_NAME` | `Sapphire Alpha Admin` | Shown in authenticator UI. |
| `ADMIN_SESSION_SECRET` | (random per-process) | **Required in prod.** itsdangerous secret for the cookie + challenge handles. Rotate to invalidate every session. |
| `ADMIN_EXPECTED_ORIGIN` | derived from `RP_ID` | Override the `expected_origin` passed to `verify_*_response`. Comma-separate to allow multiple. |
| `GCP_PROJECT` | `tho-ai-agent` | Firestore project for `admin_credentials`. |
| `PORT` | `8080` | Used to derive the localhost dev origin. |

### Cloud Run permissions

The service account running `sapphire-analytics` needs:

- `roles/datastore.user` on project `tho-ai-agent` (or a tighter custom
  role with `datastore.entities.{create,get,update,list}` on collection
  group `admin_credentials`).
- The existing `roles/bigquery.dataViewer` for the dashboard.

Without Firestore access the auth module logs a warning and falls back
to in-memory storage; admin sessions still work but credentials are lost
on each container restart.

### Registering your first passkey

**Browser (recommended):**

1. `https://sapphirealpha.xyz/admin/login`
2. Click *Register a new passkey*.
3. Pick your authenticator (Proton Pass, iCloud Keychain, hardware key,
   1Password browser extension, etc.).
4. You're auto-signed in; redirects to `/admin`.

**curl (smoke test only — passkey registration requires a real authenticator):**

```bash
# Begin
curl -sS -X POST https://sapphirealpha.xyz/api/admin/register/begin \
  -H 'content-type: application/json' \
  -c cookies.txt -b cookies.txt | jq .

# This returns {options, handle}. The browser would now call
# navigator.credentials.create(options) and POST the resulting
# attestation back to /api/admin/register/complete with the handle.
# There is no curl-only happy path — the attestation is produced by
# the authenticator hardware.
```

### Local development

```bash
cd services/analytics_dashboard
pip install -r requirements.txt
ADMIN_SESSION_SECRET=dev RP_ID=localhost PORT=8080 python3 app.py
```

Visit `http://localhost:8080/admin/login`. Browsers allow WebAuthn on
plain `http://localhost`; any other host must be HTTPS.

### Tests

```bash
pytest tests/unit/test_analytics_admin_auth.py -v
```

34 unit tests cover SessionManager (sign/verify/expiry/flow-tag), the
in-memory credential store, the `@requires_admin` decorator (401 JSON,
302 HTML, 503 missing config, allow valid), and the full
register/login/logout HTTP surface with `webauthn.verify_*_response`
mocked. The Firestore backend is exercised by passing it as a custom
store, so no GCP creds are needed in CI.
