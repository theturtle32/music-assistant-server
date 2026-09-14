# Operations

Two adjacent questions: what is the server doing right now, and what went wrong. Both are answered
by core controllers read through the API rather than through HTTP routes, and both are deliberately
bounded in memory. Neither writes a job table.

## Where things are on disk

| Path | Holds |
|---|---|
| The storage directory | Settings, the library database, the auth database, the log file and its rotations |
| The cache directory | The cache database, thumbnails, anything disposable |

The server logs to a file in the storage directory with rotated predecessors beside it, which is
the first place to look when something is not reproducible on demand. The library database is
readable with any SQLite client; treat it as read-only while the server is running.

## Background tasks

The tasks controller manages work a user should be able to see and interfere with: library syncs,
playlist mutations, metadata refreshes, the audio analysis scan.

**It is not the general-purpose scheduler.** Short-lived internal work belongs on the event loop
helpers described in [Events and commands](events-and-commands.md), which also disambiguates the
three different things called tasks in this codebase.

| Kind | Lifetime | Retention |
|---|---|---|
| Scheduled | Registered at setup, visible even while idle | Permanent, with runtime state persisted |
| Ad hoc | Queued immediately, runs once | Bounded history |

A scheduled task is always listed even when it has never run, and that is the point of registering
one rather than just setting a timer: it gives the user somewhere to see the next run, pause it,
change the schedule, or run it now.

### Partial success is a real outcome

A long sync that fails on three of five thousand tracks is not a failure, and reporting it as
success hides real problems.

Task code reports each recoverable problem as a non-fatal issue, and a handler that returns
normally with a non-zero issue count is recorded as partial success. That is the whole reason the
status set has more than success and failure in it.

### Scheduling and persistence

Schedules are hourly, daily or weekly, all in UTC, and each task holds its own timer so it can be
rescheduled independently.

**Runtime state is persisted; definitions are not.** The handler and schedule shape come from code
and are re-registered on every startup, while the last run, the failure state and the paused flag
live in config. A restart therefore preserves "when did this last run" and "the user paused this"
without the config ever holding a schedule the code disagrees with.

### Logs attach themselves

A handler on the root logger reads the active task from a context variable, so **task code needs no
logging awareness at all.** Anything logged anywhere inside a task's call stack, including deep
inside a provider, is attributed to that task and shown in the UI. Nothing outside a task is
captured.

The same approach gives task code a progress handle without threading the controller through every
call.

### Reports

A task can attach a Markdown report explaining what it did, which the UI renders. That is the right
shape for an outcome that is neither a percentage nor an error: playlist migration reports which
tracks matched exactly, which were approximated and which could not be found.

### Visibility and events

A caller holding the manage scope sees every task; anyone else sees only their own, so a non-admin
sees the playlist edit they started and nothing else.

Updates are emitted at two speeds: lifecycle changes are debounced briefly so they stay responsive,
while progress and log churn is throttled to a much longer interval. Without that, a sync reporting
per-track progress would flood every connected client.

See [controllers/tasks](../../music_assistant/controllers/tasks/README.md).

## Diagnostics

The diagnostics report answers "what went wrong" in a form **safe to paste into a public issue**.

Capture and assembly are deliberately separate:

| Where | Role |
|---|---|
| A standard-library-only helper with no package imports | Always-on capture, installable before the server object exists |
| The controller | On-demand assembly, sanitization and return |

That split is why capture can be installed as the very first thing at startup, before anything that
might fail, so a boot-time error still lands in the report. Its always-on cost is one handler doing
bounded in-memory appends, with no sanitization, formatting or I/O on that path.

There is **no HTTP download endpoint**. The report is an API command requiring the system manage
scope, with an optional log tail.

### What is captured, and what it costs

Two bounded structures at warning level and above: a ring of recent records, and exception
aggregates keyed by fingerprint with counts and timestamps.

The fingerprint is deliberately computed at **function granularity rather than line numbers**, so a
retry loop or a shifted line does not fragment one problem into many entries.

Keeping the handler cheap is why the traceback walk reads only the frame's code object and defers
every source read to report time. Capture is also wrapped so it can never raise, because capturing
diagnostics may not break logging itself.

### The report

Five sections: system facts including a sampled event loop lag measurement, an install census, the
aggregated exceptions, pluggable contributions, and optionally a log tail. Each is assembled
independently, so a failure becomes an error value in place rather than losing the whole report.

The census reports **which config keys differ from default, by name only and never by value**. The
report also carries its own note explaining what was redacted, so whoever reads it knows what the
placeholders mean.

Any controller or provider can contribute a section. Contributors are isolated: gathered
concurrently, bounded by a short timeout, and an exception becomes an error value for that section
alone. The intended shape is aggregate numbers rather than names or payloads.

### Sanitization is the point

Everything reaching the report is sanitized, including dictionary keys. Redactions cover code
paths, URL query strings and credentials, tokens, media paths and filenames, email addresses, MAC
addresses, IP addresses and home directories.

Two of those choices are worth understanding before changing them. **Media paths and MAC addresses
become stable hashes rather than blanks**, so the same value stays correlatable within one report
without revealing what it was. And **IP candidates are parsed rather than pattern-matched**, so a
timestamp is not mangled, while loopback addresses are kept deliberately because they are
diagnostically useful and not private.

See [controllers/diagnostics](../../music_assistant/controllers/diagnostics/README.md) for the full
list and the remaining rationale.

## Safe mode

If a provider is preventing startup, safe mode loads the core controllers and builtin providers
only, so the UI is reachable and the offending provider can be disabled before restarting normally.
See [Overview](overview.md).

## Related

- [Events and commands](events-and-commands.md) for the three kinds of task.
- [Discovery](discovery.md) for why a device is not appearing.
- [Configuration and persistence](configuration.md) for where settings and databases live.
- [The API and authentication](api-and-auth.md) for the scopes these commands require.
