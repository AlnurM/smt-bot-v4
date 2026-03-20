---
phase: 06-reporting-and-audit
plan: "02"
subsystem: reporting
tags: [pine-script, tradingview, alembic, postgresql, jsonb, aiogram, tdd]

# Dependency graph
requires:
  - phase: 06-01
    provides: signal generation pipeline with zones dict from SMC detection
  - phase: 04-telegram-interface
    provides: CallbackQuery handlers pattern, SignalAction callback data factory
  - phase: 03-signal-and-risk
    provides: OrderBlock, FairValueGap, StructureLevel dataclasses from smc.py
provides:
  - Alembic migration 0005 adding zones_data JSONB column to signals table
  - generate_pine_script() pure function in bot/reporting/pine_script.py
  - Signal.zones_data ORM column for Pine Script zone reconstruction
  - handle_pine callback — delivers .txt Pine Script file via answer_document
  - cmd_chart command — queries latest Signal for symbol, delivers .txt file
  - zones_data persistence in run_strategy_scan via _zones_to_json_safe
affects:
  - 06-03-audit (may query zones_data for audit reporting)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Pure generator function — generate_pine_script() takes explicit params, returns string (no DB, no network)
    - _zones_to_json_safe() normalises both dataclass instances and plain dicts — handles generator and DB paths
    - Lazy import pattern for pine_script module inside handlers — consistent with Phase 3/4 established patterns
    - answer_document() with BufferedInputFile for .txt delivery — same pattern as chart PNG delivery

key-files:
  created:
    - alembic/versions/0005_add_signal_zones_data.py
    - bot/reporting/__init__.py
    - bot/reporting/pine_script.py
    - tests/test_pine_script.py
  modified:
    - bot/db/models.py
    - bot/telegram/handlers/callbacks.py
    - bot/telegram/handlers/commands.py
    - bot/strategy/manager.py
    - tests/test_telegram_callbacks.py

key-decisions:
  - "generate_pine_script() accepts individual params not a Signal ORM object — pure function, no DB dependency, fully testable"
  - "_zones_to_json_safe() uses hasattr(__dataclass_fields__) duck-typing — handles both dataclass instances (from generator) and plain dicts (from DB JSONB)"
  - "Zones capped at 5 per type in Pine Script output — Pine editor performance degrades with too many box/line objects"
  - "test_pine_callback_sends_placeholder test updated to match real implementation (sends document, not plain text)"

patterns-established:
  - "Pine Script delivery pattern: generate string → encode UTF-8 → BufferedInputFile → answer_document with caption"
  - "zones_data persistence: _zones_to_json_safe called inline in manager.py before session.commit()"

requirements-completed: [PINE-01, PINE-02, PINE-03]

# Metrics
duration: 5min
completed: 2026-03-20
---

# Phase 6 Plan 02: Pine Script Generation Summary

**Pine Script v5 generator delivering hardcoded TradingView overlay files (OBs, FVGs, BOS/CHOCH, MACD, RSI) via button callback and /chart command, with JSONB zone persistence in signals table**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-20T07:43:01Z
- **Completed:** 2026-03-20T07:47:41Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Alembic migration 0005 adds `zones_data JSONB` to signals table; `Signal.zones_data` ORM column added
- `generate_pine_script()` pure function (28 tests, all green) produces Pine Script v5 with OB boxes, FVG dashed boxes, BOS/CHOCH lines, entry arrow, MACD+RSI panels — all values hardcoded
- `handle_pine` callback replaced (was placeholder) — queries DB, calls generator, sends `.txt` via `answer_document`
- `cmd_chart` command replaced (was placeholder) — queries latest Signal for symbol, delivers `.txt` file
- `run_strategy_scan` persists `zones_data` using `_zones_to_json_safe` before `session.commit()`

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration + Signal.zones_data ORM column** - `d6ba6fd` (feat)
2. **Task 2: Implement generate_pine_script() with TDD** - `1ca2c00` (feat + test)
3. **Task 3: Wire handle_pine, cmd_chart, zones_data persistence** - `94d8097` (feat)

**Plan metadata:** (docs commit — see final_commit step)

_Note: Task 2 used TDD — test file committed together with implementation (all 28 tests pass GREEN)_

## Files Created/Modified

- `alembic/versions/0005_add_signal_zones_data.py` - Migration adding zones_data JSONB to signals
- `bot/reporting/__init__.py` - New reporting package
- `bot/reporting/pine_script.py` - generate_pine_script() pure function + _zones_to_json_safe() helper
- `bot/db/models.py` - Signal.zones_data Mapped[Optional[dict]] JSONB column added after caption
- `bot/telegram/handlers/callbacks.py` - handle_pine replaced with real DB query + document delivery
- `bot/telegram/handlers/commands.py` - cmd_chart replaced with real Signal query + document delivery
- `bot/strategy/manager.py` - zones_data persisted via _zones_to_json_safe before session.commit()
- `tests/test_pine_script.py` - 28 tests covering all behavior spec items
- `tests/test_telegram_callbacks.py` - Updated pine test to match real implementation (document, not text)

## Decisions Made

- `generate_pine_script()` accepts individual params (not Signal ORM) — pure function with no DB dependency, fully unit-testable without async fixtures
- `_zones_to_json_safe()` uses `hasattr(__dataclass_fields__)` duck-typing — handles both dataclass instances from the generator and plain dicts from DB JSONB transparently
- Zones capped at 5 per type in Pine Script output — Pine editor performance degrades with many box/line objects
- `test_pine_callback_sends_placeholder` test updated (Rule 1 — existing test was testing deprecated behavior)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_pine_callback_sends_placeholder to match real implementation**
- **Found during:** Task 3 (wiring handle_pine)
- **Issue:** Existing test `test_pine_callback_sends_placeholder` tested placeholder text delivery (callback.message.answer). New implementation uses answer_document — test would fail permanently on the replaced behavior.
- **Fix:** Updated test to `test_pine_callback_sends_document` — mocks `answer_document`, asserts it's called, checks caption contains symbol. Added `test_pine_callback_signal_not_found` for the None path.
- **Files modified:** tests/test_telegram_callbacks.py
- **Verification:** 5 callback tests pass (was 4 previously failing with 1 error)
- **Committed in:** `94d8097` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — existing test testing replaced behavior)
**Impact on plan:** Required fix — test was testing deliberately deleted placeholder code. No scope creep.

## Issues Encountered

- `python` command not in PATH (macOS), used `.venv/bin/python` for all verification — consistent with project's venv setup
- `bot/reporting/` directory did not exist — created package with `__init__.py` (Rule 3 fix, inline)

## User Setup Required

None - no external service configuration required. The Alembic migration `0005_add_signal_zones_data.py` must be run (`alembic upgrade head`) when deploying to a live DB.

## Next Phase Readiness

- Pine Script delivery is complete end-to-end: generation, persistence, delivery via button and command
- Trader can now cross-check any signal on TradingView by pasting the generated Pine Script
- Phase 6 Plan 03 (audit/reporting) can query `zones_data` from Signal rows if needed

---
*Phase: 06-reporting-and-audit*
*Completed: 2026-03-20*
