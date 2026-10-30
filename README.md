# Agent Chat

AI chat workflows (LangChain + LangGraph) behind a REST API and an MCP server, with a React frontend.
A deliberately small application built the way a production system should be: layered, typed, tested,
secured, and with quality gates that are enforced rather than intended.

```
 Browser ──► frontend (React, nginx) ──► /api ──┐
                                                 ├─► backend (FastAPI) ──► PostgreSQL
 AI client (Claude, IDE) ──────────► /mcp ──────┘
```

## Run it

```powershell
copy .env.example .env          # fill in the secrets (see comments in the file)
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:8080 | Chat UI (log in as `demo` with `DEMO_PASSWORD`) |
| http://localhost:8000/docs · `/redoc` | API documentation (OpenAPI: Swagger UI and ReDoc) |
| http://localhost:8000/mcp | MCP endpoint (same bearer token as the API) |

Set `LLM_PROVIDER=fake` to run without an Anthropic key (a scripted model; refused in production).

**Local development:** `docker compose up db` for Postgres, then `uv run uvicorn app.main:create_app --factory --reload`
in `backend/` (with a `backend/.env` holding `DATABASE_URL`, `JWT_SECRET`, `DEMO_PASSWORD`) and `npm run dev` in `frontend/`.

## Architecture

### Backend: layers with one-way dependencies

```
app/main.py           composition root: wires everything (dependency injection in one place)
app/api/  app/mcp/    thin transport layers: HTTP/MCP concerns only, no business logic
app/services/         use cases + authorization (chat, auth) - shared by REST and MCP
app/workflows/  app/db/   ChatWorkflow implementations (LangGraph) | repositories + migrations
app/domain/  app/config.py   Pydantic models and errors | settings
```

- **One interface for all agents.** Every workflow implements `ChatWorkflow.stream(thread_id, message)`
  (`workflows/base.py`). Services and transports only know that interface, so workflows are swappable and
  testable in isolation (the tests swap in non-LangGraph implementations).
- **One set of models.** Pydantic models in `domain/models.py` are used by every layer. The OpenAPI spec is
  generated from them and the frontend's TypeScript types are generated from that spec
  (`npm run gen:api`), so backend and frontend cannot drift apart. CI fails if they do.
- **Authorization in the service layer**, not in the transports: REST and MCP can't diverge, and a user can
  only reach their own conversations.
- **Durable workflows.** LangGraph state lives in Postgres (checkpointer), so a workflow paused for human
  approval survives restarts and deploys.

### Frontend

React + TypeScript (strict), Vite. Components receive the `ChatApi` interface (`src/api/client.ts`), so
tests inject a fake backend. Messages stream live over server-sent events.

## Quality gates

The same rules run at three moments. Only CI with branch protection is a guarantee; the others give
faster feedback.

| Gate | Backend | Frontend |
|---|---|---|
| Complexity | ruff: cyclomatic complexity <= 8, <= 5 arguments, <= 8 branches, <= 30 statements, <= 4 returns | eslint: complexity <= 8, <= 4 params, depth <= 3, <= 60 lines per function |
| Coupling / architecture | import-linter: layer contracts; transports may not import db/workflows | components depend on the `ChatApi` interface |
| Documentation | ruff `D` rules: every module, class and function has a docstring (Google style) | a doc comment per module (convention, not lint-enforced) |
| Types | mypy `--strict` | tsc `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` |
| Security | ruff `S` (bandit) rules, pip-audit | eslint strict-type-checked, npm audit |
| Tests + coverage | pytest, coverage >= 80% (currently 99%) | vitest, coverage >= 80% (currently 96%) |

| When | How |
|---|---|
| While AI writes code | Claude Code hook (`.claude/settings.json`) lints every edited file; violations go back to the AI to fix |
| On commit | pre-commit (`.pre-commit-config.yaml`), plus secret scanning (gitleaks) |
| On every pull request | GitHub Actions (`.github/workflows/ci.yml`): all of the above + integration and e2e tests |

## Tests

| Level | What | Run |
|---|---|---|
| Unit | services, workflows (with a fake LLM), REST and MCP layers (SQLite in memory) | `uv run pytest` (backend), `npm test` (frontend) |
| Integration | real Postgres via Testcontainers: migrations up/down, a paused approval survives an app restart | included in `uv run pytest` (needs Docker) |
| E2E (API) | full stack through nginx: chat flow, MCP, auth | `uv run pytest -m e2e` (stack running, `E2E_PASSWORD` set) |
| E2E (browser) | Playwright clicks through the UI: login, draft, approve, reload, complaint, logout | `npx playwright test` in `frontend/` |

## Security by design

- Every API and MCP call requires a bearer token (JWT: signature, expiry, audience, issuer and scope checked).
  Authentication sits behind `AuthService`, so an identity provider (Entra ID, Cognito) can replace local login.
- Authorization in the service layer; unknown and foreign conversations both return 404 (no information leak).
- Secrets only from the environment; no defaults for secrets; startup fails on short secrets.
  The fake model is refused in production.
- Passwords hashed with bcrypt; login takes the same time for unknown users (no username probing).
- Workflow errors are logged with a reference id; users never see internals.
- Human-in-the-loop: the AI never sends a reply without approval; complaints are never answered by AI.
- LLM output is rendered as Markdown without raw HTML (no XSS); strict Content-Security-Policy and security headers.
- MCP: DNS-rebinding protection (allowed hosts), same token validation as the API.
- Containers run as non-root; request IDs on every request for traceability.
