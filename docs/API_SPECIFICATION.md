# IP-SAKTI Sahayak — API

The live, authoritative specification is the OpenAPI schema. It includes request and response models and examples:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Conventions

- **Auth:**
  - `POST /api/auth/login` returns a token and also sets an httpOnly cookie.
  - API clients send `Authorization: Bearer <token>`.
  - Cookie-authenticated writes must send `X-Requested-With: ipsakti`.
- **Workspace:** select one with the `X-Workspace-Id` header. The default is the user's first workspace.
- **Responses:**
  - success: `{"success": true, "data": …, "meta": {…}}`
  - error: `{"success": false, "error": {"code", "message"}}`
  - Stack traces are never returned.
- **Rate limits:** per user per minute on chat, search, ingest and reports.

## Endpoint groups (73 paths)

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `/auth/login`, `/auth/logout`; `GET /auth/me`, `/auth/session` |
| Workspaces | `GET/POST /workspaces`; `GET/PATCH /workspaces/{id}`; `POST /workspaces/{id}/members` |
| Innovations | `GET/POST /innovations`; `GET/PATCH/DELETE /innovations/{id}`; `POST …/profile/generate`; `PATCH …/profile`; `POST …/analyze`; `GET …/summary`, `…/provisions`, `…/evidence` (+`POST`), `…/scientific`, `…/tk`, `…/patents` (+`PATCH …/patents/matches/{id}`), `…/evidence-gaps` (+`PATCH`), `…/risk-map`, `…/graph`, `…/classification` (+`POST`), `…/regulatory` |
| Research | `POST /chat`; `GET /conversations`, `/conversations/{id}`, `/conversations/{id}/messages`; `DELETE /conversations/{id}`; `PATCH /messages/{id}` |
| Search & verification | `POST /search`, `/search/patents`, `/search/scientific`, `/search/regulatory`, `/citations/verify`, `/classification/analyze`; `GET /classification/questions`, `/regulatory/{IN\|US\|AU}` |
| Review | `POST/GET /escalations`; `GET/PATCH /escalations/{id}`; `POST/GET /reports`; `GET /reports/{id}`, `/reports/{id}/markdown`; `POST/GET /feedback`; `PATCH /feedback/{id}`; `GET /audit` |
| Corpus | `GET/POST /sources`; `PATCH /sources/{id}`; `GET/POST /documents`; `GET /documents/{id}`; `PATCH /documents/{id}/review`; `POST /documents/ingest`; `GET /ingestion-jobs`, `/ingestion-jobs/{id}`, `/uploads/notice`, `/coverage`, `/privacy` |
| Admin | `GET /dashboard`, `/admin/overview`, `/admin/users` (+`PATCH`), `/admin/workspaces`, `/admin/update-queue`, `/metrics`; `POST /admin/retention/run` |
| Evaluation | `GET /evaluations`; `POST /evaluations/run` |
| Health | `GET /health`, `/health/database`, `/health/vector`, `/health/llm` |
