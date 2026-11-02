# Pension Agents Demo

AI chat workflows (LangChain + LangGraph) behind a REST API and an MCP server, with a React frontend.
A deliberately small application built the way a production system should be: layered, typed, tested,
secured, and with quality gates that are enforced rather than intended.

This is a demo: the pension fund, its members and its policies are fictional. How and why it was built
this way is described (in Dutch) in [docs/ai-agents-architectuur.md](docs/ai-agents-architectuur.md).

```
 Browser ──► frontend (React, nginx) ──► /api ──┐                        ┌─► PostgreSQL + pgvector
                                                 ├─► backend (FastAPI) ──┤
 AI client (Claude, IDE) ──────────► /mcp ──────┘                        └─► MLflow (traces, evals)
```

Three workflows: a tool-calling **weather agent**, a **support-email workflow** (parallel steps, a reviewer
loop, human approval) and a **policy assistant** that answers from the fund's documents with sources (RAG).

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
| http://localhost:5000 | MLflow: a trace of every chat turn, and evaluation runs (only reachable from this machine) |

Without `ANTHROPIC_API_KEY` the app still starts, and every chat answers that no AI model is configured.
To try the workflows without a key, add the e2e override: `docker compose -f docker-compose.yml -f docker-compose.e2e.yml up --build`.
It injects a scripted model from `backend/tests/fakes`; the production image contains no test code.

**Local development:** `docker compose up db` for Postgres, then `uv run uvicorn app.main:create_app --factory --reload`
in `backend/` (with a `backend/.env` holding `DATABASE_URL`, `JWT_SECRET`, `DEMO_PASSWORD`, `ANTHROPIC_API_KEY`) and `npm run dev` in `frontend/`.

## Architecture

### Backend: layers with one-way dependencies

```
app/main.py  app/cli.py   composition root (dependency injection in one place) | operator commands
app/api/  app/mcp/        thin transport layers: HTTP/MCP concerns only, no business logic
app/services/             use cases + authorization (chat, auth) - shared by REST and MCP
app/workflows/  app/db/   ChatWorkflow implementations (LangGraph) | repositories, pgvector, migrations
app/rag/                  KnowledgeBase interface, document chunking, embeddings
app/domain/  app/config.py  app/observability.py   models and errors | settings | MLflow tracing
```

- **One interface for all agents.** Every workflow implements `ChatWorkflow.stream(thread_id, message)`
  (`workflows/base.py`). Services and transports only know that interface, so workflows are swappable and
  testable in isolation (the tests swap in non-LangGraph implementations).
- **One set of models.** Pydantic models in `domain/models.py` are used by every layer. The OpenAPI spec is
  generated from them and the frontend's TypeScript types are generated from that spec
  (`npm run gen:api`), so backend and frontend cannot drift apart. CI fails if they do.
- **Authorization in the service layer**, not in the transports: REST and MCP can't diverge, and a user can
  only reach their own conversations.
- **Dependency injection in one place.** `build_container` in `main.py` wires everything; the chat model is
  a parameter, so tests and the e2e stack inject a scripted model without any test code in `app/`.
- **Durable workflows.** LangGraph state lives in Postgres (checkpointer), so a workflow paused for human
  approval survives restarts and deploys.

### RAG: the policy assistant

```
knowledge/*.md ──► chunk per section ──► embed (local model) ──► pgvector ◄── search ◄── question
                                                                                 │
                                       answer with [1] citations ◄── Claude ◄── top passages
```

- **Knowledge** lives in `backend/knowledge/` as Markdown (fictional policies). `python -m app.cli ingest`
  (run at container start) chunks them per section and embeds only new or changed chunks (content hash).
- **Embeddings run locally** (`paraphrase-multilingual-MiniLM-L12-v2` via fastembed, baked into the image):
  no extra API key, and member questions never leave our infrastructure. Dutch questions find English documents.
- **pgvector in the existing Postgres**: no extra service, same backups and access control, schema via Alembic.
- **Grounded or nothing.** The model may only use the retrieved passages and must cite them. When nothing
  scores above the relevance threshold, the assistant says so *without* calling the model.
- Workflows depend on the `KnowledgeBase` interface (`app/rag/base.py`), not on pgvector: tests use an
  in-memory implementation, and the support workflow uses the same retrieval for its policy lookup.

### MLflow: tracing and evaluation

- **Tracing.** `mlflow.langchain.autolog()` turns every chat turn into one trace: the LangGraph run, each node,
  every model and tool call, and our own retrieval step (a RETRIEVER span with the passages and scores).
  Traces are grouped per conversation (session). Set `MLFLOW_TRACKING_URI` to turn it on.
- **Evaluation.** `uv run python -m evals.rag_eval` asks 22 member questions (English and Dutch, plus
  off-topic ones), measures hit rate, MRR and how many off-topic questions are declined, and logs every run
  to MLflow, so model or chunking changes can be compared side by side. CI fails below 0.85.
  Current result: hit rate 1.00, MRR 0.96, off-topic declined 1.00.
- **Privacy.** Traces contain prompts, and therefore member data. The MLflow server is bound to localhost
  and must stay internal (in production: behind authentication, with a retention policy).

### Frontend

React + TypeScript (strict), Vite. Components receive the `ChatApi` interface (`src/api/client.ts`), so
tests inject a fake backend. Messages stream live over server-sent events and are rendered as GitHub-flavoured
Markdown (tables included), never as raw HTML.

## Quality gates

Lint, type and architecture rules run at three moments; tests, coverage and evaluations run in CI.
Only CI with branch protection is a guarantee; the earlier moments give faster feedback.

| Gate | Backend | Frontend |
|---|---|---|
| Complexity | ruff: cyclomatic complexity <= 8, <= 5 arguments, <= 8 branches, <= 30 statements, <= 4 returns | eslint: complexity <= 8, <= 4 params, depth <= 3, <= 60 lines per function |
| Coupling / architecture | import-linter: layer contracts; transports may not import db/workflows | components depend on the `ChatApi` interface |
| Documentation | ruff `D` rules: every module, class and function has a docstring (Google style) | a doc comment per module (convention, not lint-enforced) |
| Types | mypy `--strict` | tsc `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` |
| Security | ruff `S` (bandit) rules, pip-audit | eslint strict-type-checked, npm audit |
| Tests + coverage | pytest, coverage >= 80% (currently 98%) | vitest, coverage >= 80% (currently 96%) |
| AI quality | RAG evaluation: hit rate, MRR, off-topic declined >= 0.85 | - |

| When | How |
|---|---|
| While AI writes code | Claude Code hook (`.claude/settings.json`) lints every edited file; violations go back to the AI to fix |
| On commit | pre-commit (`.pre-commit-config.yaml`): lint, format, types and layer rules for backend and frontend, plus secret scanning (gitleaks) |
| On every pull request | GitHub Actions (`.github/workflows/ci.yml`): all of the above + integration, RAG evaluation and e2e tests |

## Tests

| Level | What | Run |
|---|---|---|
| Unit | services, workflows (with the scripted model from `tests/fakes`), REST and MCP layers (SQLite in memory) | `uv run pytest` (backend), `npm test` (frontend) |
| Integration | real Postgres + pgvector via Testcontainers: migrations up/down, a paused approval survives an app restart, ingestion is idempotent, a Dutch question finds the English document | included in `uv run pytest` (needs Docker) |
| RAG evaluation | retrieval quality with the real embedding model, logged to MLflow | `uv run python -m evals.rag_eval` |
| E2E (API) | full stack through nginx: chat flow, MCP, auth | `uv run pytest -m e2e` (stack started with `docker-compose.e2e.yml`, `E2E_PASSWORD` set) |
| E2E (browser) | Playwright clicks through the UI: login, draft, approve, reload, complaint, policy assistant with sources, logout | `npx playwright test` in `frontend/` (same stack) |

## Security by design

- Every API and MCP call requires a bearer token (JWT: signature, expiry, audience, issuer and scope checked).
  Authentication sits behind `AuthService`, so an identity provider (Entra ID, Cognito) can replace local login.
- Authorization in the service layer; unknown and foreign conversations both return 404 (no information leak).
- Secrets only from the environment; no defaults for secrets; startup fails on short secrets.
  The scripted test model lives in `tests/` only and is never part of the production image.
- Passwords hashed with bcrypt; login takes the same time for unknown users (no username probing).
- Workflow errors are logged with a reference id; users never see internals.
- Human-in-the-loop: the AI never sends a reply without approval; complaints are never answered by AI.
- LLM output is rendered as Markdown without raw HTML (no XSS); strict Content-Security-Policy and security headers.
- MCP: DNS-rebinding protection (allowed hosts), same token validation as the API.
- All containers run as non-root (the frontend uses unprivileged nginx); request IDs on every request for traceability.
