# ASYNC TIMEOUT FIX — Implementation Plan
**Pattern: Background Thread + Polling**

> **Scope:** Flask Backend | **Target:** One User at a Time | **Host:** Render Free Tier (0.1 CPU / 512MB)

---

## 1. Problem Statement

The Flask backend hosts compute-heavy pipelines (Pose, Audio, Evaluation). These pipelines take 90–120 seconds to complete and longer on Render's free tier due to constrained CPU.

The current architecture holds an open HTTP connection for the full duration of the pipeline. This causes the following failure modes:

| Failure Mode | Root Cause |
|---|---|
| Gunicorn timeout | Gunicorn worker kills requests exceeding its `--timeout` setting |
| Render proxy timeout | Render's reverse proxy hard-kills connections after ~30s on free tier |
| Worker starvation | A single worker blocked for 120s cannot serve any other request |
| MediaPipe delay amplified | Video duration directly increases pipeline time — long videos fail more often |

Raising the Gunicorn timeout alone does **not** solve the Render proxy limit, does not free the worker, and does not scale with longer videos.

---

## 2. Chosen Solution

> **Decision: Background Thread + In-Memory Job Store**
>
> Decouple pipeline execution from the HTTP request lifecycle. The HTTP request returns immediately with a `job_id`. The pipeline runs in a background thread. The frontend polls a separate status endpoint until the job is complete.

This solution was chosen over alternatives for the following reasons:

| Option | Verdict | Reason |
|---|---|---|
| Raise timeout only | ❌ Rejected | Doesn't fix Render proxy limit or worker blocking |
| RabbitMQ | ❌ Rejected | Requires broker + consumer process — overkill for 1 user |
| Celery + Redis | ⚠️ Deferred | Correct at scale; unnecessary complexity for current use |
| Background Thread + Poll | ✅ Chosen | Zero new services, ~30 lines of change, fits 1-user constraint perfectly |

---

## 3. Architecture Change

### 3.1 Before (Current — Broken)

```
POST /analyze
    → Gunicorn worker receives request
    → Pipeline runs synchronously (90–120s)
    → Gunicorn times out OR Render proxy kills connection
    → Client receives 504 / connection error
```

### 3.2 After (Target — Fixed)

```
POST /analyze
    → Gunicorn worker receives request
    → Background thread is spawned with the pipeline function
    → HTTP request returns immediately:  { job_id: "abc-123" }  (202 Accepted)

GET /status/<job_id>   [polled every 4s by frontend]
    → Returns: { status: "processing" }            while running
    → Returns: { status: "done", result: {...} }   when complete
    → Returns: { status: "error", error: "..." }   if pipeline fails
```

---

## 4. What Needs to Change

Changes are **confined to route handler files only**. Pipeline logic, metrics, aggregators, and all other modules remain completely untouched.

### 4.1 Files to Modify

| Layer | Change Required |
|---|---|
| Route handler(s) for pipeline endpoints | Replace synchronous pipeline call with background thread dispatch + return `job_id` |
| Route handler(s) — new endpoint | Add `GET /status/<job_id>` endpoint that reads from the job store |
| Gunicorn launch command | Change to `--workers 1 --threads 2 --timeout 120` |

### 4.2 Files to NOT Modify

- Pipeline orchestrator files — pipeline logic is unchanged
- Any metrics, normalizer, aggregator, or derived_attributes files
- `config.py` — no constants change
- `db_handler.py` — database writes still happen inside the pipeline as before
- `llm_interpreter.py` — LLM call still happens at the end of the evaluation pipeline
- `app.py` / blueprint registration — no changes needed

---

## 5. Implementation Instructions

The following steps must be applied to **every pipeline route endpoint** in the codebase.

---

### Step 1 — Add a job store at the top of each route file

Add the following at module level, near the imports:

```python
import threading
import uuid

# In-memory store: { job_id (str) -> job_record (dict) }
# job_record shape: { "status": str, "result": dict|None, "error": str|None }
# status values:    "processing" | "done" | "error"
jobs = {}
```

---

### Step 2 — Create a background worker function

Create a **private function** (underscore prefix) in the same route file. This function must:

- Accept `job_id` + any arguments needed by the pipeline (e.g. file path, session_id)
- Set `jobs[job_id] = { "status": "processing" }` at the start
- Call the existing pipeline function **exactly as the route currently calls it** — no changes to how the pipeline is invoked
- On success → set `jobs[job_id] = { "status": "done", "result": <pipeline output>, "error": None }`
- On exception → set `jobs[job_id] = { "status": "error", "result": None, "error": str(exception) }`
- In a `finally` block → clean up any temp files (e.g. delete `/tmp/<session_id>.mp4`)
- Use `logger` (not `print`) for all logging — same logger already in scope in the route file

---

### Step 3 — Modify the existing POST route

Change the existing route handler so that:

- Everything **before** the pipeline call stays the same (file validation, saving to `/tmp`, generating `session_id`)
- Generate a new `job_id` using `str(uuid.uuid4())`
- Set `jobs[job_id] = { "status": "processing", "result": None, "error": None }`
- Spawn a `threading.Thread` targeting the background worker function, passing `job_id` + pipeline args
- Set `daemon=True` on the thread so it doesn't block server shutdown
- Call `thread.start()`
- **Return immediately** — JSON response `{ "job_id": job_id, "session_id": session_id }` with HTTP `202`
- **Do NOT** await the thread. **Do NOT** call `thread.join()`. The route must return in milliseconds.

---

### Step 4 — Add a new GET /status route

Add a new route to the same blueprint:

- **Method:** `GET`
- **Path:** `/status/<job_id>` (or `/<pipeline_prefix>/status/<job_id>` to match your existing URL convention)
- **Logic:**
  - Look up `job_id` in the `jobs` dict
  - If not found → return `{ "status": "not_found" }` with HTTP `404`
  - If found → return the full job record (`status` + `result` + `error`) with HTTP `200`
- No authentication needed — job_ids are UUIDs (unguessable)

---

### Step 5 — Update the Gunicorn launch command

Update the start command in your Render dashboard or `render.yaml`:

```bash
gunicorn "app:create_app()" --workers 1 --threads 2 --timeout 120
```

| Flag | Reason |
|---|---|
| `--workers 1` | Single process prevents MediaPipe from loading twice (RAM constraint) |
| `--threads 2` | One thread for pipeline execution, one thread free to serve polling requests |
| `--timeout 120` | Safety net only — pipeline no longer holds the request thread so this won't normally trigger |

---

## 6. Frontend Polling Contract

After receiving a `job_id` from a POST response, the frontend must implement the following polling loop:

```
1. POST to pipeline endpoint  →  receive { job_id }
2. Show loading state to user
3. Every 4 seconds, GET /status/<job_id>
4. If response.status === "processing"  →  continue polling
5. If response.status === "done"        →  stop polling, pass result to next step
6. If response.status === "error"       →  stop polling, show error to user
7. If response.status === "not_found"   →  stop polling, handle as unexpected error
8. Implement a max-poll timeout (e.g. 5 minutes) as a safety net
```

> **Poll interval:** 4 seconds is recommended. Gentle on free-tier CPU and fast enough for UX. Do not poll faster than every 2 seconds.

---

## 7. Constraints & Guardrails

### 7.1 What this solution handles

- Timeouts caused by long-running synchronous pipeline execution
- Render free tier reverse proxy hard limits
- Gunicorn worker blocking
- Any pipeline duration — scales with video length without hitting new limits

### 7.2 Known limitations (acceptable for current scope)

| Limitation | Why It's Acceptable |
|---|---|
| Job results lost on server restart | One user at a time; user re-submits if restart occurs |
| No job queue / concurrency control | One user at a time; a second request simply creates a second thread |
| No result TTL / cleanup | Server restart clears `jobs` dict naturally |
| Thread shares process memory | Safe for one user; no race conditions on separate `job_id`s |

### 7.3 When to upgrade this solution

- Multiple concurrent users needed → upgrade to **Celery + Redis**
- Job persistence across restarts needed → add a SQLite job table in `db_handler.py`
- Paid Render tier → increase `--workers` and remove `--threads` constraint

---

## 8. Implementation Checklist

Use this to verify the implementation is complete and correct before testing.

- [ ] `jobs` dict added at module level in every modified route file
- [ ] Background worker function created (private, underscore prefix)
- [ ] Background worker wraps pipeline call in `try / except / finally`
- [ ] `finally` block deletes the temp file regardless of success or failure
- [ ] POST route returns `202` + `job_id` immediately (no blocking)
- [ ] Thread spawned with `daemon=True`
- [ ] `GET /status/<job_id>` endpoint added to the same blueprint
- [ ] Status endpoint returns `404` for unknown `job_id`s
- [ ] Gunicorn launch command updated: `--workers 1 --threads 2 --timeout 120`
- [ ] No pipeline files modified (`pipeline.py`, `metrics.py`, `aggregator.py` etc. all unchanged)
- [ ] Frontend polling loop implemented with 4s interval and a max-timeout safety net

---

*Plan version 1.0 | Scope: single-user free-tier deployment | Upgrade path: Celery + Redis when concurrent users are required.*