# Phase 6: Reporting and Audit - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Daily summary report at 21:00 UTC+5, Pine Script v5 generator (full overlay + MACD/RSI panels), and skipped coins tracking with `/skipped` command and consecutive-skip alert with loosen-criteria buttons. These are additive features on top of the fully working trade loop from Phases 1-5.

</domain>

<decisions>
## Implementation Decisions

### Daily Summary Content
- Metrics: PnL ($), trade count, win rate (%), current stake tier, balance snapshot (current + change from yesterday), best/worst trade of the day (symbol + PnL), number of active strategies + number due for review
- Always send at 21:00 even on zero-trade days: "Нет сделок за сегодня. Баланс: $X. Ставка: 3%"
- Scheduled at 21:00 UTC+5 (trader's timezone) — APScheduler CronTrigger with `timezone='Etc/GMT-5'`
- Data sourced from DailyStats table (already aggregated by Position Monitor) + Binance balance API

### Pine Script Output
- Full TradingView overlay: entry/SL/TP hlines, OB zones (box.new), FVG zones (box.new dashed), BOS/CHOCH lines (line.new), entry arrow (plotshape)
- Include MACD + RSI lower panels in Pine Script
- Signal annotation: text label with direction, R/R, signal strength
- Delivered as .txt file attachment in Telegram (not inline code block) — trader downloads and pastes into Pine Editor
- Scope: any signal by ID — `/chart SOLUSDT` returns Pine for the most recent signal, inline Pine Script button returns Pine for that specific signal
- Replace the placeholder `handle_pine` in callbacks.py and `/chart` in commands.py with real implementations

### Skipped Coins Display
- Compact list by default: one line per coin (symbol, failed criteria count, timestamp)
- `/skipped SYMBOL` drill-down: detailed view with full backtest results + which criteria failed
- Time filters per spec: `/skipped` = last 24h, `/skipped week` = last 7 days, `/skipped SYMBOL` = history for specific coin
- Consecutive-skip alert (already wired in Phase 4): ADD inline buttons to loosen specific criteria (e.g., "Ослабить drawdown до -15%", "Ослабить return до 150%")

### Claude's Discretion
- Pine Script v5 code generation approach (template-based vs dynamic)
- Daily summary message formatting (exact emoji placement, line spacing)
- How to determine "best/worst trade" when DailyStats doesn't store individual trade details (query Trade table)
- Skipped coins loosen-button callback data format

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec
- `.planning/PROJECT.md` — Core value
- `.planning/REQUIREMENTS.md` — TG-19, PINE-01 through PINE-03, SKIP-01 through SKIP-04
- `.planning/ROADMAP.md` — Phase 6 details, success criteria

### Original spec
- `idea.md` — Section 8.3 (daily summary at 21:00), Section 9.2 (Pine Script format with exact code example), Section 5.4-5.5 (skipped coins notification and /skipped command)

### Existing code
- `bot/telegram/handlers/callbacks.py: handle_pine` — placeholder, needs real implementation
- `bot/telegram/handlers/commands.py: cmd_chart` — placeholder, needs real implementation
- `bot/telegram/notifications.py: send_skipped_coins_alert()` — already wired, needs loosen-criteria buttons added
- `bot/db/models.py: DailyStats` — date, total_pnl, trade_count, win_rate, win_streak
- `bot/db/models.py: SkippedCoin` — symbol, backtest_results JSONB, failed_criteria JSONB, created_at
- `bot/db/models.py: Trade` — entry_price, exit_price, realized_pnl, close_reason (for best/worst trade query)
- `bot/db/models.py: Signal` — has all fields needed to reconstruct Pine Script (entry, SL, TP, zones data)
- `bot/signals/smc.py` — OrderBlock, FVG, StructureLevel dataclasses (for Pine Script zone coordinates)
- `bot/main.py` — APScheduler job registration pattern established

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot/telegram/handlers/callbacks.py: handle_pine` — placeholder at line 200, just needs body replaced
- `bot/telegram/handlers/commands.py: cmd_chart` — placeholder at line 344, needs real implementation
- `bot/telegram/notifications.py: send_skipped_coins_alert()` — needs inline keyboard added for loosen buttons
- `bot/db/models.py: DailyStats` — already has all needed fields, aggregated by position monitor
- `bot/db/models.py: SkippedCoin` — already has backtest_results and failed_criteria JSONB
- `bot/signals/smc.py` — zone dataclasses can be deserialized from Signal's strategy data for Pine generation

### Established Patterns
- APScheduler CronTrigger for scheduled jobs (scan hourly, expiry daily)
- Russian labels + English data in Telegram messages
- Compact one-line-per-item for query commands
- `send_error_alert()` with 15-min throttle for notifications
- `BufferedInputFile` for sending files via Telegram (used for chart PNG)

### Integration Points
- Daily summary: new APScheduler CronTrigger job at 21:00 UTC+5, queries DailyStats + Trade + Binance balance
- Pine Script: `handle_pine` callback reads Signal + zones data → generates Pine v5 string → sends as .txt file
- `/chart SYMBOL`: queries latest Signal for symbol → same Pine generation → sends as .txt file
- Skipped coins loosen buttons: callback modifies StrategyCriteria table (same pattern as /criteria command)
- All three features register in main.py alongside existing jobs/routers

</code_context>

<specifics>
## Specific Ideas

- The spec (section 9.2) has an exact Pine Script v5 example — use this as the template for generation
- Pine Script must be copy-paste ready — no placeholder variables, all values hardcoded for the specific signal
- Daily summary should look similar to the spec section 8.3 notification example
- Loosen-criteria buttons on the consecutive-skip alert should show the most commonly failed criteria across recent skips

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-reporting-and-audit*
*Context gathered: 2026-03-20*
