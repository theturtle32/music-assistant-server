# Background tasks controller

The long-running task manager for user-visible background work: library syncs, playlist mutations,
metadata refreshes, index rebuilds, the audio analysis scan.

**This controller is for work a user should be able to see and interfere with.** Short-lived
internal jobs belong on the event loop helpers instead. Three different things get called "tasks"
in this codebase, and only this one emits events or appears in the frontend; see
[events and commands](../../../docs/architecture/events-and-commands.md) for the other two.

## Module layout

| Module | Role |
|---|---|
| `controller.py` | Orchestration, API handlers, queueing, the execution lifecycle |
| `constants.py` | Queue, log and retention limits, and the context variables |
| `context.py` | The runtime handle task code uses to report progress and issues |
| `helpers.py` | Visibility, sorting, retention, timer ids, log capture |
| `models.py` | The runtime-only task state container |

## Two kinds of task

| Kind | Lifetime | Retention |
|---|---|---|
| Scheduled | Registered at provider or controller setup, visible even while idle | Kept in memory permanently, runtime state persisted |
| Ad hoc | Queued immediately, runs once | Bounded history |

A scheduled task is always listed even when it has never run, and that is the point of registering
one rather than just setting a timer. It gives the user somewhere to see when the next run is due,
pause it, change its schedule, or run it now.

## Success, failure, and partial success

A long sync that fails on three of five thousand tracks is not a failure, and reporting it as
success hides real problems. Task code reports each recoverable problem as a non-fatal issue, and a
handler that returns normally with a non-zero issue count is recorded as partial success rather
than success.

## Scheduling

Schedules are hourly, daily or weekly, all in UTC. A candidate time that has already passed rolls
forward, and a weekly schedule evaluates every listed day and takes the earliest. Each scheduled
task gets its own timer so it can be rescheduled or cancelled independently.

**Runtime state is persisted; definitions are not.** The handler and the schedule shape come from
code and are re-registered on every startup, while the last run, the failure state and the enabled
flag live in this controller's core config. That split means a restart preserves "when did this
last run" and "the user paused this" without the config ever holding a schedule the code disagrees
with. Re-registering a known id merges, refreshing the definition while carrying the persisted
state forward.

## Execution and concurrency

Pending task ids sit in a queue drained up to a configurable concurrency limit. A priority task is
inserted at the front, so a user-initiated action is not stuck behind a background metadata
refresh.

Deduplication is by task id. Queueing an id that is already active returns the existing task
unchanged rather than starting a second run; an inactive task with that id is replaced. Requeueing
resets logs, progress and failure state, so the UI shows the current run rather than a mixture of
two.

Cancellation, exceptions and clean returns each map to a status, every outcome appends a lifecycle
log line, and the teardown reschedules the next occurrence for a scheduled task or trims history
for an ad hoc one.

### Tearing down

Plain unregistering only requests cancellation, so a task can still be unwinding when the caller
continues. That matters for a teardown path about to destroy state the task is still touching, such
as unloading a provider whose sync holds a network share mount, so there is a variant that waits,
bounded by a timeout.

Be aware of the limit of that guarantee: a task blocked in a thread unwinds immediately while its
thread keeps running, so a return does not prove all of the task's work has stopped.

## Log capture needs no cooperation

A log handler on the root logger reads the active task from a context variable, so **task code needs
no logging awareness at all.** Any module logging anywhere inside a task's call stack, including
deep inside a provider or a helper, has its output attributed to that task and shown in the UI.
Nothing outside a task is captured, because the context variable is unset.

Two details. The handler hands lines to the event loop thread-safely, unlike the event bus, because
logging genuinely arrives from executor threads. And each task's buffer is bounded, with failure
messages capped separately.

The same context-variable approach gives task code a progress handle without threading the
controller through every call, so a helper five frames deep can report progress without knowing
which task it is in.

## Markdown reports

A task can attach a Markdown report explaining what it did, which the UI renders. That is the right
shape for an outcome that is neither a percentage nor an error: playlist migration reports which
tracks matched exactly, which were approximated and which could not be found.

A report can be set by task id, for the task active in the current context, or from a handler that
already holds its context. It is persisted on scheduled tasks and reset when the task reruns.

## Events, throttled two ways

State changes reach clients as one event type, emitted at two speeds. Lifecycle changes are
debounced briefly so they stay responsive, while progress and log churn is throttled to a much
longer interval. Without that, a sync reporting per-track progress would flood every connected
client. Both funnel through one timer, so at most one update is in flight.

The WebSocket layer re-derives the payload per connection rather than forwarding the event as-is,
so each client sees only the tasks visible to it.

## Visibility is per user

A caller holding the manage scope sees every task. Anyone else sees only tasks they own, so a
non-admin sees the playlist edit they started and nothing else. Sorting puts running tasks first,
then pending, then scheduled, then finished, each group by most recently updated.

## Related architecture docs

- [Operations](../../../docs/architecture/operations.md) for the big picture and for diagnostics.
- [Configuration](../../../docs/architecture/configuration.md) for the concurrency setting.
- [API and auth](../../../docs/architecture/api-and-auth.md) for the scopes these commands require.
