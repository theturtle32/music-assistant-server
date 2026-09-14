# Diagnostics controller

Answers "what went wrong" with a single report designed to be **safe to paste into a public GitHub
issue**.

## Capture and assembly are separate

That split is the central design decision.

| Where | Role |
|---|---|
| [helpers/diagnostics.py](../../helpers/diagnostics.py) | Always-on capture. Standard library only, with no imports from this package, so it can be installed before the server object exists |
| This package | On-demand assembly. Builds, sanitizes and returns the report only when asked |

Installing the capture handler is idempotent and attaches a single handler to the root logger. The
entry point installs it as early as possible, and this controller adopts whatever is already there
or installs it itself for embedded use.

The always-on cost is one handler doing bounded in-memory appends. No sanitization, no formatting,
no I/O.

There is deliberately **no HTTP download endpoint.** The report is an API command requiring the
system manage scope, with an optional log tail. The download route that originally accompanied it
was removed.

## What capture keeps

Two bounded structures, at warning level and above: a ring of recent records with truncated
messages, and exception aggregates keyed by fingerprint with a count and first and last seen
timestamps.

The fingerprint is a hash of the exception type, the raise site and the topmost in-package frame,
deliberately at **function granularity rather than line numbers**, so a retry loop or a slightly
shifted line does not fragment into many entries.

Keeping this cheap is why the traceback walk reads only the frame's code object, with no source
file reads at all, deferring every source lookup to report time. The aggregate map evicts least
recently used entries.

Capture is wrapped so that it can never raise. Capturing diagnostics may not break logging itself.

## Report structure

Five top-level sections, each assembled independently so a failure becomes an error value in place
rather than losing the whole report.

| Section | Contents |
|---|---|
| System | Version, Python, platform, add-on and safe-mode flags, uptime, a sampled event loop lag measurement, memory, disk free, and counts of threads, tasks, timers, subscribers and clients |
| Install | A census: providers with load state, player counts by provider and type, library counts per media type, and which core config keys differ from default, **key names only, never values** |
| Exceptions | The aggregated exceptions, most recent first, with rendered tracebacks |
| Sections | Pluggable contributions |
| Log tail | Only when asked for |

The report carries its own note explaining what was redacted, so a maintainer reading it knows what
the placeholders mean, plus a schema version and a generation timestamp.

Disk and memory probing and traceback rendering are both pushed off the event loop, the latter
because rendering reads source files.

## Pluggable sections

Any core controller or provider can contribute by overriding the diagnostics hook, and external
code can register a named callback.

Contributors that have not overridden the hook are skipped by identity comparison rather than by
calling and discarding, so the base no-op never appears as an empty section.

Each contributor is isolated: gathered concurrently, bounded by a short timeout, and any exception
becomes an error value for that section alone. Both sync and async callbacks are accepted. The
result is round-tripped through JSON to normalize and validate it, then sanitized in depth.

The tasks controller's contribution is a good model for the intended shape: totals, counts by
status, queue depth and the concurrency limit. Aggregate numbers, no names and no payloads.

## Sanitization

Every string reaching the report is sanitized, and structures have their **keys** sanitized as well
as their values. Redactions cover absolute code paths, URL query strings and userinfo, tokens and
secret assignments, media paths and bare media filenames, email addresses, MAC addresses, IP
addresses and home directories.

Several choices there are deliberate and worth understanding before changing them.

**Hashes, not blanks, for media paths and MAC addresses.** A stable short hash keeps the same value
correlatable within one report, so you can still see that one file failed twelve times or that two
log lines concern one device, without revealing what either was.

**IP candidates are parsed, not just pattern-matched.** A candidate that does not parse as an
address is left alone, which stops timestamps and MAC lookalikes from being mangled. Loopback and
unspecified addresses are kept on purpose, since they are diagnostically useful and not private.
IPv6 is matched before IPv4 so a mapped address is redacted whole.

**The long-token heuristic requires a digit.** A long run of token characters only counts as a
secret if it contains at least one digit, which is a cheap way to spare long identifiers and dotted
module paths from being redacted as credentials.

**Media filename redaction is deliberately greedy.** A bare filename can contain spaces, so
unquoted prose immediately preceding one is redacted along with it. Privacy beats message fidelity
here.

## Related architecture docs

- [Operations](../../../docs/architecture/operations.md) for debugging a running server.
- [API and auth](../../../docs/architecture/api-and-auth.md) for the scope this command requires.
