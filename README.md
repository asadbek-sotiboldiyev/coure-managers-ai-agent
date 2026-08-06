# Manager Agent — Full Project Documentation

Last updated: 2026-08-05T20:16:00+05:00

This document describes the repository structure, how the system works end-to-end, the roles of each folder and file, and the responsibilities of important functions. It is written in English and attempts to include implementation-level details where practical. The real .env is intentionally not read; reference values come from `.env.example`.

---

## High-level overview

Manager Agent is an automated pipeline that:
- analyzes student progress from the PostgreSQL business DB (accounts_app),
- collects and scrubs Telegram private chat histories for problematic students (chat_history_app),
- runs an LLM-based analysis (LangChain + Google Gemini) to assess assistant-student interaction quality (ai_agent_app),
- stores structured results in a local SQLite file (ai_reports) and tracking tables (shared/local_db.py),
- exposes a web UI and API (main_app) including a streaming NDJSON endpoint for real-time frontend updates.

The code is split into four main logical modules (see README): `accounts_app`, `chat_history_app`, `ai_agent_app`, and `main_app`. Shared utilities live in `shared/`. A small `scripts/` folder contains interactive login helpers. `frontend/` contains static UI templates and JS for the dashboard.

## Databases

- Primary business data (Groups, Students, Users, etc.) is stored in PostgreSQL. Access is centralized via `shared/db.py`.
- Local SQLite (path configured by `LOCAL_SQLITE_PATH`, default `local_data.sqlite3`) stores runtime artifacts: `chats_last_check`, `ai_reports`, and `assistant_tg_info` (sessions metadata). Code to create and use these tables is in `shared/local_db.py`.

Design note: local SQLite is used to avoid writing analysis results into primary DB and to allow pipeline to run offline for fast tests.

## How the pipeline works (end-to-end)

1. `accounts_app` fetches group progress snapshots from PostgreSQL. Each group's students have a simple `hw_count` metric.
2. `accounts_app.progress_analyzer` calls a structured LLM schema (LangChain `with_structured_output`) to label each student `has_problem` + `problem` (Uzbek sentence). Problems are collated.
3. Problematic students are resolved to assistant/student pairs using `accounts_app.repository` and `shared/local_db` assistant session info.
4. For each assistant (session), `chat_history_app.fetcher` opens Pyrogram client using the session file and retrieves chat histories for relevant students, scrubbing names using `chat_history_app.scrubber`.
5. `ai_agent_app.analyzer` turns scrubbed chats into prompts and calls `langchain_google_genai` (Gemini) with a structured Pydantic schema (`ai_agent_app/schema.py`) to obtain `InteractionAnalysis`.
6. `ai_agent_app.reports_repository` saves structured `InteractionReport` rows into local SQLite `ai_reports`.
7. `main_app.orchestrator` wires the above into a streaming generator (`run_full_pipeline_stream`) used by the API streaming endpoint `/api/check_groups` (NDJSON). The same logic can be invoked in blocking mode via `/api/run` (non-streaming variant exists as `POST /run` in API docs).

Fault isolation: every IO/LLM call is guarded. Failures for one student or one report do not stop the whole pipeline; errors are surfaced in stream events (`state: "error"`) but pipeline continues.

---

## Top-level files and purpose

- `README.md` — human overview (Uzbek/English) and run instructions.
- `.env.example` — required environment keys (DB credentials, Telegram API config, AI config, app settings).
- `requirements.txt` — pip dependencies (fastapi, pyrogram, langchain-google-genai, psycopg2-binary, python-dotenv, etc.).
- `run.bat`, `install.bat` — convenience Windows scripts.
- `API_STREAMING.md` — detailed streaming API contract (NDJSON states & examples).
- `local_data.sqlite3` — generated runtime SQLite (committed here in this copy but generally created/updated at runtime).
- `logs/app.log` — runtime log file created by shared/logger.py.

---

## Folder-by-folder, file-by-file description

Note: only key files are shown with short but detailed descriptions and important functions / classes.

### shared/
Purpose: common configuration, DB helpers, local DB management, models/DTOs, and logger.

Files:
- `config.py`
  - Reads environment variables via python-dotenv.
  - Constants & dataclasses: `DBConfig`, `LocalDBConfig`, `TelegramConfig`, `AIConfig`, `AppConfig`.
  - Exposes `db_config`, `local_db_config`, `tg_config`, `ai_config`, `app_config`.
  - Ensures `sessions` directory exists for Pyrogram sessions.

- `db.py`
  - Provides `get_connection()` context manager returning a psycopg2 connection with `NamedTupleCursor`.
  - Handles rollback on errors and logs errors.

- `local_db.py`
  - Manages local SQLite DB: ensures tables and provides CRUD helper functions.
  - Table creation helpers: `ensure_tracking_table_exists()`, `ensure_ai_reports_table_exists()`, `ensure_assistant_tg_info_table_exists()`, etc.
  - Functions to upsert and read assistant/session info: `upsert_assistant_tg_info`, `get_assistant_tg_info`, `get_active_assistant_tg_infos`.
  - Helpers for logging/issue tables and categorization heuristics (e.g., `categorize_issue`) used when saving issue logs.
  - Reports & tracking write helpers: `insert_group_check_log`, `insert_student_issues`, `save_reports` uses by ai_agent_app.

- `logger.py`
  - Single `get_logger(name)` function sets up console + file handlers and uses `LOG_DIR = logs`.

- `models.py`
  - Dataclasses and Pydantic request schemas for data transfer across modules.
  - Key DTOs: `AssistantInfo`, `StudentInfo`, `AssistantWithStudents`, `ChatMessage`, `ScrubbedChatHistory` (with `to_prompt_text()`), `InteractionReport`, plus progress snapshot DTOs.

### main_app/
Purpose: web API, template UI endpoints, and the orchestrator that runs the pipeline.

Files:
- `server.py`
  - FastAPI app factory with `lifespan` ensuring local SQLite tables exist on startup.
  - Mounts `frontend` static files and registers routers from `tg_auth` and `api`.
  - Several template endpoints for the dashboard (`/dashboard`, `/assistant/{id}`, `/connect-tg`, etc.).

- `api.py`
  - Defines `api_router` with:
    - `POST /api/check_groups` — streaming NDJSON endpoint that calls `main_app.orchestrator.run_full_pipeline_stream` and yields JSON lines to the client. It collects `summary` events into a in-memory cache `_last_reports_cache`.
    - `GET /api/reports` — returns the last run's collected reports (cache-based).
    - `GET /api/assistants` — returns list of assistants joined with group info from PostgreSQL and their local Telegram session status from `assistant_tg_info`.
  - Utility functions: `fetch_assistant_tg_status_map()`, `fetch_student_info_map(student_ids)`.

- `orchestrator.py`
  - Core streaming orchestrator: `run_full_pipeline_stream(group_ids, assistant_id)` returns an async generator yielding dict events with `state` (accounts, chat_history_checking, summary, error, batch_done, done).
  - Steps mirrored from E2E pipeline: fetch progress snapshots -> call progress_analyzer -> save group_check_logs -> resolve targets to assistants -> fetch chat histories per assistant -> yield chat_history events -> call ai_agent_app.analyze_chat_history -> save reports.
  - Implements fault isolation: try/except around each major step, writes logs and yields `error` events while continuing.

- `tg_auth.py`
  - APIRouter prefix `/telegram/assistant` for programmatic assistant login flows (send-code, verify-code, verify-password) using Pyrogram.
  - Functions:
    - `_check_assistant_exists(assistant_id)` checks PostgreSQL user exists.
    - `_finish_successful_login` finalizes session by writing to `assistant_tg_info` and returning success.
  - Holds `active_login_sessions` to keep Pyrogram client + phone_code_hash during multi-step interactive HTTP flow.

### ai_agent_app/
Purpose: wrap LLM calls and schema enforcement; persist AI results.

Files:
- `analyzer.py`
  - Key function: `analyze_chat_history(history: ScrubbedChatHistory) -> InteractionReport`.
  - Uses `langchain_google_genai.ChatGoogleGenerativeAI`, wraps with `with_structured_output(InteractionAnalysis)` to enforce response schema.
  - Builds messages: `SystemMessage` using `prompts.SYSTEM_PROMPT`, and `HumanMessage` from `prompts.build_user_prompt()`.
  - On success converts `InteractionAnalysis` to `InteractionReport` dataclass. On error returns a safe default InteractionReport with score 0 and an explanatory summary.

- `prompts.py`
  - `SYSTEM_PROMPT` instructs the LLM how to evaluate assistant-student interactions.
  - `build_user_prompt(chat_text, problem)` returns the user message text including the pre-identified problem if present.

- `schema.py`
  - Pydantic `InteractionAnalysis` model that enumerates all expected fields from Gemini: `support_quality_score`, `assistant_contacted_student`, `contact_summary`, `addressed_issues`, `discussed_flagged_problem`, `offered_help`, `problem_discussed`, `last_contacted_date`, `summary`, `recommendations`.
  - Enforced via LangChain `with_structured_output` so the LLM response is parsed & validated.

- `reports_repository.py`
  - Persists `InteractionReport` dataclasses into local SQLite `ai_reports` (raw_model_response JSON stored in `raw_json` field).
  - Functions: `save_report(report)` and `save_reports_batch(reports)` with fault isolation.

### accounts_app/
Purpose: fetch and prepare progress data, call LLM to select problematic students.

Files:
- `repository.py`
  - DB access to fetch group ids, group progress snapshot, and to resolve problematic students to assistant + student info.
  - Important functions: `fetch_all_group_ids()`, `fetch_group_progress_snapshot(group_id, group_name)`, `fetch_group_progress_snapshots(group_ids)`, `fetch_group_progress_batches(group_ids=None)`, `resolve_targets_for_problems_with_assistant(problems, assistant_id)`.
  - Also includes `resolve_leader_targets_for_problems` (maps based on DB group->assistant associations) and helper queries.

- `progress_analyzer.py`
  - `analyze_group_progress(snapshot)` sends snapshot JSON to LLM with `accounts_app.progress_prompts.PROGRESS_SYSTEM_PROMPT` and expects `GroupProgressAnalysis` schema.
  - `analyze_group_progress_batch(snapshots)` runs each group's analyze sequentially (small sleep between calls). `only_with_problem` filters only students with problems.

- `progress_prompts.py` and `progress_schema.py`
  - Provide LLM system prompt and Pydantic schema for group progress analysis.

### chat_history_app/
Purpose: connect to Telegram via Pyrogram sessions and fetch private chat histories per assistant-student, scrub names and update tracking.

Files:
- `fetcher.py`
  - `fetch_chat_history_for_student(client, assistant, student, problem)` retrieves messages since `chats_last_check` using `get_chat_history` from Pyrogram, scrubs names, and updates `chats_last_check`.
  - `_safe_pyrogram_call(coro_factory, max_retries)` wraps Pyrogram calls to handle `FloodWait` exceptions with retry/backoff.
  - `_resolve_chat_id_for_student(client, student)` resolves chat id using `student.user_id_number` or name fallback heuristics.
  - `fetch_all_histories_for_leader(assistant, students, problems_by_student)` opens a session using `tg_config.sessions_dir/<session_name>` and iterates students.
  - Global: `builtins.input` is overridden to prevent interactive login inside pipeline (raises ConnectionError if called).

- `scrubber.py`
  - Builds regex patterns for assistant and student name parts and replaces them with `assistant_{id}` and `student_{id}` respectively. `build_name_patterns` and `scrub_text`.

- `tracking.py`
  - Reads/writes `chats_last_check` in local SQLite. Functions: `get_last_check_date(assistant_id, student_id)` and `update_last_check_date(assistant_id, student_id, checked_at)`.

### scripts/
Purpose: interactive utilities executed manually by operators.

Files:
- `login_assistant.py` (also `login_leader` referenced in README; repository has `login_assistant.py`)
  - Full interactive flow using Pyrogram to create a session file for a given assistant (user.id), ask for phone, code, optional 2FA password.
  - On success, writes session to `sessions/assistant_<id>` and upserts row to `assistant_tg_info` via `shared/local_db.upsert_assistant_tg_info`.
  - This script is intended to be run manually and only once per assistant (or when session expires).

### frontend/
Contains templates (Jinja2 templates) and static JS/CSS used by the provided UI. Main pages: `dashboard.html`, `group_check.html`, `assistants.html`, `assistant-reports.html`, `assistant-detail.html`, `tg_auth.html`. JS under `frontend/js` processes NDJSON streaming and updates UI in real time.

Important: The streaming API contract is in `API_STREAMING.md` and `frontend/example.json` provides example event payloads per state.

---

## Important functions and behavioral details (reference)

Below is a concise function-to-purpose mapping for maintainers.

- shared/config.py
  - `db_config.conn_string` — used by `shared/db.get_connection()` (note password hidden in representation).
  - `tg_config.sessions_dir` — path where Pyrogram session files are stored (guaranteed to exist on import).

- shared/db.get_connection() — yields psycopg2 connection with NamedTuple-like cursor; handles rollback/close.

- shared/local_db.get_local_connection() — yields sqlite3.Connection, sets row_factory to sqlite3.Row.
  - ensure_*_exists() functions: create tables idempotently.
  - upsert_assistant_tg_info(...)
  - insert_group_check_log(...), insert_student_issues(...), resolve_student_issues(...)
  - categorize_issue(problem_text) — simple Uzbek keyword heuristic mapping to categories (`homework_missing`, `low_attendance`, `other`).

- shared/models.ScrubbedChatHistory.to_prompt_text() — converts messages to prompt text where names are already replaced with `assistant_{id}` or `student_{id}`.

- accounts_app.repository.fetch_group_progress_snapshots(group_ids) — returns list of GroupProgressSnapshot for given groups; used as input to LLM progress analyzer.

- accounts_app.progress_analyzer.analyze_group_progress(snapshot)
  - sends snapshot JSON to LLM; returns list[StudentProblem]. Fault-tolerant: returns empty list on LLM or other errors.

- chat_history_app.fetcher.fetch_all_histories_for_leader(assistant, students, problems_by_student)
  - opens Pyrogram session (`Client(session_path, api_id, api_hash)`), iterates students and calls `fetch_chat_history_for_student`.
  - fetch_chat_history_for_student uses `get_chat_history(chat_target, limit=200)` then filters messages newer than last_check_date and scrubs them.
  - uses `_safe_pyrogram_call` to handle FloodWait (with retries defined by `app_config.flood_wait_max_retries`).

- ai_agent_app.analyzer.analyze_chat_history(history)
  - uses `ChatGoogleGenerativeAI` configured with `ai_config` and `with_structured_output(InteractionAnalysis)` to get validated structured output; converts into `shared.models.InteractionReport`.
  - On exception returns default `InteractionReport` with support_quality_score=0 and textual message signaling technical error.

- ai_agent_app.reports_repository.save_report(report)
  - stores `report` into local SQLite `ai_reports` table and serializes raw model JSON into `raw_json`.

- main_app.orchestrator.run_full_pipeline_stream(group_ids, assistant_id)
  - the orchestrator yields events for each major step. Key states: `accounts`, `chat_history_checking`, `summary`, `batch_done`, `done`, `error`.
  - writes group_check_logs and student_issues into local SQLite for audit/trending.

- main_app.api StreamingResponse logic
  - collects `summary` events into `_last_reports_cache` (in-memory). If StreamingResponse is interrupted, cache still updated in the generator `finally` block.

---

## API endpoints (summary)

- GET / (redirects to /dashboard)
- GET /dashboard, /assistants, /connect-tg, /assistant/{id}, /group-check — templates
- API prefix `/api`
  - POST /api/check_groups — streaming NDJSON (expects `GroupsCheckRequest` body with `group_ids` and `assistant_id`). Each NDJSON line is a JSON object with `state` and `data`.
  - GET /api/reports — returns last cached run's `summary` reports
  - GET /api/assistants — returns assistants list with group info and Telegram session status
- APIRouter `/telegram/assistant` (main_app/tg_auth.py)
  - POST /telegram/assistant/send-code
  - POST /telegram/assistant/verify-code
  - POST /telegram/assistant/verify-password

See `API_STREAMING.md` for NDJSON contract details and example JS frontend code to consume the stream.

---

## Running locally

1. Install dependencies:

   pip install -r requirements.txt

2. Copy `.env.example` to `.env` and fill values (PostgreSQL credentials, TG_API_ID/HASH, GOOGLE_API_KEY). Do NOT commit `.env`.

3. Create Pyrogram sessions for assistants (one-time): run `python -m scripts.login_assistant` and follow prompts.

4. Start the API server (development):

   uvicorn main_app.api:app --reload

5. Use the frontend at `/frontend` or call `/api/check_groups` with `group_ids` and `assistant_id` JSON body to start a streaming run.

Notes:
- The app creates local SQLite tables automatically on startup (server lifespan ensures it).
- For production, run under a proper process manager, set environment variables securely, and ensure PostgreSQL is reachable.

---

## Security & operational notes

- Never store secrets in the repo. `.env` should remain private; only `.env.example` is included as safe template.
- Pyrogram sessions are stored under `sessions/` — protect that folder.
- FloodWait handling: Pyrogram requests may raise `FloodWait` — code retries with wait = e.value + 1 seconds, up to configured retries.
- LangChain/Gemini calls use `with_structured_output` to minimize parsing errors; still, analyzer functions catch exceptions and return safe defaults so pipeline continues.
- The pipeline intentionally scrubs personal names before sending text to the model. The scrubber uses simple regex patterns based on first/last name tokens — consider stronger anonymization if required.

---

## Where to look to change behavior

- To alter LLM model / parameters: `shared/config.py` (AIConfig) and `.env` keys `AI_MODEL`, `AI_MAX_TOKENS`, `AI_TEMPERATURE`.
- To change progress batch size: `PROGRESS_GROUP_BATCH_SIZE` in `.env` / `AppConfig`.
- To change Pyrogram session dir: `TG_SESSIONS_DIR` in `.env` / `TelegramConfig`.
- To change local DB schema or storage path: `shared/local_db.py` and `LOCAL_SQLITE_PATH`.
- To change streaming API shape: `main_app.api` and `main_app.orchestrator`.

---

## Quick developer checklist

- Ensure `.env` exists and contains valid DB & API keys (do not check into VCS).
- Create Pyrogram sessions via `scripts/login_assistant.py` for assistants who will be queried.
- Confirm `local_data.sqlite3` is writable and `sessions/` directory is accessible.
- Run `uvicorn main_app.api:app --reload` and test `/api/check_groups` with small group list.

---

If any specific module or function should be expanded with code-level comments or example usages, indicate which files or functions and a follow-up doc will be provided.
