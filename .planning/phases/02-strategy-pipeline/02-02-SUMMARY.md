---
phase: 02-strategy-pipeline
plan: "02"
subsystem: ai
tags: [anthropic, claude, pydantic, files-api, code-execution, strategy, walk-forward]

# Dependency graph
requires:
  - phase: 02-strategy-pipeline/02-00
    provides: "Wave-0 test stubs for claude_engine, anthropic_api_key in Settings, strategy criteria fields"
provides:
  - "bot/strategy/claude_engine.py: generate_strategy, _build_prompt, StrategySchema, ClaudeTimeoutError, StrategySchemaError"
  - "bot/strategy/__init__.py: package marker"
  - "Pydantic schema (StrategySchema) for full strategy dict validation with extra='ignore'"
  - "Walk-forward prompt builder with 70/30 split and all 6 criteria thresholds embedded"
  - "Files API upload/delete lifecycle via client.beta with betas=['files-api-2025-04-14']"
  - "Single retry on StrategySchemaError; always deletes file in finally block"
affects: [02-03-strategy-manager, 02-04-strategy-filter, signal-generator]

# Tech tracking
tech-stack:
  added:
    - anthropic==0.86.0 (AsyncAnthropic client with Files API beta)
    - pandas==3.0.1 (OHLCV DataFrame to CSV serialization)
  patterns:
    - "Files API lifecycle: upload before message, delete in finally — never leak files on error"
    - "Model string pinned explicitly: claude-sonnet-4-20250514 — never use alias or latest"
    - "beta.messages.create with betas=['files-api-2025-04-14'] when using container_upload blocks"
    - "StrategySchema.model_config = {'extra': 'ignore'} — unknown fields from Claude silently dropped"
    - "Single retry pattern: fresh API call on StrategySchemaError, no multi-turn"

key-files:
  created:
    - bot/strategy/__init__.py
    - bot/strategy/claude_engine.py
  modified:
    - requirements.txt (added anthropic==0.86.0, pandas==3.0.1)

key-decisions:
  - "model_config extra='ignore' on StrategySchema — Claude may return extra fields during prompt engineering iteration; silently drop rather than reject"
  - "Single retry with fresh API call on StrategySchemaError — no multi-turn conversation, avoids confusing Claude with partial bad output"
  - "anthropic and pandas added to requirements.txt — missing dependencies caught as Rule 2 deviation"
  - "asyncio.timeout() used (Python 3.11+) instead of asyncio.wait_for() — aligns with project requires-python >=3.12"

patterns-established:
  - "Pattern 1: Files API lifecycle — always upload → use → delete(finally) in single async function scope"
  - "Pattern 2: Typed exceptions for Claude errors — ClaudeTimeoutError, ClaudeRateLimitError, StrategySchemaError allow Strategy Manager to route failures cleanly"
  - "Pattern 3: Walk-forward prompt structure — WALK-FORWARD VALIDATION heading, 70/30 split, validation metrics as authoritative result"

requirements-completed: [STRAT-01, STRAT-02, STRAT-04]

# Metrics
duration: 4min
completed: 2026-03-19
---

# Phase 02 Plan 02: Claude Strategy Engine Summary

**Async Claude strategy engine using Files API CSV upload and code_execution tool with Pydantic schema validation and 70/30 walk-forward backtesting prompt**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-19T13:04:46Z
- **Completed:** 2026-03-19T13:09:03Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Implemented `generate_strategy` async function: uploads OHLCV CSV via Files API (beta.files.upload), calls beta.messages.create with model `claude-sonnet-4-20250514`, betas `files-api-2025-04-14`, tool `code_execution_20250825`, and always deletes file in finally block
- Implemented `StrategySchema` Pydantic model mirroring idea.md section 6.2 with nested MACDParams, RSIParams, SMCParams, EntryConditions, ExitRules, BacktestResults and `extra='ignore'` for Claude output tolerance
- Implemented `_build_prompt` with explicit WALK-FORWARD VALIDATION section, 70/30 train/validation split, 0.6 rejection threshold, and all 6 strategy criteria thresholds embedded
- Defined three typed exceptions: `ClaudeTimeoutError`, `ClaudeRateLimitError`, `StrategySchemaError` for precise error routing in Strategy Manager

## Task Commits

Each task was committed atomically:

1. **Task 1: Pydantic schema, prompt builder, and typed exceptions** - `a376f2a` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `bot/strategy/__init__.py` - Empty package marker for bot.strategy module
- `bot/strategy/claude_engine.py` - Full Claude engine: StrategySchema, _build_prompt, generate_strategy, exceptions, _parse_strategy_response
- `requirements.txt` - Added anthropic==0.86.0 and pandas==3.0.1

## Decisions Made
- `model_config = {"extra": "ignore"}` on StrategySchema — Claude may return additional experimental fields; drop silently rather than reject valid strategies
- Single retry uses a fresh API call (not multi-turn) — avoids confusing Claude with partial malformed output from first attempt
- `asyncio.timeout()` context manager (Python 3.11+) used over `asyncio.wait_for()` — cleaner syntax, compatible with project's requires-python >=3.12

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added anthropic and pandas to requirements.txt**
- **Found during:** Task 1 (implementation)
- **Issue:** `anthropic` and `pandas` not present in requirements.txt but required by claude_engine.py
- **Fix:** Installed both in venv, pinned versions to requirements.txt (`anthropic==0.86.0`, `pandas==3.0.1`)
- **Files modified:** requirements.txt
- **Verification:** `import anthropic; import pandas` succeeds in venv; all 3 tests pass
- **Committed in:** a376f2a (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical dependency)
**Impact on plan:** Necessary for correct operation — library is the core dependency of this module.

## Issues Encountered
- `python` command not found in shell (macOS 3.14 default); resolved by using `.venv/bin/python` which is the project's Python 3.14 venv. All tests run via `.venv/bin/python -m pytest`.

## User Setup Required
None - no external service configuration required for the engine implementation itself. The `ANTHROPIC_API_KEY` env var is already required by Settings and documented in prior phases.

## Next Phase Readiness
- `bot/strategy/claude_engine.py` is importable and fully implemented — ready for Strategy Manager (02-03) to call `generate_strategy()`
- All 3 RED tests now GREEN: test_prompt_contains_walk_forward, test_strategy_schema_validation, test_request_structure
- Requirements STRAT-01, STRAT-02, STRAT-04 fulfilled

## Self-Check: PASSED

All required files present:
- bot/strategy/__init__.py: FOUND
- bot/strategy/claude_engine.py: FOUND
- .planning/phases/02-strategy-pipeline/02-02-SUMMARY.md: FOUND

All task commits present:
- a376f2a: FOUND

---
*Phase: 02-strategy-pipeline*
*Completed: 2026-03-19*
