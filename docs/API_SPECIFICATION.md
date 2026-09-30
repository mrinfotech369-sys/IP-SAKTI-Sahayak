# IP-SAKTI Sahayak — API

The live, authoritative specification is the OpenAPI schema. It includes request and response models and examples:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Conventions

- **Two separate sessions, two separate logins:**
  - **App (user) session:** `POST /api/auth/login` returns a token and sets an httpOnly `ipsakti_session` cookie, scoped `"user"`. Used for every `/api/*` route below except `/api/admin/*`.
  - **Admin console session:** `POST /api/auth/admin/login` (role must be `ADMIN`) returns a token and sets a separate httpOnly, `SameSite=Strict` `ipsakti_admin` cookie, scoped `"admin"`. Required for every `/api/admin/*` route — an app session, even for an ADMIN-role account, is never accepted there (server-side, on every request, not just at login). Conversely an admin-scoped token is never accepted on app routes.
  - API clients send `Authorization: Bearer <token>` (the app or admin token, matching the route). Browser clients rely on the matching cookie.
  - Cookie-authenticated writes must send `X-Requested-With: ipsakti`.
  - `GET /api/auth/session` and `GET /api/auth/admin/session` never 401 — they report `null`/`{"state": "signed_out"}` etc. so the frontend can render the right screen.
- **Workspace:** select one with the `X-Workspace-Id` header. The default is the user's first workspace. Not used by `/api/admin/*` routes, which are workspace-agnostic.
- **Responses:**
  - success: `{"success": true, "data": …, "meta": {…}}`
  - error: `{"success": false, "error": {"code", "message"}}`
  - Stack traces are never returned.
- **Rate limits:** per user per minute on chat, search, ingest, reports and login attempts.

## Endpoint groups (91 paths)

| Group | Endpoints |
|---|---|
| Auth (app) | `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/change-password`; `GET /auth/me`, `/auth/session`; `PATCH /auth/me` |
| Auth (admin console) | `POST /auth/admin/login`, `/auth/admin/logout`; `GET /auth/admin/session` |
| Workspaces | `GET/POST /workspaces`; `GET/PATCH /workspaces/{id}`; `POST /workspaces/{id}/members` |
| Innovations | `GET/POST /innovations`; `GET/PATCH/DELETE /innovations/{id}`; `POST …/profile/generate`; `PATCH …/profile`; `POST …/analyze`; `GET …/summary`, `…/provisions`, `…/evidence` (+`POST`), `…/scientific`, `…/tk`, `…/patents` (+`PATCH …/patents/matches/{id}`), `…/evidence-gaps` (+`PATCH`), `…/risk-map`, `…/graph`, `…/classification` (+`POST`), `…/regulatory` |
| Research | `POST /chat`; `GET /conversations`, `/conversations/{id}`, `/conversations/{id}/messages`; `DELETE /conversations/{id}`; `PATCH /messages/{id}` |
| Search & verification | `POST /search`, `/search/patents`, `/search/scientific`, `/search/regulatory`, `/citations/verify`, `/classification/analyze`; `GET /classification/questions`, `/regulatory/{IN\|US\|AU}` |
| Review (own workspace) | `POST/GET /escalations`; `GET/PATCH /escalations/{id}`; `POST/GET /reports`; `GET /reports/{id}`, `/reports/{id}/markdown`; `POST/GET /feedback`; `PATCH /feedback/{id}`; `GET /audit` |
| Corpus (read + own uploads) | `GET /sources`; `GET/POST /documents`; `GET /documents/{id}`; `GET /ingestion-jobs`, `/ingestion-jobs/{id}`, `/uploads/notice`, `/coverage`, `/privacy` |
| Dashboard | `GET /dashboard` — the caller's own workspace only; not to be confused with the admin console's system-wide dashboard below |
| Health | `GET /health`, `/health/database`, `/health/vector`, `/health/llm` |
| **Admin console** (`/admin/*`, requires the admin session above) | `GET /admin/overview`, `/admin/metrics`, `/admin/settings`; `POST /admin/retention/run`; `GET/PATCH /admin/users`, `/admin/users/{id}`; `GET /admin/workspaces`; `GET/POST /admin/sources`, `PATCH /admin/sources/{id}`; `GET /admin/documents`, `/admin/documents/{id}`; `POST /admin/documents/ingest`, `/admin/documents/{id}/reindex`; `PATCH /admin/documents/{id}/review`; `GET /admin/ingestion-jobs`, `/admin/update-queue`; `GET /admin/rag`, `/admin/citations` (retrieval & citation monitoring); `GET/POST /admin/escalations`, `GET/PATCH /admin/escalations/{id}`; `GET/PATCH /admin/feedback`, `/admin/feedback/{id}`; `GET /admin/audit-logs`, `/admin/audit-logs/export` (CSV); `GET /admin/evaluations`, `POST /admin/evaluations/run` |
