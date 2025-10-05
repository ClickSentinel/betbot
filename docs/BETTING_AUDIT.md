# Betting Storage & Timer Audit

This document summarizes a focused audit of the betting system, findings about why bets and timers stopped showing, and a recommended plan to unify storage and restore correct behavior.

## Quick summary
- What I inspected: `_process_bet`, the `!bet` command (`place_bet`), `!mybet`, reaction handlers, `utils/live_message.py`, and a repo-wide search for `data["betting"]` and `BetState`.
- Key finding: the code currently uses two distinct bet storages:
  - Legacy single-session: `data["betting"]["bets"]` (many commands and `BetState` rely on this).
  - Multi-session: `data["betting_sessions"][session_id]["bets"]` (newer session-aware code paths).
- Consequence: Some flows write to the session-specific place while others read the legacy structure (or vice versa). This causes `!mybet`, `!bettinginfo`, and live embeds/timers to appear empty or out-of-sync.

## Recommendation (canonical storage)
Pick one canonical approach and adapt the rest. Recommended minimal-risk approach:

- Canonical storage: per-session model — `data["betting_sessions"][session_id]`.
- Implement a thin accessor layer (adapter functions) that provides a single API for reading/writing bets:
  - `get_bets(data, session_id=None)`
  - `set_bet(data, session_id, user_id, bet_info)` / `remove_bet(...)`
  - `find_session_for_contestant(...)` (reuse existing `find_session_by_contestant`)

Why this approach:
- Minimal call-site changes; many call sites only need to call a helper instead of directly changing storage logic.
- Keeps backwards compatibility in single-session mode (accessors map to legacy `data["betting"]`).

## Per-command audit (findings & required changes)
Below are critical commands / modules that touch bets or timers and what must change.

- `!bet` / `place_bet` (`cogs/betting.py`)
  - Problem: Mixed reads/writes to both storages. If `_process_bet` writes to sessions but `place_bet` reads legacy bets to compute `old_amount`, `mybet` will show nothing.
  - Change: Use the accessor for reading existing bets and for updates; ensure session context is passed to `_process_bet`.

- `_process_bet` (`cogs/betting.py`)
  - Problem: It currently has a multi-session branch writing `session["bets"]` and a legacy branch that calls `BetState` which writes `data["betting"]["bets"]`.
  - Change: Refactor to use accessors for writes. Optionally provide a session-aware BetState wrapper.

- Reaction handlers (in `cogs/betting.py`)
  - Problem: They may still update legacy storage when manual bets use session storage (or vice versa).
  - Change: Resolve `session_id` based on the live message and write via accessor with that session_id.

- `!mybet`
  - Problem: Reads `data["betting"]["bets"]` only.
  - Change: Use accessor. When multiple sessions are active, show per-session bets (or accept a session arg).

- `!bettinginfo` / `!debug`
  - Change: Enumerate `data["betting_sessions"]` and show bets using accessor; include contestant->session mapping and timer info.

- `utils/live_message.py`
  - Problem: Some code uses `betting_data = data["betting"]`.
  - Change: When `update_live_message` is called with a `session_id`, it must use that session's bets exclusively. When called without `session_id`, be explicit (update all sessions or legacy behavior).

- `bet_state.py` (utils/bet_state.py)
  - Problem: `BetState` operates on `data["betting"]` only.
  - Change: Add `SessionBetState` wrapper (or extend BetState) so existing logic can run against a session view.

- `betting_timer.py`
  - Problem: Uses legacy `data["betting"]` checks.
  - Change: Iterate active sessions and process timers per-session; when a session auto-closes, call the session-specific close flow.

- Helpers: `betting_utils.py`, `message_formatter.py`
  - Change: Accept optional `session_id` or a direct session dict; ensure message formatter accepts normalized contestant keys.

- `data_manager.py`
  - Change: Add accessor helpers and a lightweight migration helper to convert legacy `data["betting"]` into a session if `multi_session_mode` toggles are required.

## Concrete implementation plan (safe steps)
1. Add accessor helpers in `data_manager.py`:
   - `get_bets(data, session_id=None)`
   - `set_bet(data, session_id, user_id, bet_info)`
   - `remove_bet(data, session_id, user_id)`
2. Update `_process_bet` to use accessor helpers instead of direct dict access.
3. Update reaction handlers to resolve session_id from the live message and use accessors.
4. Create `SessionBetState` wrapper so `BetState` logic can be reused for sessions.
5. Update `!mybet`, `!bettinginfo`, live message updater, and timer logic to use the accessor.
6. Run tests and fix failures iteratively.

Order and safety: do the accessor and `_process_bet` refactor first (low-risk), then update BetState wrapper and callers.

## Contract (short)
- Inputs: `data`, optional `session_id`, `user_id`, `bet_info`.
- Outputs: direct dict reference for reads; True/False for writes and save_data on success.
- Errors: missing/invalid session, insufficient funds, or concurrent writes (handled via existing bot single-thread model).

## Edge cases
- Legacy vs multi-session toggle: recommended behavior is to auto-create a session from legacy `data["betting"]` when migrating, or provide an adapter view.
- Reactions on messages before session mapping exists: resolve session by `live_message_id`; otherwise ignore or fallback to legacy.
- Users changing bets across sessions: ensure old reaction bets are removed correctly using `contestant_to_session`.

## Tests to add / modify (minimum)
- Unit tests:
  - `test_accessor_get_set_remove`
  - `test_process_bet_session_writes`
  - `test_reaction_handler_session_writes`
  - `test_timer_embed_updates`
- Integration tests:
  - `!bet` then `!mybet` assert
  - Multi-session `!mybet` shows bets in each session
  - Backwards compatibility tests for single-session mode

## Files likely to be changed
- `betbot/data_manager.py` — add accessors and migration helper
- `betbot/cogs/betting.py` — `_process_bet`, reaction handlers, `place_bet`, `mybet`, `bettinginfo`
- `betbot/utils/bet_state.py` — add `SessionBetState` wrapper
- `betbot/utils/live_message.py` — ensure session-aware updates
- `betbot/utils/betting_timer.py` — iterate and handle session timers
- Tests under `betbot/tests/` — add/modify tests that assert on storage consistency

## Quality gates
- After each change: run pytest.
- Smoke test: create a short-timer session, place a bet via `_process_bet`, call `!mybet`, and assert timer info in `update_live_message` embed.

## Next steps I can take (if you approve)
1. Implement accessor helpers and refactor `_process_bet` to use them. Run tests.
2. Iterate on reaction handlers and `!mybet` if needed (running tests after each step).

Estimated time: 30–90 minutes depending on number of call-sites and test failures.

---

If you want me to proceed I will implement step 1 and step 2 now and run the test suite, then report the results and next edits.

## Work completed (2025-10-05)

- Implemented canonical accessor helpers in `betbot/data_manager.py`:
  - `get_bets(data, session_id=None)`
  - `set_bet(data, session_id, user_id, bet_info)`
  - `remove_bet(data, session_id, user_id)`

- Refactored `_process_bet` in `betbot/cogs/betting.py` to use the accessors for multi-session writes and to use accessor reads for legacy flows where appropriate. Changes include:
  - Multi-session branch now uses `get_bets`/`set_bet` to read/update session bets and persists via `set_bet`.
  - Legacy branch continues to use `BetState` (preserves existing refund/balance logic).
  - When placing a manual bet after a reaction bet, the old reaction removal flow remains and now uses accessors for consistency.

- Type-checking adjustments: imported `UserBet` TypedDict and cast the payload in `_process_bet` to satisfy static checks.

- Ran the full test suite after changes: `pytest` => 164 passed, 0 failed.

- Additional work (2025-10-05):
  - Updated reaction handlers in `betbot/cogs/betting.py` (`on_raw_reaction_add` and `on_raw_reaction_remove`) to be session-aware:
    - Reactions on session-specific live messages now resolve the `session_id` and store pending reaction entries with `session_id`.
    - Removal/add flows for reaction-based bets use the accessor API (`set_bet`/`remove_bet`) so reaction bets and manual `!bet` commands converge on the same canonical storage.
  - Added tests to cover accessor behavior and session `_process_bet` flows; iteratively fixed a fixture issue and re-ran the test suite until green.
  - Final test run after these edits: `pytest` => 166 passed, 0 failed.
  - Committed changes on branch `dev` with message: "bet: add accessor helpers, refactor _process_bet to use session-aware storage, add tests and update audit doc" (and additional doc updates committed in a follow-up commit).

  - SessionBetState and code-wide replacement (2025-10-05):
    - Implemented `SessionBetState` in `betbot/utils/bet_state.py`. It mirrors the `BetState` public API but operates on a session dict (the shape used in `data["betting_sessions"][session_id]`). It reuses the existing `Economy` logic, result calculation, and persistence (`save_data`).
    - Replaced session-aware uses of `BetState` with `SessionBetState` in `betbot/cogs/betting.py`:
      - Winner declaration path (`_process_winner_declaration`) now resolves a session for the provided contestant name and uses `SessionBetState` to calculate results and declare the winner for that session. Legacy single-session winner processing is preserved unchanged.
      - Session-specific bet placement flows (where a `session_id` is available) now use the accessor layer or `SessionBetState` as appropriate so refunds and balance validation use the same economy logic as legacy flows.
    - Ran the full test-suite after these edits: `pytest` => 165 passed, 1 skipped, 2 warnings. All tests pass.

    - Lint notes: a few type hint mismatches were addressed via casting where session dicts are dynamically typed; this maintains runtime compatibility while keeping the static checks reasonable.

    - Commit summary: implemented session wrapper and updated win/declare flows to be session-aware. Remaining call-sites of `BetState` that are intentionally legacy (e.g., top-level `self.bet_state`) were left to preserve single-session compatibility.

## Small follow-ups performed / validation

- Verified `utils/live_message.py` already supports `session_id` in `update_live_message` and normalizes contestant keys for the message formatter (no changes required there for now).
- Confirmed `schedule_live_message_update_for_session(session_id)` exists and is used in parts of the codebase; the scheduler will handle per-session updates when the identifier is a session id.

## Remaining recommended steps

1. Reaction handlers: update reaction-based bet handlers to resolve `session_id` from the reacted message (via `get_session_live_message_info`) and use `set_bet/remove_bet` so reaction and manual bets are stored in the same place.
2. `SessionBetState`: add a thin wrapper to `betbot/utils/bet_state.py` so existing BetState logic (refunds, balance updates) can be reused for session dicts, removing duplication.
3. Reporting commands: refactor `!mybet`, `!bettinginfo`, and `!debug` to use `get_bets` and show per-session results (or accept a session arg).
4. Timer code: update `betting_timer.py` to iterate `active_sessions` and process timers per-session (use existing `timer_config.auto_close_at` & `schedule_live_message_update_for_session`).
5. Tests: add tests for reaction->session bet flows and `!mybet` integration; add timer embed tests.

If you want me to continue I will next implement the Reaction handlers update (step 1) and run the test suite. I will update this document with each completed step.
