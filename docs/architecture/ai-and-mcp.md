# AI and MCP

AI appears in three architecturally distinct places, and conflating them makes all three harder to
reason about.

1. **The server consuming a model**, through a provider feature. A plugin implements the hook and
   other components call it.
2. **The server orchestrating AI-driven experiences**, such as generating spoken radio segments or
   quiz wording.
3. **The server being exposed to external agents**, by publishing itself as a Model Context
   Protocol server.

The first two share one contract and are covered together. The third is the inverse direction.

## There is no AI subsystem

There is no AI controller, no cross-cutting AI state, no shared prompt builder and no shared retry
policy. AI is not a subsystem; it is a request-and-response capability that some plugin happens to
offer, exactly like lyrics lookup or image resolution, and it stays modelled as a provider feature.

Two hooks exist: one takes a string and returns a string, and one takes a message and returns
stream details for synthesized speech.

**Those contracts are deliberately thin.** There is no message-role structure, no system prompt
parameter, no conversation history, no token budget, no streaming, no tool calling and no
structured-output request. A consumer that wants JSON asks for JSON in the prompt and validates the
reply itself.

Speech returns stream details rather than bytes or a URL, which lets a cloud backend answer with a
URL and a local synthesizer answer with a file it just wrote, with neither the core nor the caller
caring which.

## The unit of choice is an engine

What *did* get factored out is which backend answers. One plugin can expose several backends: a
bridge exposes one per matching entity, an API-backed plugin one per configured model. Treating the
plugin as the choice would make half the available backends unreachable.

So discovery, selection and the config picker are shared, and an engine carries a
provider-scoped id plus a globally unique one that config stores. Engines are server-side only and
never serialized to clients.

**One rule is repeated in every docstring: another engine is never substituted for a missing one.**
An unset selection auto-adopts the first available engine, but a selection the user made explicitly
is either honoured or reported as missing. Silently falling back would send a prompt to a different
model, with different cost, latency and output, while the UI still showed the original choice.

Auto-adoption is why engine ordering has to be stable: it must resolve to the same engine across
restarts.

## What a consumer cannot assume

**Not availability.** The feature set is computed per provider and changes at runtime. The reference
backend adds and removes both flags whenever it re-resolves its entities, so every call site has to
handle the empty case, and *how* is the main thing that varies between consumers.

**Not latency.** A call can reach a cloud model. The base contract has no timeout, so a consumer
that cares imposes its own.

**Not well-formedness, or even honesty.** The return type is a string. Any structure inside it is a
convention between the prompt and the parser, and the model may violate it.

**Not idempotence or determinism.** Two identical prompts can return different text, and nothing
caches results.

It *can* assume the call is authenticated and configured, because the backend plugin owns
credentials and endpoint config. A consumer never sees an API key.

The in-tree consumers differ in exactly the places the shared layer does not cover: their prompt,
their timeout, and what happens on failure. Timeouts scale with how long a user is waiting, from
tens of seconds for an interactive quiz round up to minutes for a long background station run. Some
consumers degrade silently to a non-AI path; others fail the whole operation.

## Grounding: the server owns the facts, the model owns the phrasing

The most interesting pattern here is how the quiz uses a model without trusting it, and it is worth
studying as the default posture for any future consumer, because the hook returns an unconstrained
string and the only protection available is what the caller builds.

**The server selects the facts; the model only phrases them.** For a trivia round the server picks
the track, the question target and the correct answer from real library metadata, and the model is
asked to word a question and invent plausible wrong answers. It never chooses what is true.

Prompt-side defences bound the input: an oversized prompt is never sent, and untrusted metadata
values are truncated individually. The trivia prompt goes further and treats metadata as a
**prompt-injection vector**, fencing the payload between explicit markers with an instruction that
text inside the block is untrusted data rather than instructions, and declaring the correct answer
immutable and not to be returned at all.

Response-side validation rejects an oversized reply and requires JSON with an **exact** key set
rather than a superset. Answers are length-bounded, single-line, and checked not to contain the
correct answer. The distractor path requires the returned ranking to be a **complete permutation**
of the server's own candidates, so the model may reorder but cannot add, drop or invent one.

Even a valid response is not used verbatim: answers are de-duplicated and any shortfall is
back-filled from other grounded facts, so a model that returns three near-identical wrong answers
still yields a playable round.

## Speech and announcements

Announcements accept text as well as a URL, so the server does not depend on something upstream
having synthesized audio first. Given text it resolves an engine, renders the clip **up front**, and
proceeds exactly as with a supplied URL.

Rendering before the group fan-out is what stops every member of a group re-speaking the same
sentence.

Two pieces of shared plumbing are worth knowing. A language fallback retries **without** the
requested language when an engine rejects it, because a voice that cannot speak one locale should
still say something rather than fail. And the returned stream details are validated into a path and
a stream type, so a URL, a local file and anything invalid are told apart with an error naming the
offending engine.

## The MCP server inverts the direction

Instead of calling a model, the server publishes itself as an MCP server so external agents can
drive it.

**The constraint that shapes everything is that there is no second server.** The runtime mounts
into the existing webserver under a configurable path: no extra process, no extra port, no changes
to core.

Its tool surface is namespaced by area, covering the library, queues, playback, players, playlists,
media, metadata, debugging and configuration. Responses are purpose-built brief shapes rather than
this project's wire models, because tool output has to be small enough to be worth a model's
context budget.

Visibility is **operator-driven rather than scope-driven**. Every tool is tagged, each tag maps to a
config boolean, and disabling one makes the tools vanish from listings entirely, with no error path
and no permission-denied trace for the model to reason about. Debug and config tools are off by
default.

Authentication, when enabled, delegates to the server's own, and the plugin implements no token
decoding of its own beyond one claim it must check first for ordering reasons.

See [providers/fastmcp_server](../../music_assistant/providers/fastmcp_server/README.md) and its
[permissions deep dive](../../music_assistant/providers/fastmcp_server/permissions.md).

## Related

- [plugins.md](plugins.md) for the plugin provider model these hooks live on.
- [providers/ai_radio](../../music_assistant/providers/ai_radio/README.md) for the orchestrator.
- [providers/music_quiz](../../music_assistant/providers/music_quiz/README.md) for the grounded
  consumer.
- [providers/smart_playlist](../../music_assistant/providers/smart_playlist/README.md) for AI as an
  optional garnish.
- [players.md](players.md) for the announcement flow.
- [api-and-auth.md](api-and-auth.md) for tokens and scopes.
