---
name: Fix Pre-existing Doc Errors
overview: Fix 13 errors in 5 pre-existing documentation files where they contradict the architecture docs. In every case, the architecture docs were verified correct against the code.
todos:
  - id: fix-significant
    content: "Fix 4 significant factual errors: bcrypt→PBKDF2 in webserver README (4 occurrences), 30s→60s in streams README, 3 errors in spotify_connect ARCHITECTURE.md (events.py, stdout→pipe, credentials.json→stderr), current_media in sync_group README"
    status: pending
  - id: fix-omissions
    content: "Fix 5 omissions: join_codes table + GUEST role in webserver README, protocol priority in players README, elapsed_time in sync_group README, setup() guidance in DEVELOPMENT.md"
    status: pending
  - id: fix-minor
    content: "Fix 1 minor precision issue: identifier priority grouping in players README"
    status: pending
  - id: fix-precommit
    content: Run pre-commit to verify all changes pass
    status: pending
isProject: false
---

# Fix Pre-existing Documentation Errors

Cross-referencing all pre-existing docs against our architecture docs revealed 13 contradictions. In every case, the architecture docs are correct and the pre-existing docs contain the errors. This plan fixes the pre-existing docs to align with reality.

## No Issues Found in Architecture Docs

Our architecture docs (`docs/architecture/`) were correct in every case where they disagreed with a pre-existing doc. No changes to architecture docs are needed.

## Fixes to Pre-existing Docs

### Priority 1 -- Significant Factual Errors

**1. [controllers/webserver/README.md](music_assistant/controllers/webserver/README.md) -- "bcrypt" hashing (4 occurrences)**

The README says "bcrypt hashing" in 4 places. The code uses `hashlib.pbkdf2_hmac("sha256", ..., iterations=100000)` with `{user_id}:{server_id}` as the salt. There is no bcrypt import anywhere in the webserver code. Replace all 4 "bcrypt" references with "PBKDF2-HMAC SHA-256".

**2. [controllers/streams/README.md](music_assistant/controllers/streams/README.md) line 90 -- Buffer pre-fill timing**

Says "~30s before track end". The code uses `duration - 60`. Change to "~60s".

**3. [providers/spotify_connect/ARCHITECTURE.md](music_assistant/providers/spotify_connect/ARCHITECTURE.md) -- events.py description**

Three errors in this file:
- Says events.py is a "Webservice" that "Runs on a custom port for each provider instance". In reality, events.py is a standalone Python script invoked via librespot's `--onevent` flag. It reads event data from environment variables and POSTs to the provider's endpoint on the shared streams server (port 8097). Fix the description and diagram.
- Says librespot "Outputs raw PCM audio to stdout (piped to ffmpeg)". In reality, librespot uses `--backend pipe --device /tmp/{instance_id}` (a named pipe). Fix to say "named pipe".
- Says "The provider reads `credentials.json` to extract the logged-in username". In reality, the username is parsed from librespot's stderr line `"Authenticated as 'username'"`. Fix the description.

**4. [providers/sync_group/README.md](music_assistant/providers/sync_group/README.md) line 296 -- current_media source**

The state properties table says `current_media` source is "Stored on group itself". The code's `current_media` property always delegates to `self.sync_leader.current_media`. Fix the table.

### Priority 2 -- Missing Information / Omissions

**5. [controllers/webserver/README.md](music_assistant/controllers/webserver/README.md) -- Missing `join_codes` table**

Database schema lists 4 tables but omits `join_codes`. Add it (used by the Party plugin for QR/link-based login).

**6. [controllers/webserver/README.md](music_assistant/controllers/webserver/README.md) -- Missing GUEST role**

Lists only ADMIN and USER roles. Add GUEST (used by the Party plugin).

**7. [controllers/players/README.md](music_assistant/controllers/players/README.md) line 181 -- Incomplete protocol priority**

Output protocol selection lists only "AirPlay > Chromecast > DLNA". The actual `PROTOCOL_PRIORITY` dict has 5 entries: airplay=10, squeezelite=20, chromecast=30, sendspin=40, dlna=50. Add the missing entries.

**8. [providers/sync_group/README.md](music_assistant/providers/sync_group/README.md) line 294 -- elapsed_time incomplete**

Says `elapsed_time` comes from "Sync leader". Should note it can also come from the sync leader's active output protocol player (when the leader uses a non-native protocol like AirPlay).

**9. [DEVELOPMENT.md](DEVELOPMENT.md) lines 76-77 -- Misleading setup() guidance**

Tells developers "The `setup()` function is called by Music Assistant upon initialization of the provider. It gives you the opportunity to prepare the provider for usage. For example, logging in a user or obtaining a token can be done in this function." This is misleading -- `setup()` should just create and return the provider instance. Heavy async initialization (login, token acquisition, daemon startup) belongs in `handle_async_init()`. Add a note clarifying the lifecycle phases.

### Priority 3 -- Minor Precision Issues

**10. [controllers/players/README.md](music_assistant/controllers/players/README.md) line 164 -- Identifier priority grouping**

Groups CAST_UUID and AIRPLAY_ID at the same priority tier (#4). The code iterates them as separate entries (CAST_UUID then AIRPLAY_ID). Minor -- rarely matters in practice but could be more precise.
