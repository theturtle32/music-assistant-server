# 20 — Background Tasks and Diagnostics

Two operational-observability subsystems share this document because neither alone justifies one, and because they answer adjacent questions: *what is the server doing right now?* (`TasksController`) and *what went wrong?* (`DiagnosticsController`).

Both are core controllers, both are read through the API rather than through HTTP routes, and both are deliberately bounded in memory — neither writes a log file or a job table.

The in-tree [`controllers/tasks/README.md`](../../music_assistant/controllers/tasks/README.md) covers the tasks package's responsibilities and module layout; this document owns the model, the lifecycle, and the cross-cutting flows.

---

## Three things called "tasks"

The overloading is genuinely confusing, so start here:

| Thing | Purpose | User-visible? |
|---|---|---|
| `mass.create_task(coro, ...)` | Fire-and-forget internal work on the event loop, tracked so it can be cancelled at shutdown. Supports `task_id` deduplication and `eager_start` | No |
| `helpers/util.TaskManager` | Bounded-parallelism fan-out — an `asyncio.TaskGroup` alternative that does **not** cancel siblings when one member fails. Built on `mass.create_task` | No |
| `TasksController` (`mass.tasks`) | Long-running jobs with progress, logs, scheduling, retry, cancellation, and a UI surface | **Yes** |

Only the third emits events or appears in the frontend. See [01-event-system.md](01-event-system.md#task-creation-masscreate_task) for the first two. The tasks README states the boundary as a rule: short-lived internal jobs should keep using `mass.create_task` and `mass.call_later`.

---

## `TasksController`

`TasksController` (`controllers/tasks/`, ~1450 lines across six modules) manages work that a user should be able to see and interfere with: library syncs, playlist mutations, metadata refreshes, index rebuilds, the audio-analysis background scan.

### Two kinds of task

| Kind | Created by | Lifetime | Retention |
|---|---|---|---|
| **Scheduled** (recurring) | `register_scheduled_task(...)` | Registered at provider/controller setup, visible even while idle | Kept in memory permanently; runtime state persisted |
| **Ad hoc** | `run_background_task(...)` | Queued immediately, runs once | Bounded history, `MAX_FINISHED_TASK_HISTORY` = 100 |

A scheduled task is *always listed*, even when it has never run — that is the point of registering it rather than just calling `call_later`. It gives the user somewhere to see "library sync: next run in 4 hours", pause it, change its schedule, or run it now.

### The task model

`BackgroundTask` (`music_assistant_models.background_task`) is the serialized shape the frontend receives. Beyond the obvious identity and timestamp fields, the interesting ones:

| Field | Purpose |
|---|---|
| `status` | `TaskStatus`: `idle`, `pending`, `running`, `success`, `partial_success`, `failed`, `cancelled`, `unknown` |
| `schedule` | `TaskSchedule` for recurring tasks, `None` for ad hoc |
| `progress` / `progress_text` | Integer percentage (validated 0–100) or `None` for indeterminate, plus a human-readable phase string |
| `failure_count` / `failure_messages` | **Non-fatal** issues reported during a run — the mechanism behind `partial_success` |
| `logs` | In-memory tail of log lines captured during the run |
| `last_run_user_id` | Who last triggered it; `None` for automatic/system runs. Distinct from `user_id`, which is who *queued* an ad hoc task |
| `allow_retry` / `allow_cancel` | What the UI is allowed to offer |
| `translation_owner` | The namespace the task's `translation_key` resolves under; stamped by the controller and **not serialized** — see [21-localization.md](21-localization.md) |

`partial_success` is worth dwelling on. A long sync that fails on 3 of 5000 tracks is not a failure, and reporting it as success hides real problems. Task code calls `add_task_failure(message)` for each recoverable problem; if the handler then returns normally with a non-zero `failure_count`, `_run_task` records `PARTIAL_SUCCESS` rather than `SUCCESS` and logs "Task completed with N issue(s)".

### Scheduling

`TaskSchedule` supports three types, all in **UTC**, with constructor classmethods (`TaskSchedule.hourly()`, `.daily()`, `.weekly()`) and `__post_init__` validation that nulls out the fields irrelevant to the chosen type:

| Type | Fields | Meaning |
|---|---|---|
| `hourly` | `every` | Every N hours from now |
| `daily` | `every`, `hour`, `minute` | At a UTC clock time, every N days |
| `weekly` | `days_of_week`, `hour`, `minute` | At a UTC clock time on the given weekdays (Monday = 0, Sunday = 6; normalized and de-duplicated) |

`get_task_schedule_next_run()` computes the next moment. For daily and weekly, a candidate that has already passed today rolls forward; weekly evaluates every listed day and takes the earliest. Each scheduled task gets its own timer id (`managed_task_timer_{task_id}`) so it can be rescheduled or cancelled independently.

**Runtime state is persisted, definitions are not.** The handler and schedule shape come from code — re-registered on every startup — while `last_run`, failure state, and the `enabled` flag live in the `tasks` core config under `scheduled_task_states`. That split means a restart preserves "when did this last run" and "the user paused this" without the config ever holding a schedule the code disagrees with. `register_scheduled_task` on an already-known id **merges**: it refreshes the name, translation metadata, and schedule definition while carrying the persisted state forward via `merge_task_schedule_state`.

### Execution and concurrency

Queueing is a `deque` of pending task ids with a concurrency cap:

- `max_concurrent_tasks` defaults to **2** (`CONF_ENTRY_MAX_CONCURRENT_TASKS`, range 1–10, advanced, no reload needed)
- `_start_pending_tasks()` drains the queue while `running < max_concurrent`
- `priority=True` on `run_background_task` inserts at the **front** of the queue, so a user-initiated action is not stuck behind a background metadata refresh

Deduplication is by `task_id`: queueing an id that is already active returns the existing task unchanged rather than starting a second run. An *inactive* task with that id is replaced. Requeueing resets logs, progress, and failure state so the UI shows the current run, not a mixture.

`_run_task` wraps the handler and maps the outcome to a status: `CancelledError` → `cancelled`, any other exception → `failed` with `last_error` set, clean return → `success` or `partial_success`. Every outcome appends a lifecycle log line, and the `finally` block resets the context vars and finalizes the run (rescheduling the next occurrence for a scheduled task, trimming history for an ad hoc one).

### Log capture is contextvar-driven

This is the neatest part of the design. `TaskLogHandler` is attached to the **root logger** at controller setup, and `_run_task` sets `ACTIVE_TASK_ID` (a `ContextVar`) for the duration of the handler:

```python
def emit(self, record: logging.LogRecord) -> None:
    if not (task_id := ACTIVE_TASK_ID.get()):
        return
    line = self.format(record)
    self._mass.loop.call_soon_threadsafe(self._append_log, task_id, line)
```

The consequence is that **task code needs no logging awareness at all**. Any module logging anywhere inside a task's call stack — including deep inside a provider or a helper — has its output attributed to that task and shown in the UI's task log. Nothing outside a task is captured, because `ACTIVE_TASK_ID` is unset.

Two details: the handler uses `call_soon_threadsafe` (unlike the event bus, which can assume the loop thread) because logging genuinely arrives from executor threads; and each task's buffer is bounded by `max_log_lines`, default `DEFAULT_TASK_LOG_LINES` = 250, with failure messages separately capped at 25.

### The task execution context

`TaskExecutionContext` (`context.py`) is published on the `ACTIVE_TASK_CONTEXT` contextvar during a run, giving task code a handle for progress reporting without threading the controller through every call. `update_current_task_progress(progress, text)` on the controller is the convenience form — it reads the active task id from the contextvar, so a helper five frames deep can report progress without knowing which task it is in.

### API surface

Ten commands, split cleanly on scope:

| Command | Scope | Purpose |
|---|---|---|
| `tasks/list` | `SYSTEM_READ` | All tasks visible to the caller |
| `tasks/get` | `SYSTEM_READ` | One task by id |
| `tasks/log` | `SYSTEM_READ` | The task's captured log buffer |
| `tasks/run` | `SYSTEM_MANAGE` | Queue for immediate execution |
| `tasks/retry` | `SYSTEM_MANAGE` | Retry a failed or cancelled task |
| `tasks/cancel` | `SYSTEM_MANAGE` | Cancel a pending or running task |
| `tasks/set_enabled` | `SYSTEM_MANAGE` | Pause/resume automatic scheduling |
| `tasks/update_schedule` | `SYSTEM_MANAGE` | Change a recurring schedule |
| `tasks/remove` | `SYSTEM_MANAGE` | Drop a finished task from history |
| `tasks/clear_finished` | `SYSTEM_MANAGE` | Drop all finished ad hoc tasks |

**Visibility is per-user, not just per-scope.** `list_tasks_for_user(user)` and `is_task_visible_to_user()` show every task to a caller holding `Scope.SYSTEM_MANAGE`, but restrict anyone else to tasks whose `user_id` matches their own. So a non-admin user sees the playlist edit they started and nothing else. Sorting puts running tasks first, then pending, then scheduled, then finished — each group by most recently updated. See [19-authentication.md](19-authentication.md#the-scope-model) for the scope model.

### Events

State changes reach clients as `EventType.TASKS_UPDATED`, and the emission is deliberately two-speed:

| Change kind | Behaviour |
|---|---|
| Lifecycle (queued, started, finished, cancelled) | Debounced by `TASK_LIFECYCLE_UPDATE_DEBOUNCE` = 0.25 s — responsive |
| Progress and log churn | Throttled to `TASK_ACTIVITY_UPDATE_INTERVAL` = 10 s |

Without the throttle, a sync reporting per-track progress would flood every connected client. Both funnel through a single timer (`TASK_UPDATE_TIMER_ID`) so at most one update is in flight.

The WebSocket layer then **re-derives the payload per connection** rather than forwarding the event as-is, calling `list_tasks_for_user(user)` so each client sees only its own visible tasks. That special-casing is described in [12-webserver-api.md](12-webserver-api.md#event-subscription).

### Config and consumers

`tasks` joined `CONFIGURABLE_CORE_CONTROLLERS` (#4914) so it appears in the settings UI with its `max_concurrent_tasks` entry, and it carries an icon (`playlist-play`) like the other core modules (#5084). See [02-configuration.md](02-configuration.md) and [00-overview.md](00-overview.md).

Who registers work here:

| Consumer | Tasks |
|---|---|
| Music controller | Per-provider/per-media-type library sync (scheduled), plus ad hoc syncs — see [08-media-library.md](08-media-library.md#library-sync) |
| Playlists sub-controller | Ad hoc playlist mutations (add/remove tracks) |
| Metadata controller | Scheduled metadata maintenance passes, plus ad hoc refreshes — see [14-metadata.md](14-metadata.md) |
| Cache controller | Scheduled cache maintenance — see [02-configuration.md](02-configuration.md) |
| Audio analysis | The scheduled background analysis scan — see [16-audio-analysis.md](16-audio-analysis.md#background-scan) |
| Players controller | A scheduled maintenance pass |
| Genres sub-controller | Scheduled genre maintenance |
| Providers | `builtin`, `playlist_metadata`, `sonic_similarity` (index refresh), `lastfm_recommendations` |

Note that `unregister_scheduled_task` exists and is used: a provider that unloads removes its scheduled tasks, and by default clears their persisted state too.

---

## `DiagnosticsController`

`DiagnosticsController` (`controllers/diagnostics/`) plus `helpers/diagnostics.py` (#4652, extended in #4675) answers "what went wrong" with a single report designed to be **safe to paste into a public GitHub issue**.

The split between the two modules is the key design decision:

| Module | Role |
|---|---|
| `helpers/diagnostics.py` | **Always-on capture.** Stdlib-only, zero MA imports, so it can be installed before the server object exists |
| `controllers/diagnostics/` | **On-demand assembly.** Builds, sanitizes, and returns the report only when asked |

`install_diagnostics_log_handler()` is idempotent and attaches a single `DiagnosticsLogHandler` to the root logger. `__main__` installs it as early as possible; the controller adopts whatever is already there, or installs it itself for embedded use. The always-on cost is one handler doing bounded in-memory appends — no sanitization, no formatting, no I/O.

### There is no HTTP download endpoint

`diagnostics/get` is an API command requiring `Scope.SYSTEM_MANAGE`, with an optional `include_log_tail` flag. The HTTP download route that originally accompanied it was **removed in #4709**, so there is no `/diagnostics` URL to document. See [12-webserver-api.md](12-webserver-api.md#diagnostics).

### What the capture handler keeps

Two bounded structures, at `WARNING` and above:

- **A log ring**, `LOG_RING_MAXLEN` = 300 recent records (timestamp, level, logger, message truncated to 500 chars).
- **Exception aggregates**, up to `MAX_EXCEPTION_FINGERPRINTS` = 100, keyed by fingerprint with a count and first/last-seen timestamps.

The fingerprint is a SHA-256 prefix of `exception type | raise site | topmost music_assistant frame`, deliberately at **function granularity rather than line numbers** so a retry loop or a slightly shifted line does not fragment into many entries. The traceback walk reads only `tb_frame.f_code` — no `linecache`, no source files — and `TracebackException` is constructed with `lookup_lines=False`, deferring every source read to report time. That is what keeps an always-on handler cheap. The aggregate map is an `OrderedDict` with LRU eviction.

`emit()` is wrapped in a bare `except Exception: pass`, with the reasoning stated in the code: capturing diagnostics may never break logging itself.

### Report structure

`_build_report()` assembles five top-level sections, each in its own `try` so a failure becomes an `{"error": ...}` value rather than losing the whole report:

| Section | Contents |
|---|---|
| `system` | Version, Python, platform, add-on/safe-mode flags, uptime, a spot-sampled **event loop lag** measurement, memory RSS, data-dir disk free/total, and counts of threads, asyncio tasks, tracked tasks/timers, event subscribers, and WebSocket clients |
| `install` | A census: providers with load/availability state, player counts by provider and type, library counts per media type, and **which core config keys differ from default — key names only, never values** |
| `exceptions` | The aggregated exceptions, most recent first, with rendered tracebacks |
| `sections` | Pluggable contributions (below) |
| `log_tail` | Only when `include_log_tail=True` |

Alongside `schema_version`, `generated_at`, and `redaction_notice` — the report carries its own explanation of what was redacted, so a maintainer reading it knows what the placeholders mean.

Two things are pushed off the event loop: disk and memory probing (`asyncio.to_thread`) and traceback rendering (an executor, since `linecache` reads source files).

### Pluggable sections

Any core controller or provider can contribute by overriding `get_diagnostics()`, and external code can register a named callback with `register_section(name, callback)` (returning an unregister callable, with a guard so a stale unregister cannot remove a later registration under the same name).

`_collect_sections()` gathers three groups: core controllers from a fixed `CORE_CONTROLLER_ATTRS` tuple, every loaded provider sorted by `instance_id`, and the explicitly registered callbacks. Contributors that have **not** overridden the hook are skipped by identity comparison (`type(x).get_diagnostics is BaseClass.get_diagnostics`) rather than by calling and discarding — so the base no-op never appears as an empty section.

Each contributor is isolated: gathered concurrently, bounded by `SECTION_TIMEOUT` = **2 seconds**, and any exception becomes a sanitized `{"error": ...}` for that section only. Sync and async callbacks are both accepted (`inspect.isawaitable` on the result). The result is round-tripped through JSON to normalize and validate it, then sanitized in depth. `TasksController.get_diagnostics()` is a good example of the intended shape: totals, counts by status, scheduled count, pending-queue depth, concurrency limit — aggregate numbers, no names or payloads.

### Sanitization

Every string that reaches the report goes through `sanitize_text()`, and structures through `sanitize_data()` (which sanitizes dict **keys** as well as values). The redaction list, in application order:

| Target | Replacement |
|---|---|
| Absolute code paths | Shortened relative to `site-packages/` or `music_assistant/` |
| URL query strings and `user:pass@` userinfo | `?<redacted-query>`, `<redacted>@` |
| JWTs, `Bearer`/`Basic`/`Digest` values, `key=value` secret assignments, long token blobs | `<redacted-token>` / `<redacted>` |
| Media file paths and bare media filenames | `<path-{hash8}>.{ext}` |
| E-mail addresses | `<redacted-email>` |
| MAC addresses | `<mac-{hash8}>` |
| IPv6 then IPv4 addresses | `<redacted-ip>` |
| Home directories | `~` |

Several choices in there are worth understanding:

**Hashes, not blanks, for media paths and MACs.** A stable 8-char hash means the same value stays correlatable *within* one report — you can still see that the same file failed twelve times, or that two log lines concern one device — without revealing what it was.

**IP candidates are verified, not just pattern-matched.** `_redact_ip` parses each candidate with the `ipaddress` module and returns it unchanged if it does not parse, which stops timestamps and MAC-address lookalikes from being mangled. Loopback and unspecified addresses are deliberately **kept**, since `127.0.0.1` is diagnostically useful and not private. IPv6 is matched before IPv4 so an IPv4-mapped address is redacted whole.

**The long-token heuristic requires a digit.** 32+ characters of token alphabet only counts as a secret if it contains at least one digit — a cheap way to spare long `snake_case` identifiers and dotted module paths from being redacted as credentials.

**Media-filename redaction is deliberately greedy.** Because a bare filename can contain spaces, unquoted prose immediately preceding a media filename is redacted along with it. The code says why: privacy beats message fidelity here.

---

## Key Files

| File | Purpose |
|---|---|
| [`music_assistant/controllers/tasks/controller.py`](../../music_assistant/controllers/tasks/controller.py) | `TasksController` — registration, queueing, execution, the ten API commands, `get_diagnostics` |
| [`music_assistant/controllers/tasks/constants.py`](../../music_assistant/controllers/tasks/constants.py) | Concurrency/log/retention bounds, debounce intervals, `ACTIVE_TASK_ID` |
| [`music_assistant/controllers/tasks/helpers.py`](../../music_assistant/controllers/tasks/helpers.py) | `TaskLogHandler`, schedule maths, visibility and sorting, history trimming, state (de)serialization |
| [`music_assistant/controllers/tasks/context.py`](../../music_assistant/controllers/tasks/context.py) | `TaskExecutionContext` and `ACTIVE_TASK_CONTEXT` |
| [`music_assistant/controllers/tasks/models.py`](../../music_assistant/controllers/tasks/models.py) | `ManagedTask` — the runtime-only container wrapping `BackgroundTask` |
| [`music_assistant/controllers/tasks/README.md`](../../music_assistant/controllers/tasks/README.md) | In-tree overview: responsibilities, package layout, design notes |
| `music_assistant_models.background_task` | `BackgroundTask`, `TaskSchedule`, `TaskMetadata` |
| [`music_assistant/controllers/diagnostics/__init__.py`](../../music_assistant/controllers/diagnostics/__init__.py) | `DiagnosticsController` — report assembly, census, pluggable sections |
| [`music_assistant/helpers/diagnostics.py`](../../music_assistant/helpers/diagnostics.py) | Always-on capture handler, exception fingerprinting, `sanitize_text` / `sanitize_data` |
| [`music_assistant/helpers/util.py`](../../music_assistant/helpers/util.py) | `TaskManager` — the bounded-parallelism helper, not to be confused with this controller |
| [`music_assistant/constants.py`](../../music_assistant/constants.py) | `CONFIGURABLE_CORE_CONTROLLERS`, `CONF_ENTRY_MAX_CONCURRENT_TASKS` |
