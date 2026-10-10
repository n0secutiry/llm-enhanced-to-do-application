# LLM-enhanced TODO API

A REST API for task notes built with FastAPI and MongoDB, where a local LLM
(Ollama) performs **auxiliary, non-critical** work: it generates note titles and
supplies narrow signals for prioritisation.

The guiding principle: **the LLM provides a signal, business logic makes the
decision.** The model never returns a priority — it returns `urgency`, `effort`
and `blocks_others`, and a deterministic Python formula turns those into a
number. If the model is unavailable, slow or returns garbage, the application
keeps working on neutral defaults (graceful degradation).

## Why it is built this way

Asking a model "what is the priority of this task, 1 to 10?" looks simpler, but
the answer drifts between runs, cannot be explained to a user and cannot be
tested. Splitting the work solves all three problems:

| Who | Responsibility |
|---|---|
| **LLM** | bounded estimates: urgency 1–5, effort 1–5, blocks_others true/false |
| **Python** | today's date, days until the deadline, number of open tasks, the final score |

The result is reproducible, explainable (`GET /todos/next` returns the reason
for every suggestion), covered by tests that never call a model, and still
useful when the model is down. This pattern is called **deterministic prompt
augmentation**.

## Architecture

```
HTTP
 │
 ▼
routers.py        ← HTTP layer: request validation, status codes, Depends, rate limit
 │
 ▼
service.py        ← business logic: title ownership, fallbacks, prioritisation
 │        ├─────────────► llm/service.py ──► Ollama (structured JSON, retries, tracing)
 │        └─────────────► scoring.py    ──► the priority formula (pure Python)
 ▼
repository.py     ← MongoDB access: filters, pagination, soft delete, atomic updates
 │
 ▼
MongoDB
```

Rules the code follows:

- routers never touch the MongoDB driver directly;
- the repository knows nothing about HTTP or the LLM;
- request schemas describe what the **client is allowed** to send; anything the
  server owns (`title_source`, `priority_score`, `priority_signals`, timestamps)
  is written through dedicated repository methods;
- the Mongo client and the Ollama client are created once in `lifespan` and
  handed out through `Depends`;
- the scoring formula is a pure function, so it is unit-tested without Mongo.

## Stack

| Purpose | Tool |
|---|---|
| HTTP | FastAPI, Uvicorn |
| Database | MongoDB via `pymongo` (`AsyncMongoClient`) |
| Validation | Pydantic v2, pydantic-settings |
| LLM | Ollama, `qwen2.5:1.5b`, structured JSON output |
| Observability | loguru with per-request `Log ID`, optional LangFuse tracing |
| Tests, linting | pytest, ruff, mypy |
| Runtime | Docker Compose, multi-stage image, non-root container |

## Running the project

You need Docker Desktop and [Ollama](https://ollama.com) on the host.

```bash
# 1. the model used for generation
ollama pull qwen2.5:1.5b

# 2. configuration
cp .env.example .env     # then fill in the values

# 3. start the API and MongoDB
docker compose up -d --build

# optional: the database browser
docker compose --profile tools up -d
```

- API and Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- mongo-express: http://localhost:8081 (only with the `tools` profile)

Ollama runs on the host, so `.env` points to `http://host.docker.internal:11434`
— that is how a container reaches its host. The app starts even when Ollama is
unreachable; `/health` then reports `"llm": "unavailable, using fallbacks"`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/todos` | Create a note. Without a `title` one is generated in the background |
| `GET` | `/api/v1/todos` | List notes: `status`, `tag`, `priority_gte` filters, `limit`/`offset` |
| `GET` | `/api/v1/todos/next` | Top three notes to work on now, with a reason each |
| `GET` | `/api/v1/todos/{id}` | A single note |
| `PATCH` | `/api/v1/todos/{id}` | Partial update |
| `DELETE` | `/api/v1/todos/{id}` | Soft delete (sets `deleted_at`) |
| `POST` | `/api/v1/todos/{id}/regenerate-title` | Generate the title again (rate limited) |
| `POST` | `/api/v1/todos/{id}/prioritize` | Recompute the priority (rate limited) |
| `POST` | `/api/v1/llm` | Generate a title from arbitrary text (prompt-tuning helper) |
| `GET` | `/health` | MongoDB connectivity plus LLM availability |

### Examples

Creating a note without a title — the response arrives immediately:

```bash
curl -X POST localhost:8000/api/v1/todos \
  -H 'Content-Type: application/json' \
  -d '{"content": "Call the clinic and book a check-up for Monday morning"}'
```

```json
{
  "id": "6abfbf111262a728cdf54f68",
  "title": "Call the clinic and book a check-up for",
  "title_source": "fallback",
  "priority_score": 0.0,
  "priority_signals": null
}
```

A second later the same note carries a generated title and a computed priority:

```bash
curl localhost:8000/api/v1/todos/6abfbf111262a728cdf54f68
```

```json
{
  "title": "Book a clinic check-up",
  "title_source": "llm",
  "priority_score": 12.5,
  "priority_signals": {
    "urgency": 4,
    "effort": 1,
    "blocks_others": false,
    "reasoning": "a short appointment with a near deadline"
  }
}
```

Asking what to do now:

```bash
curl localhost:8000/api/v1/todos/next
```

```json
{
  "items": [
    {
      "todo": { "title": "Ship the release" },
      "priority_score": 12.0,
      "reason": "score 12.0; overdue by 9 day(s); urgency 3/5, effort 3/5"
    }
  ],
  "generated_at": "2026-10-10T11:02:13.481Z"
}
```

## How title generation works

1. `POST /todos` without a `title` **never waits for the LLM**: the note is
   created straight away with the first 40 characters of the text and
   `title_source="fallback"`.
2. Once the response is sent, a background task calls Ollama.
3. The prompt lives in [app/prompts/prompt.txt](app/prompts/prompt.txt). The
   user's text is wrapped in markers and labelled as **data, not instructions**
   — the prompt-injection guard. Examples inside the prompt are written in
   different languages on purpose: they teach the model to answer in the same
   language as the input.
4. The answer comes back as structured JSON: Ollama receives
   `format=<Pydantic JSON schema>` and the result is validated against it
   (3–60 characters).
5. Invalid answers are retried, then abandoned in favour of the fallback.
6. The write is atomic — the update only applies while `title_source` is still
   `"fallback"`, so a title typed by the user is never overwritten.

`title_source` always records the origin: `user`, `llm` or `fallback`.

## How prioritisation works

1. `build_priority_context` collects facts the model cannot know: today's date,
   the deadline, the exact number of days left, the status, tags and how many
   tasks are currently open. No LLM involved, fully testable.
2. Those facts are injected into
   [app/prompts/priority_prompt.txt](app/prompts/priority_prompt.txt), which
   asks only for signals and states explicitly that the model does not decide
   the priority.
3. `PrioritySignals` validates the answer: `urgency` and `effort` must be 1–5.
   An out-of-range answer is retried, then replaced by neutral defaults
   (`urgency=3, effort=3, blocks_others=false`).
4. [app/v1/todo/scoring.py](app/v1/todo/scoring.py) computes the score:

   ```
   score = w1*urgency + w2*(6 - effort) + w3*blocks_others + deadline_boost(days_left)
   ```

   `6 - effort` inverts the effort scale, so a quick task wins over a slow one
   when everything else is equal. `deadline_boost` adds +3.0 when overdue,
   +2.0 today, +1.0 within three days, 0 otherwise. The weights `w1`, `w2`,
   `w3` come from configuration, not from code.
5. The signals are stored next to the score, so it stays visible what the model
   said and what the system decided.

### Comparing prompt versions

[scripts/prompt_ab.py](scripts/prompt_ab.py) measures how closely a prompt's
ordering matches a reference ordering you provide by hand, using Spearman's
rank correlation:

```bash
uv run python scripts/prompt_ab.py --runs 3
uv run python scripts/prompt_ab.py --prompt-b app/prompts/my_other_prompt.txt
```

The dataset in [scripts/priority_dataset.json](scripts/priority_dataset.json)
holds ten tasks with a `manual_rank` each — replace them with your own tasks and
your own ordering to get a meaningful number.

## Observability

- Every request is logged with a short `Log ID` shared by the request and the
  response lines, so one request can be followed through the log.
- Logs go to the console and to `/logs/app.log` inside a named volume.
- LLM calls are traced to **LangFuse** when `LANGFUSE_PUBLIC_KEY` and
  `LANGFUSE_SECRET_KEY` are set: prompt, answer, latency, token counts, model
  name and prompt version (`title-v2`, `priority-v1`). With empty keys tracing
  is off and nothing is sent anywhere. A tracing failure never breaks a request.

## Indexes

Created on startup by `create_todo_indexes`:

| Index | Purpose |
|---|---|
| `deleted_at + status` | listing by status (deleted notes are always excluded) |
| `deleted_at + priority_score` | sorting by priority, `GET /todos/next` |
| `due_date` | deadline queries |
| `tags` | filtering by tag |
| text index on `content` | full-text search |

## Development

```bash
uv sync                  # install dependencies
uv run pytest            # 62 tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy              # type check
```

The test suite is split by what it needs:

- **scoring, rate limiting, prompt context** — pure functions, no services;
- **LLM service** — a scripted fake Ollama covers valid answers, malformed
  answers, out-of-range signals, timeouts and a missing client;
- **repository and API** — a real MongoDB in a separate `<name>-test` database
  that is wiped before each test, with the LLM faked. When Mongo is not
  running, these tests are skipped rather than failing.

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs lint, format
check, mypy, the full test suite against a MongoDB service container, and a
Docker image build.

## Limitations

- **Title quality is bounded by the model.** `qwen2.5:1.5b` often drifts to the
  wrong language and can distort meaning. A larger model (`qwen2.5:3b` and up)
  behaves noticeably better; the code only needs `OLLAMA_MODEL` changed.
- **Background work has no queue.** If the app restarts between creating a note
  and finishing the task, the title stays a fallback and the priority stays 0.
  A real deployment needs an external queue (Celery, ARQ, Dramatiq).
- **The rate limiter is in-process.** It counts requests in a single process
  and resets on restart; multiple workers or containers need Redis.
- **No authentication.** All notes are shared, there is no concept of a user.
- **Logs capture every request header**, including `cookie`. The header list
  should be filtered before production.
- **`priority_gte` filtering and sorting assume priorities were computed.**
  A note that was never prioritised keeps a score of 0 and sinks to the bottom.
- **The prompt A/B dataset ships with example tasks**, not with a real labelled
  set, so the correlation it reports is only as meaningful as the ranks you put
  in it.
