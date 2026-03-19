---
phase: 02-strategy-pipeline
plan: "00"
subsystem: testing
tags: [anthropic, pydantic, pytest, settings, strategy, scanner, claude]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Settings class (SecretStr fields), pytest infra, conftest.py, models.py
provides:
  - anthropic_api_key SecretStr field + claude_model + coin_whitelist on Settings
  - ANTHROPIC_API_KEY placeholder in .env.example with scanner config vars
  - test_settings fixture extended with anthropic_api_key
  - sample_criteria fixture for filter/manager tests
  - 19 RED-state test stubs across 4 test files (importorskip until production modules exist)
affects:
  - 02-01-PLAN (market scanner — test_scanner.py stubs)
  - 02-02-PLAN (claude engine — test_claude_engine.py stubs)
  - 02-03-PLAN (filter + manager — test_strategy_filter.py + test_strategy_manager.py stubs)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pytest.importorskip at module level for RED-state stubs — entire module skipped until production module exists"
    - "sample_criteria fixture as plain dict — avoids DB or ORM coupling in pure unit tests"

key-files:
  created:
    - tests/test_scanner.py
    - tests/test_claude_engine.py
    - tests/test_strategy_filter.py
    - tests/test_strategy_manager.py
  modified:
    - bot/config.py
    - .env.example
    - tests/conftest.py

key-decisions:
  - "pytest.importorskip at module level chosen to keep test code matching the production API surface — the entire module is skipped (not collected) until the production module exists, satisfying RED state requirement"
  - "anthropic_api_key placed immediately after database_url in Settings field order — groups all required secrets together before optional fields"
  - "coin_whitelist defaults to 15 hardcoded coins — overridable via COIN_WHITELIST env var per SettingsConfigDict config"

patterns-established:
  - "Wave 0 test scaffolding pattern: create test stubs with importorskip before building production modules"
  - "Scanner config fields (top_n_coins, min_volume_usdt, consecutive_empty_cycles_alert) co-located with coin_whitelist in Settings"

requirements-completed:
  - SCAN-01
  - SCAN-02
  - SCAN-03
  - SCAN-04
  - STRAT-01
  - STRAT-02
  - STRAT-03
  - STRAT-04
  - STRAT-05
  - FILT-01
  - FILT-02
  - FILT-03
  - FILT-04
  - FILT-05
  - LIFE-01
  - LIFE-02
  - LIFE-03
  - LIFE-04
  - LIFE-05

# Metrics
duration: 5min
completed: 2026-03-19
---

# Phase 2 Plan 00: Wave-0 Foundation Summary

**anthropic_api_key + claude_model + coin_whitelist added to Settings; 19 RED-state test stubs scaffolded across 4 files using pytest.importorskip for strategy pipeline Wave 1/2 plans**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-19T12:56:54Z
- **Completed:** 2026-03-19T13:01:54Z
- **Tasks:** 2
- **Files modified:** 7 (3 modified, 4 created)

## Accomplishments

- Added `anthropic_api_key: SecretStr`, `claude_model: str`, `coin_whitelist: list[str]`, and scanner config fields to Settings — bot now fails fast with a clear error if ANTHROPIC_API_KEY is missing
- Updated `.env.example` with ANTHROPIC_API_KEY, CLAUDE_MODEL, COIN_WHITELIST, TOP_N_COINS, MIN_VOLUME_USDT, CONSECUTIVE_EMPTY_CYCLES_ALERT placeholders
- Extended `test_settings` fixture with `anthropic_api_key=SecretStr("test_anthropic_key_abc123")` and added `sample_criteria` fixture
- Created 4 test files with 19 stubs in RED/skipped state — collectible and syntactically valid, blocked by absent production modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Add anthropic_api_key, claude_model, coin_whitelist to Settings + update fixtures** - `f2d4ab5` (feat)
2. **Task 2: Scaffold all 4 Wave-0 test files in RED state** - `ed2a11c` (test)

**Plan metadata:** (docs commit, next)

## Files Created/Modified

- `bot/config.py` - Added anthropic_api_key, claude_model, coin_whitelist, top_n_coins, min_volume_usdt, consecutive_empty_cycles_alert fields to Settings
- `.env.example` - Added Anthropic API and scanner config section
- `tests/conftest.py` - Extended test_settings with anthropic_api_key; added sample_criteria fixture
- `tests/test_scanner.py` - 5 RED stubs: SCAN-01, SCAN-02, SCAN-03, SCAN-04, STRAT-03
- `tests/test_claude_engine.py` - 3 RED stubs: STRAT-01, STRAT-02, STRAT-04
- `tests/test_strategy_filter.py` - 3 RED stubs: FILT-01, FILT-02, FILT-03
- `tests/test_strategy_manager.py` - 8 RED stubs: STRAT-05, FILT-04, FILT-05, LIFE-01..05

## Decisions Made

- `pytest.importorskip` at module level is the right pattern for RED-state stubs — it skips the whole module cleanly when the production module is absent, rather than failing with ImportError noise
- `anthropic_api_key` placed immediately after `database_url` to group all required SecretStr fields before optional fields

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- Settings now has all required Anthropic fields — 02-01 (scanner), 02-02 (claude engine), 02-03 (filter + manager) can all reference `settings.anthropic_api_key.get_secret_value()` immediately
- All 19 test stubs are in place; running each plan's implementation will flip its tests from skipped to green
- Existing Phase 1 tests (10 passing) remain unaffected

---
*Phase: 02-strategy-pipeline*
*Completed: 2026-03-19*
