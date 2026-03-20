# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — CTB MVP

**Shipped:** 2026-03-20
**Phases:** 7 | **Plans:** 23 | **Commits:** 123

### What Was Built
- Full semi-automated crypto futures trading bot with Claude AI strategy generation
- SMC + MACD/RSI signal detection with weighted scoring and chart visualization
- 14-command Telegram bot with Russian interface
- Order execution with SL/TP bracket, position monitoring, progressive stakes
- Daily summary, Pine Script generation, skipped coins tracking with loosen buttons

### What Worked
- Wave-based parallel execution — Plans 02-01/02-02, 03-02/03-03, 04-02/04-03, 06-01/06-02, 07-01/07-02 all ran in parallel successfully
- TDD Wave 0 pattern — RED test stubs before implementation caught real issues (pandas-ta column naming, pydantic .env isolation)
- Plan checker caught context compliance violations (expiry deactivation, signal dispatch wiring) before execution
- Spec-driven development — idea.md provided exact table schemas, message formats, and API examples that accelerated implementation

### What Was Inefficient
- Cross-phase integration gaps not caught until milestone audit — Signal DB row, DailyStats starting_balance, and orphaned risk functions required a full Phase 7 gap closure
- VERIFICATION.md frontmatter not updated after gap fixes during execution — led to stale status in audit
- Docker image needed rebuild between plans but volume mounts were used as workaround — should establish `docker compose build` as part of plan completion

### Patterns Established
- Async Python with dependency injection (client, session as params, not globals)
- Pydantic models for schema validation (StrategySchema, Settings with SecretStr)
- APScheduler CronTrigger for periodic jobs, IntervalTrigger for monitoring
- Russian labels + English data for Telegram messages
- `asyncio.to_thread()` for CPU-bound work (chart rendering)
- `SELECT ... FOR UPDATE` for idempotent Telegram callbacks
- Local imports to break circular dependencies (executor → commands._bot_state)

### Key Lessons
1. **Integration testing is the gap** — unit tests per module all pass, but cross-module wiring was the failure mode. Future milestones should include an integration test plan or dedicated wiring phase.
2. **Signal row creation is the linchpin** — the entire downstream flow (confirm, order, monitor, trade, stats) depends on a single DB row being created at the right moment. This was the most impactful single bug.
3. **Orphaned functions are a code smell** — `check_rr_ratio`, `validate_liquidation_safety`, `check_and_warn_daily_loss` were all implemented but never called. Planner should verify all exported functions have at least one call site.

### Cost Observations
- Model mix: ~80% Sonnet (researchers, planners, executors, checkers), ~20% Opus (planner model for complex phases)
- 7 phases completed in ~24 hours elapsed time
- Parallel execution saved ~30% time on multi-plan waves

---

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Phases | 7 |
| Plans | 23 |
| LOC (bot) | 6,111 |
| LOC (tests) | 4,375 |
| Commits | 123 |
| Duration | 2 days |
| Gaps found at audit | 3 |
| Gap closure phases | 1 |
