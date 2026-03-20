---
phase: 05-order-execution-and-position-monitoring
plan: "00"
subsystem: database, testing
tags: [alembic, sqlalchemy, pytest, binance-futures, positions, orders]

# Dependency graph
requires:
  - phase: 04-telegram-interface
    provides: Signal confirm/reject flow; callback idempotency pattern
  - phase: 03-signal-and-risk
    provides: Position, Order, Trade ORM models; RiskSettings

provides:
  - Alembic migration 0004 adding sl_order_id, tp_order_id, is_dry_run to positions table
  - UniqueConstraint uq_orders_signal_id on orders.signal_id
  - Updated Position and Order ORM models matching migration
  - mock_binance_client with 7 Futures order methods for Plans 01 and 02
  - mock_signal and mock_risk_settings fixtures
  - RED test stubs for ORD-01..05 + dry-run (test_order_executor.py)
  - RED test stubs for MON-01..05 (test_position_monitor.py)

affects:
  - 05-01-order-executor
  - 05-02-position-monitor

# Tech tracking
tech-stack:
  added: []
  patterns:
    - pytest.importorskip at module level for RED-state test stubs (established in Phase 2/3, continued here)
    - Alembic migration down_revision chain: 0003 -> 0004
    - UniqueConstraint in __table_args__ tuple on Order for double-tap protection

key-files:
  created:
    - alembic/versions/0004_phase5_position_order_fields.py
    - tests/test_order_executor.py
    - tests/test_position_monitor.py
  modified:
    - bot/db/models.py
    - tests/conftest.py

key-decisions:
  - "Phase 5 double-tap protection relies on uq_orders_signal_id DB constraint — executor will catch IntegrityError and return early rather than application-level check"
  - "RED stubs use pytest.importorskip at module level — entire file skips until production module exists, avoiding ImportError noise (consistent with Phase 2/3 pattern)"
  - "mock_binance_client extended in-place (not replaced) — backward compatible with all existing tests from Phases 2-4"

patterns-established:
  - "Bracket order IDs (SL/TP) stored as String(50) on Position — Binance order IDs are integers but stored as strings for flexibility"
  - "is_dry_run defaults server-side to false — production code sets True only for paper trading mode"

requirements-completed:
  - ORD-01
  - ORD-02
  - ORD-03
  - ORD-04
  - ORD-05
  - MON-01
  - MON-02
  - MON-03
  - MON-04
  - MON-05

# Metrics
duration: 2min
completed: 2026-03-20
---

# Phase 5 Plan 00: Order Execution and Position Monitoring — Wave 0 Infrastructure Summary

**Alembic migration 0004 adds sl_order_id, tp_order_id, is_dry_run to positions and uq_orders_signal_id constraint to orders; RED test scaffolds (11 async stubs) and extended mock_binance_client (7 Futures methods) establish the test contract for Plans 01 and 02.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-20T07:05:51Z
- **Completed:** 2026-03-20T07:07:57Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created Alembic migration 0004 with 4 schema ops: 3 new Position columns + 1 Order unique constraint
- Updated Position ORM model (sl_order_id, tp_order_id, is_dry_run) and Order model (__table_args__ UniqueConstraint)
- Extended mock_binance_client with all 7 Futures order API methods; added mock_signal and mock_risk_settings fixtures
- Created 6 RED async stubs in test_order_executor.py (ORD-01..05 + dry-run) and 5 in test_position_monitor.py (MON-01..05)

## Task Commits

Each task was committed atomically:

1. **Task 1: DB migration 0004 + ORM model updates** - `bdb764c` (chore)
2. **Task 2: Extend conftest.py + write RED test scaffolds** - `c6e5134` (test)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `alembic/versions/0004_phase5_position_order_fields.py` - Migration adding 3 Position columns and 1 Order unique constraint (rev 0003->0004)
- `bot/db/models.py` - Position gains sl_order_id, tp_order_id, is_dry_run; Order gains __table_args__ UniqueConstraint
- `tests/conftest.py` - mock_binance_client extended with 7 Futures methods; mock_signal and mock_risk_settings added
- `tests/test_order_executor.py` - 6 async RED stubs for ORD-01..05 + dry-run, importorskip on bot.order.executor
- `tests/test_position_monitor.py` - 5 async RED stubs for MON-01..05, importorskip on bot.monitor.position

## Decisions Made

- Phase 5 double-tap protection relies on uq_orders_signal_id DB constraint — executor catches IntegrityError and returns early rather than using an application-level check
- RED stubs use pytest.importorskip at module level — entire file skips until production module exists, avoiding ImportError noise (consistent with Phase 2/3 pattern)
- mock_binance_client extended in-place — backward compatible with all existing Phase 2-4 tests

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- DB schema ready for Plans 01 and 02 (migration 0004 defines all required columns)
- Test contracts established: Plans 01 and 02 implement production code until all 11 stubs turn GREEN
- mock_binance_client covers all 7 Futures API methods Plans 01 and 02 need

## Self-Check: PASSED

All required files found on disk. All task commits verified in git log.

---
*Phase: 05-order-execution-and-position-monitoring*
*Completed: 2026-03-20*
