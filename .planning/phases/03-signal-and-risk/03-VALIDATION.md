---
phase: 3
slug: signal-and-risk
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24+ |
| **Config file** | `pytest.ini` (exists from Phase 1) |
| **Quick run command** | `pytest tests/test_smc.py tests/test_indicators.py tests/test_risk_manager.py tests/test_chart_generator.py -q --tb=short` |
| **Full suite command** | `pytest tests/ -q --tb=short` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 25 seconds

---

## Wave 0 Requirements

- [ ] `requirements.txt` — add `pandas-ta-classic==0.4.47`, `mplfinance==0.12.10b0`
- [ ] `tests/fixtures/ohlcv_sample.csv` — sample 15m OHLCV data (100+ rows) for deterministic tests
- [ ] `tests/test_smc.py` — covers SIG-02 (OB/FVG/BOS/CHOCH detection)
- [ ] `tests/test_indicators.py` — covers SIG-03 (MACD crossover, RSI signals)
- [ ] `tests/test_signal_generator.py` — covers SIG-01, SIG-04, SIG-05, SIG-06
- [ ] `tests/test_risk_manager.py` — covers RISK-01 through RISK-09
- [ ] `tests/test_chart_generator.py` — covers CHART-01, CHART-02, CHART-05, CHART-09

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chart OB/FVG zones render correctly | CHART-02, CHART-03 | Visual correctness | Open generated PNG, verify green/red OB zones and dashed FVG borders |
| MACD/RSI panels readable | CHART-06, CHART-07 | Visual correctness | Verify MACD histogram + RSI 30/70 levels in chart PNG |
| Chart title correct | CHART-08 | Visual correctness | Verify symbol/timeframe/direction/R:R in chart title |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
