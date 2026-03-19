# Phase 1: Foundation - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Docker stack, PostgreSQL with all tables, Alembic migrations, Binance client (Testnet/Production switch), APScheduler wiring, async app skeleton with graceful startup and shutdown. No trading logic, no signals, no Telegram commands — just the infrastructure skeleton that all later phases build on.

</domain>

<decisions>
## Implementation Decisions

### Config & Secrets
- Runtime settings (risk params, criteria, top-N, etc.) stored in DB with .env providing initial defaults
- .env contains both secrets (API keys, tokens, DB URL) AND initial default values for risk/criteria/settings
- On first boot, Alembic migration seeds default rows in risk_settings and strategy_criteria tables from the spec defaults
- DB values override .env defaults — once a setting is changed via Telegram, the DB value wins
- .env.example included in repo with all variables documented, comments explaining each, placeholder values
- Pydantic validates all env vars on boot — missing required var = immediate exit with clear error message naming the var
- API keys, tokens never appear in any log output — strict masking, no partial reveals even in debug mode

### DB Schema Design
- ALL 10 tables created in the first Alembic migration — schema is stable from spec, no per-phase migrations
- UUID primary keys on all tables (as specified in the TZ)
- created_at/updated_at use PostgreSQL server_default=now() — always UTC, DB handles timestamps
- JSONB for strategy_data and criteria_snapshot columns

### Startup & Shutdown
- Boot sequence verifies ALL three dependencies before accepting work: DB connection + migrations current, Binance API ping (confirm keys work + log active environment), Telegram bot token valid
- If any check fails → log error, exit immediately (fail fast)
- On successful boot → send Telegram message: "Bot started — env: testnet/production, balance: $X, open positions: N"
- On restart → fetch open positions from Binance API, compare with DB, reconcile mismatches, log any differences
- On shutdown (SIGTERM/SIGINT) → leave positions open on Binance (SL/TP are already placed), stop scheduler cleanly, log "shutdown complete", exit with no exceptions
- Positions are safe without the bot running because SL/TP bracket orders live on Binance

### Claude's Discretion
- Python project directory structure and module layout
- Exact Docker Compose configuration (volumes, networks, health checks)
- Logging library choice and format (loguru vs stdlib)
- SQLAlchemy model base class design
- APScheduler job store choice (PostgreSQL vs in-memory)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec
- `.planning/PROJECT.md` — Core value, constraints, tech stack decisions
- `.planning/REQUIREMENTS.md` — INFRA-01 through INFRA-08 are this phase's requirements
- `.planning/ROADMAP.md` — Phase 1 details, success criteria, plan breakdown

### Research
- `.planning/research/STACK.md` — Validated library versions (python-binance 1.0.35, aiogram 3.26, SQLAlchemy 2.0, APScheduler 3.11.2, asyncpg)
- `.planning/research/ARCHITECTURE.md` — Component boundaries, data flow, project structure recommendation
- `.planning/research/PITFALLS.md` — APScheduler PostgreSQL job store caveat, testnet URL drift warning

### Original spec
- `idea.md` — Full technical specification (ТЗ v4.0) with all table schemas, env var structure, and architecture details

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None yet — Phase 1 establishes all patterns

### Integration Points
- This phase creates the foundation that all subsequent phases import: DB session factory, Binance client, config models, scheduler instance

</code_context>

<specifics>
## Specific Ideas

- Binance environment switch must be a single env var (`BINANCE_ENV=testnet` or `production`) — base URL selected automatically
- The spec defines exact table schemas in sections 6.1, 7.1, 5.2, 10.1 — use these as the source of truth for the Alembic migration
- `.env` structure follows the pattern from section 2.2 of the spec

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-19*
