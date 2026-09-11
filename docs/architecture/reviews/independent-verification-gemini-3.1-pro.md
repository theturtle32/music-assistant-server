# Architecture Verification Report

**Reviewer:** Gemini 3.1 Pro
**Date:** July 31, 2026
**Scope:** `docs/architecture/*.md` (excluding `plans/` directory) against codebase in `music_assistant/` and `music_assistant_models`.
**Methodology:** Independent, parallel, code-driven verification within an isolated worktree.

---

## 1. Core, Events, Configuration, Provider Lifecycle, Discovery
*(docs 00, 01, 02, 13, 15)*

### Verified Accuracies
The documentation for this domain is exceptionally accurate, matching the codebase perfectly across all complex mechanisms:
*   **Event System Dispatch:** The docs correctly claim `signal_event` enforces thread safety via `verify_event_loop_thread` and uses `call_soon` (not `call_soon_threadsafe`), while `subscribe` precomputes `is_coro`. (`music_assistant/mass.py:590-631`)
*   **Config Atomic Save:** `_save_to_disk` rotates the existing file to `.backup` *only* if the temp file parses as JSON, exactly as documented. (`music_assistant/controllers/config/controller.py:291-301`)
*   **Discovery mDNS:** `async_find_mdns_service` clears its event *before* scanning the cache to prevent race conditions, and correctly strips `RAOP_MAC_PREFIX` for name matching. (`music_assistant/controllers/discovery/controller.py:169-182`)
*   **Provider Config:** The docs correctly describe the seeding, setup, rehydration, and validation flow for provider loading, as well as the auto-removal of under-specced default providers. (`music_assistant/mass.py:1194-1210`, `861-875`)

### Inaccuracies and Missing Context
*   **None.**

---

## 2. Player Model, Controller, Protocol Linking, Grouping, Volume
*(docs 03, 04, 05, 06, 07)*

### Verified Accuracies
The documentation captures complex state machines and fallback chains with high fidelity:
*   **`__final_playback_state` Override:** Correctly incorporates an upstream-clock override for active queue items of type `AudioSource`. (`music_assistant/models/player.py:2322-2362`)
*   **Mute Lock Fallback:** The controller correctly guards group volume changes from auto-unmuting players, falling back to check the parent player's mute lock for protocol players. (`music_assistant/controllers/players/controller.py:3806-3810`)
*   **Power Control Degradation:** Accurately reflects how power control degrades (`NATIVE` to `NONE`) if features drop, keeping the delegate-protocol code path unreachable. (`music_assistant/models/player.py:1320-1323`)
*   **Group Volume Interpolation:** The linear interpolation algorithm for group volume changes works exactly as described. (`music_assistant/controllers/players/controller.py:2077-2084`)

### Inaccuracies and Stale Info
*   **Location of `MEDIA_IDENTITY_KEYS` (Minor, Stale, High Confidence):** `03-player-model.md` implies this constant is in `constants.py`, but it was moved to `music_assistant/models/player.py:53-64`.

### Missing Cross-Cutting Context
*   **Unused Parameter in Protocol Linking (Minor, Missing, High Confidence):** `05-protocol-linking.md` omits that `_identifiers_match()` (`music_assistant/controllers/players/protocol_linking.py:1572`) accepts a `protocol_domain` parameter that is completely unused in the method, though the same-domain exclusion claim itself remains behaviorally true.

---

## 3. Media Library, Player Queues, Metadata
*(docs 08, 09, 14)*

### Verified Accuracies
The documentation is exceptionally accurate and up-to-date:
*   **FTS5 Trigram Indexing:** `search_name_match_clause` uses a trigram-tokenized FTS5 index for terms >= 3 characters, falling back to `LIKE` for shorter terms. (`music_assistant/controllers/music/helpers.py:23-38`)
*   **Event Suppression:** `SUPPRESS_MEDIA_ITEM_UPDATES` is a `ContextVar` used to suppress per-item events during bulk operations. (`music_assistant/controllers/music/media/base.py:92-93`)
*   **PlayerQueueData:** Correctly described as the server-side record holding the wire `queue` plus runtime fields. (`music_assistant/controllers/player_queues/state.py:15-38`)
*   **Play Action Decorator:** `@handle_play_action` correctly acquires the shared playback lock and sets `ATTR_PLAY_ACTION_IN_PROGRESS`. (`music_assistant/controllers/player_queues/helpers.py:102-117`)
*   **Metadata Priorities:** Fanart.tv (10), TheAudioDB (20), Wikipedia (25), iTunes Artwork (30), MB/LRCLIB/Genius (50), playlist_metadata (90) are all correct.

### Inaccuracies and Missing Context
*   **None.**

---

## 4. Streaming Pipeline, Audio Analysis, Smart Fades
*(docs 10, 16, 17)*

### Verified Accuracies
No inaccuracies, stale information, or broken claims were found.
*   **AudioSource Bypass & Pacing:** The fast/slow paths, use of `realtime_pcm_pacer`, and lack of `audio_source_silence_keepalive` are exactly right. `-re` injection is correct. (`music_assistant/controllers/streams/audio.py:2854`, `528`)
*   **Smart Fades Planning:** Accurate representation of candidate generation, evaluation without short-circuiting, and DJ-style band EQ assembly. (`music_assistant/controllers/streams/smart_fades/planner/assembly.py:472`)
*   **Vocal Awareness Fallback:** `_build_smart_crossfade` correctly returns the outgoing `fade_out_analysis` row to `StandardCrossFade` upon failure to prevent clipping. (`music_assistant/controllers/streams/smart_fades/mixer.py:182`)
*   **Bit-perfect Tracking:** `AudioProcessingManager` bit-perfect checks (`channels`, `bit_depth`, `sample_rate`) match the narrative exactly.
*   **DB Migrations:** `DB_TABLE_LOUDNESS_MEASUREMENTS` correctly verified dropping at schema v39.

### Inaccuracies and Missing Context
*   **None.**

---

## 5. Plugin System, AI and MCP
*(docs 11, 18)*

### Verified Accuracies
Captures recent architectural shifts perfectly:
*   **`AudioSource` Replacement:** `PluginSource` is correctly replaced by the queue-scoped `AudioSource` with dynamic capability flags. (`music_assistant/providers/yandex_ynison/provider.py:1717-1725`)
*   **Spotify Connect Migration:** Correctly reflects the `go-librespot` migration, utilizing `StreamType.CUSTOM` and abandoning the named pipe. (`music_assistant/providers/spotify_connect/__init__.py:278-283`)
*   **FastMCP Security:** `MASTokenVerifier` performs the audience check *before* calling the MA token authenticator, and debug flags are off by default. (`music_assistant/providers/fastmcp_server/auth.py:111-120`)
*   **Music Quiz Constraints:** Strict 8KiB prompt / 4KiB response boundaries are exactly defined. (`music_assistant/providers/music_quiz/quiz_types/trivia.py:37-38`)

### Inaccuracies and Stale Info
*   **None.**

### Missing Cross-Cutting Context
*   **`SOUND_EFFECT` Bypass (Minor, Missing, High Confidence):** While the docs note `get_item_by_uri` skips the library-existence check for `AUDIO_SOURCE` and `SOUND_EFFECT`, they omit that `get_item` handles this natively for both, bypassing standard plugin logic to directly call `prov.get_sound_effect(item_id)` on `MusicProvider`s. (`music_assistant/controllers/music/controller.py:968-976`)
*   **AI Radio `NotConnected` Handling (Minor, Missing, High Confidence):** The docs state that AI Radio fails the station run on text generation failure, but omit the specific UX handling where `_generate_text` intercepts `NotConnected` exceptions to prompt the user to manually reconnect the underlying HA provider. (`music_assistant/providers/ai_radio/runtime.py:1549-1554`)

---

## 6. Webserver API, Authentication, Background Tasks, Localization
*(docs 12, 19, 20, 21)*

### Verified Accuracies
*   **API Command Retry:** `APICommandHandler.parse` correctly resolves forward references with up to 32 retries. (`music_assistant/helpers/api.py:146-160`)
*   **Impersonation Guard:** The dispatch throws a `RuntimeError` at startup if a handler takes its own `user` argument while allowing impersonation. (`music_assistant/helpers/api.py:367-369`)
*   **Ingress Verification:** `is_request_from_ingress` correctly reads `request.transport.get_extra_info("sockname")` instead of trusting headers. (`music_assistant/controllers/webserver/helpers/auth_middleware.py:358-362`)
*   **Task Log Capture:** `TaskLogHandler` successfully intercepts root logger emissions and attributes them to the active task via `ACTIVE_TASK_ID`. (`music_assistant/controllers/tasks/helpers.py:386-393`)

### Inaccuracies and Stale Info
*   **Unused `auth_middleware` (Critical, Wrong/Dead Code, High Confidence):** `12-webserver-api.md` claims that `auth_middleware` manages authentication for HTTP routes by caching user state, observing a prefix allowlist, and leaving the final authorization check to a `require_authentication()` helper. **This is completely false.** `auth_middleware` and `require_authentication` exist but are never attached to the `web.Application` pipeline in `Webserver.setup`. Real non-API HTTP authentication is entirely isolated and handler-local.

---

## Cross-Document Coherence
Overall, terminology and mechanisms are highly coherent across the document corpus. The separation of concerns between domains (e.g., how the streaming pipeline interacts with player queues) is clearly defined and consistent. The only significant referential gap relates to the `auth_middleware` dead code which impacts claims made in both `12-webserver-api.md` and implicitly `19-authentication.md`.
