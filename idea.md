# ТЕХНИЧЕСКОЕ ЗАДАНИЕ
## Crypto Futures Trading Bot
**SMC + MACD/RSI | Binance Futures API | Полуавтомат | Telegram**
Версия 4.0 | 2025

---

## Содержание

1. [Общая информация](#1-общая-информация)
2. [Binance Futures Testnet](#2-binance-futures-testnet)
3. [Архитектура системы](#3-архитектура-системы)
4. [Бэктестинг через Claude code_execution](#4-бэктестинг-через-claude-code_execution)
5. [Критерии отбора стратегии](#5-критерии-отбора-стратегии-управляются-через-telegram)
6. [Формат торговой стратегии в БД](#6-формат-торговой-стратегии-в-бд)
7. [Риск-менеджмент](#7-риск-менеджмент-глобальный-управляется-через-telegram)
8. [Telegram-бот](#8-telegram-бот)
9. [Визуализация графиков](#9-визуализация-графиков)
10. [База данных](#10-база-данных)
11. [Этапы разработки](#11-этапы-разработки)
12. [Важные замечания](#12-важные-замечания-для-разработчика)

---

## 1. Общая информация

| Параметр | Значение |
|---|---|
| Название | Crypto Futures Trading Bot (CTB) |
| Тип торговли | Binance USDT-M Perpetual Futures (бессрочные контракты) |
| Начальный депозит | от $100 USDT |
| Пользователи | Один трейдер (single-user) |
| Режим автоматизации | Полуавтомат: сигналы авто, вход — ручное подтверждение |
| Интерфейс | Telegram-бот |
| Среда разработки | Binance Futures Testnet → Production (переключение одной переменной) |
| AI-компонент | Claude API: генерация стратегий + бэктест через code_execution |
| Версия ТЗ | 4.0 |

---

## 2. Binance Futures Testnet

### 2.1. Как работает

Testnet — полная копия Binance Futures с виртуальными средствами. Все API-эндпоинты, ордера, позиции, WebSocket-стримы идентичны реальной бирже.

| Параметр | Значение |
|---|---|
| URL Testnet REST API | `https://testnet.binancefuture.com` |
| URL Production REST API | `https://fapi.binance.com` |
| Аккаунт | Отдельная регистрация через testnet.binancefuture.com (GitHub-логин) |
| Стартовый баланс | ~15 000 виртуальных USDT (пополнение через Faucet) |
| Сброс данных | Раз в ~месяц (без предупреждения) |
| Ликвидность | Отличается от реальной — не отражает реальный slippage |

### 2.2. Переключение Testnet → Production

Меняются только 2 переменные в `.env`:

```env
# Testnet
BINANCE_ENV=testnet
BINANCE_API_KEY=<testnet_key>
BINANCE_API_SECRET=<testnet_secret>

# Production
BINANCE_ENV=production
BINANCE_API_KEY=<real_key>
BINANCE_API_SECRET=<real_secret>
```

В коде `base_url` выбирается автоматически по `BINANCE_ENV`. Больше ничего менять не нужно.

---

## 3. Архитектура системы

| Модуль | Функция |
|---|---|
| Market Scanner | Каждый час выбирает топ-N монет по объёму торгов |
| Strategy Manager | Проверяет наличие актуальной стратегии в БД |
| Claude Strategy Engine | Генерирует и бэктестирует стратегию через Claude API |
| Strategy Filter | Проверяет стратегию по критериям отбора (раздел 5) |
| Signal Generator | Применяет стратегию к текущим данным → сигнал |
| Risk Manager | Глобальный риск: размер позиции, прогрессия ставок, лимиты |
| Order Executor | Размещает ордер на Binance после подтверждения |
| Chart Generator | Генерирует PNG и Pine Script для сигнала |
| Telegram Bot | Единственный интерфейс: сигналы, управление, настройки |
| Database | Хранит стратегии, сигналы, сделки, настройки |

### 3.1. Технологический стек

- **Python** 3.11+
- **Binance**: python-binance или CCXT
- **AI**: Anthropic Claude API (`claude-sonnet-4-20250514`) + `code_execution` tool
- **БД**: PostgreSQL + SQLAlchemy (SQLite для MVP)
- **Scheduler**: APScheduler
- **Telegram**: aiogram 3.x
- **Индикаторы**: pandas-ta или TA-Lib
- **Графики**: mplfinance + matplotlib
- **Деплой**: VPS, Docker + systemd

---

## 4. Бэктестинг через Claude code_execution

Claude API включает встроенный инструмент `code_execution` — Claude сам пишет Python-код и выполняет его в sandbox-среде. Отдельного бэктест-сервиса не нужно.

### 4.1. Алгоритм генерации стратегии

1. Бот загружает OHLCV-данные монеты с Binance (за период `backtest_period_months`, таймфреймы 1h и 15m)
2. Передаёт данные в виде JSON в Claude API с промптом
3. Claude через `code_execution` пишет pandas-код: рассчитывает MACD, RSI, SMC-структуры, перебирает параметры
4. Выбирает комбинацию с наилучшим profit factor и winrate
5. Возвращает стратегию строго в JSON-формате (раздел 6)
6. **Strategy Filter** проверяет результаты бэктеста по критериям отбора (раздел 5)
7. Если критерии пройдены — стратегия сохраняется в БД, монета берётся в работу
8. Если критерии не пройдены — монета пропускается, бот переходит к следующей в топе

### 4.2. Пример запроса к Claude API

```python
response = anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[{
        "role": "user",
        "content": f"""
            Данные OHLCV для {symbol} ({timeframe}) за {backtest_period_months} мес.: {ohlcv_json}

            Задача: найди оптимальные параметры стратегии SMC + MACD/RSI.
            Напиши Python-код (pandas), прогони бэктест на этих данных.

            Требования к результату бэктеста:
            - Суммарная доходность >= {min_total_return_pct}%
            - Максимальная просадка <= {max_drawdown_pct}%
            - Win Rate >= {min_win_rate_pct}%
            - Profit Factor >= {min_profit_factor}
            - Минимум сделок за период: {min_trades}

            Верни ТОЛЬКО JSON в формате стратегии (без Markdown).
            Если подобрать параметры под требования невозможно —
            верни {{"status": "no_strategy_found", "reason": "..."}}
        """
    }]
)
```

### 4.3. Метрики бэктеста

| Метрика | Описание | Дефолтный критерий |
|---|---|---|
| `total_return_pct` | Суммарная доходность за период | ≥ +200% |
| `max_drawdown_pct` | Максимальная просадка | ≤ -12% |
| `win_rate` | Процент прибыльных сделок | ≥ 55% |
| `profit_factor` | Валовая прибыль / убыток | ≥ 1.8 |
| `total_trades` | Количество сделок за период | ≥ 30 |
| `avg_rr` | Среднее R/R на сделку | ≥ 2.0 |

---

## 5. Критерии отбора стратегии (управляются через Telegram)

### 5.1. Логика работы

```
Для каждой монеты из топа по объёму:

  ┌─ Есть стратегия в БД и не устарела? ──► Использовать, перейти к Signal Generator
  │
  └─ Нет / устарела
       │
       ▼
  Запрос к Claude API (бэктест за backtest_period_months)
       │
       ▼
  ┌─ Все критерии пройдены? ──► Сохранить стратегию, перейти к Signal Generator
  │
  └─ Критерии НЕ пройдены
       │
       ▼
  Записать в лог: символ + какие критерии провалены
  Отправить уведомление в Telegram (опционально, если notify_on_skip=true)
  Перейти к следующей монете в топе
```

### 5.2. Параметры критериев (таблица `strategy_criteria`)

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `backtest_period_months` | INT | 6 | Период бэктеста в месяцах |
| `min_total_return_pct` | FLOAT | 200.0 | Минимальная суммарная доходность (%) |
| `max_drawdown_pct` | FLOAT | -12.0 | Максимально допустимая просадка (%) — отрицательное число |
| `min_win_rate_pct` | FLOAT | 55.0 | Минимальный win rate (%) |
| `min_profit_factor` | FLOAT | 1.8 | Минимальный profit factor |
| `min_trades` | INT | 30 | Минимум сделок за период (статистическая значимость) |
| `min_avg_rr` | FLOAT | 2.0 | Минимальное среднее R/R |
| `notify_on_skip` | BOOL | true | Уведомлять в Telegram, если монета пропущена |
| `strict_mode` | BOOL | false | Все критерии обязательны (false = достаточно пройти основные: return + drawdown) |

### 5.3. Управление через Telegram (/criteria)

```
/criteria                        — показать текущие критерии
/criteria period 6               — период бэктеста = 6 месяцев
/criteria return 200             — мин. доходность = +200%
/criteria drawdown 12            — макс. просадка = -12% (вводим без минуса)
/criteria winrate 55             — мин. win rate = 55%
/criteria pf 1.8                 — мин. profit factor = 1.8
/criteria trades 30              — мин. сделок = 30
/criteria rr 2.0                 — мин. среднее R/R = 2.0
/criteria notify on/off          — уведомлять при пропуске монеты
/criteria strict on/off          — строгий режим (все критерии обязательны)
/criteria reset                  — сбросить на дефолтные значения
```

### 5.4. Уведомление о пропуске монеты (пример)

```
⚠️ Монета пропущена: XRPUSDT

📊 Результаты бэктеста (6 мес.):
  Доходность:    +87%     ❌  (требуется ≥ +200%)
  Просадка:      -18.4%   ❌  (лимит: -12%)
  Win Rate:       61%     ✅
  Profit Factor:  2.1     ✅
  Сделок:         44      ✅

➡️ Переход к следующей монете
```

### 5.5. Команда /skipped — история пропущенных монет

```
/skipped          — монеты, пропущенные за последние 24 часа
/skipped week     — за последние 7 дней
/skipped XRPUSDT  — история конкретной монеты
```

Это позволяет отслеживать, какие монеты стабильно не проходят критерии — возможно, стоит ослабить фильтры или убрать монету из топа вручную.

---

## 6. Формат торговой стратегии в БД

### 6.1. Поля таблицы `strategies`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | Первичный ключ |
| `symbol` | VARCHAR(20) | Тикер монеты (BTCUSDT, SOLUSDT...) |
| `timeframe` | VARCHAR(5) | Таймфрейм (1h или 15m) |
| `strategy_data` | JSONB | Полный JSON стратегии |
| `backtest_score` | FLOAT | Скор: profit_factor × win_rate |
| `is_active` | BOOLEAN | Активна ли стратегия сейчас |
| `created_at` | TIMESTAMP | Когда создана впервые |
| `updated_at` | TIMESTAMP | Последнее обновление |
| `next_review_at` | TIMESTAMP | Дата следующей проверки |
| `review_interval_days` | INT | Интервал обновления (дефолт: 30 дней) |
| `source` | VARCHAR(20) | `claude_generated` / `manual` |
| `criteria_snapshot` | JSONB | Копия критериев на момент генерации |

### 6.2. JSON-структура strategy_data

```json
{
  "symbol": "SOLUSDT",
  "timeframe": "1h",

  "indicators": {
    "macd": { "fast": 12, "slow": 26, "signal": 9 },
    "rsi":  { "period": 14, "oversold": 30, "overbought": 70 }
  },

  "smc": {
    "ob_lookback_bars":   20,
    "fvg_min_size_pct":   0.3,
    "require_bos_confirm": true,
    "use_choch":           true,
    "htf_confirmation":    "4h"
  },

  "entry": {
    "long":  [
      "price_in_demand_ob_or_fvg",
      "macd_cross_up OR rsi_exit_oversold",
      "bos_or_choch_bullish_on_htf",
      "volume_above_avg_1_3x"
    ],
    "short": [
      "price_in_supply_ob_or_fvg",
      "macd_cross_down OR rsi_exit_overbought",
      "bos_or_choch_bearish_on_htf",
      "volume_above_avg_1_3x"
    ]
  },

  "exit": {
    "sl_method":    "ob_boundary",
    "sl_atr_mult":  1.5,
    "tp_rr_ratio":  3.0,
    "trailing_stop": false
  },

  "backtest": {
    "period_months":    6,
    "total_trades":     48,
    "total_return_pct": 247.3,
    "win_rate":         0.63,
    "profit_factor":    2.45,
    "max_drawdown_pct": -7.8,
    "avg_rr":           2.9,
    "criteria_passed":  true
  }
}
```

### 6.3. Логика обновления стратегии

- Стратегия устарела, если `now() >= next_review_at`
- При устаревании монета отправляется в Claude Strategy Engine
- После генерации — прогоняется через Strategy Filter по текущим критериям
- Интервал обновления: 30 дней по умолчанию (настраивается через `/settings review_interval N`)
- При обновлении: `updated_at = now()`, `next_review_at = now() + review_interval_days`
- Старые версии стратегий не удаляются: `is_active = false`

---

## 7. Риск-менеджмент (глобальный, управляется через Telegram)

Единые настройки для всей торговли. Хранятся в таблице `risk_settings` (одна строка). Изменяются через `/risk` без перезапуска.

### 7.1. Параметры

| Параметр | По умолчанию | Описание |
|---|---|---|
| `base_stake_pct` | 3% | Начальный размер ставки от депозита |
| `current_stake_pct` | 3% | Текущий размер ставки (меняется автоматически) |
| `max_stake_pct` | 8% | Максимально допустимая ставка |
| `progressive_stakes` | [3, 5, 8] | Лесенка ставок при серии побед (%) |
| `wins_to_increase` | 1 | Побед подряд для перехода на следующую ставку |
| `reset_on_loss` | true | Сбрасывать ставку на base при любом убытке |
| `min_rr_ratio` | 3.0 | Минимальный R/R — сигналы ниже порога игнорируются |
| `max_open_positions` | 5 | Максимум одновременно открытых позиций |
| `daily_loss_limit_pct` | 5% | Дневной лимит потерь — после стоп торговли |
| `leverage` | 5 | Плечо для всех сделок |
| `margin_type` | isolated | Тип маржи (isolated рекомендован) |
| `win_streak_current` | 0 | Текущая серия побед (авто, read-only) |

### 7.2. Прогрессивные ставки

```
Старт / после любого убытка → ставка 3%   (base_stake_pct, win_streak = 0)
1-я победа                  → ставка 5%   (progressive_stakes[1])
2-я победа подряд           → ставка 8%   (progressive_stakes[2] = max)
Любой убыток                → ставка 3%   (сброс на base, win_streak = 0)
```

### 7.3. Расчёт размера позиции (Futures с плечом)

```
risk_usdt     = balance × current_stake_pct / 100
sl_distance   = |entry_price − stop_loss| / entry_price
position_usdt = risk_usdt / sl_distance
contracts     = position_usdt × leverage / entry_price

Пример: баланс $100, ставка 3%, вход $145, SL $140, плечо 5x
  risk_usdt     = $3.00
  sl_distance   = 3.45%
  position_usdt = $86.96
  contracts     = ~3.0 SOL
  Максимальный убыток: $3.00 (3% депозита) — isolated margin
```

### 7.4. Управление через Telegram (/risk)

```
/risk                      — текущие настройки
/risk stake 3              — base_stake_pct = 3%
/risk max_stake 8          — max_stake_pct = 8%
/risk progressive 3 5 8    — задать лесенку ставок
/risk rr 3.0               — минимальный R/R ratio
/risk leverage 5           — плечо
/risk daily_limit 5        — дневной лимит потерь %
/risk max_pos 5            — макс. одновременных позиций
/risk reset                — сбросить streak, вернуть базовую ставку
```

---

## 8. Telegram-бот

### 8.1. Все команды

| Команда | Описание |
|---|---|
| `/start` | Статус системы, приветствие, текущая ставка и депозит |
| `/status` | Баланс, открытые позиции, дневной PnL, текущая streak-ставка |
| `/risk` | Просмотр и изменение параметров риск-менеджмента |
| `/criteria` | Просмотр и изменение критериев отбора стратегий |
| `/signals` | Последние 10 сигналов (принятые и отклонённые с причиной) |
| `/positions` | Открытые позиции с текущим PnL в реальном времени |
| `/history` | История последних 20 закрытых сделок |
| `/strategies` | Список монет со стратегиями + дата следующего review |
| `/skipped` | Монеты, пропущенные из-за критериев |
| `/scan` | Запустить сканирование рынка вручную |
| `/chart SYMBOL` | Получить Pine Script для последнего сигнала по монете |
| `/settings` | Общие настройки: топ-N монет, таймфреймы, интервал обновления |
| `/pause` / `/resume` | Приостановить / возобновить генерацию сигналов |
| `/testnet` / `/production` | Показать текущую среду подключения |
| `/help` | Справка по всем командам |

### 8.2. Формат сигнала в Telegram

```
🟢 СИГНАЛ: LONG  |  SOLUSDT  |  1h

📌 Вход:         $145.30  (рыночный)
🛑 Stop Loss:    $140.00  (-3.65%)
🎯 Take Profit:  $163.20  (+12.32%)
⚖️  R/R Ratio:    1 : 3.37  ✅
💰 Ставка:        5% депозита  ($5.00 риск)
📊 Размер:        ~3.0 SOL  ($435 USDT с плечом 5x)
💪 Сила сигнала: Strong

📈 Обоснование:
  • Цена в зоне Demand OB [142.5 – 145.8]
  • MACD пересечение вверх (12/26/9)
  • BOS подтверждён на 4h
  • Объём: +45% к средним

[изображение графика с разметкой]

[ ✅ Открыть сделку ]   [ ❌ Отклонить ]   [ 📊 Pine Script ]
```

### 8.3. Уведомления

- Сигнал с картинкой графика
- Подтверждение открытия ордера на бирже
- Уведомление о достижении SL или TP
- ⚠️ Монета пропущена из-за критериев (если `notify_on_skip = true`)
- Ежедневная сводка в 21:00: PnL, сделки, win rate, текущая ставка
- Предупреждение при достижении 80% дневного лимита убытков
- Ошибки API, ошибки ордеров, недостаток баланса

---

## 9. Визуализация графиков

### 9.1. Картинка в Telegram

Бот генерирует PNG и прикрепляет к сообщению с сигналом автоматически.

**Что отображается:**
- Свечной график последних 100–150 баров
- Зоны Order Block: Bullish OB (зелёный прямоугольник) / Bearish OB (красный)
- Зоны Fair Value Gap (FVG): прозрачные прямоугольники с пунктирной границей
- Уровень BOS / CHOCH: горизонтальная линия с подписью
- Стрелка входа: ▲ зелёная (Long) или ▼ красная (Short)
- Горизонтальные линии: Entry (синяя пунктир), Stop Loss (красная), Take Profit (зелёная)
- Панель MACD: гистограмма + линии, точка пересечения помечена
- Панель RSI: уровни 30/70, зона сигнала выделена
- Заголовок: символ, таймфрейм, направление, R/R

**Стек:** `mplfinance` + `matplotlib`, генерация в `BytesIO` (без сохранения на диск).

```python
# Упрощённая схема
def generate_chart(symbol, signal, ohlcv_df, strategy):
    fig, axes = mpf.plot(ohlcv_df, type='candle', style='charles',
                         addplot=[macd_plot, rsi_plot], returnfig=True)
    ax = axes[0]

    for ob in signal.order_blocks:
        rect = Rectangle((ob.x, ob.low), width, ob.high - ob.low,
                          color='green' if ob.bullish else 'red', alpha=0.2)
        ax.add_patch(rect)

    ax.axhline(signal.entry, linestyle='--', color='royalblue', lw=1.2)
    ax.axhline(signal.sl,    linestyle='-',  color='red',       lw=1.5)
    ax.axhline(signal.tp,    linestyle='-',  color='green',     lw=1.5)

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    return buf
```

### 9.2. TradingView Pine Script

По кнопке `[📊 Pine Script]` бот присылает готовый Pine Script v5 — вставляешь в Pine Editor на TradingView, видишь те же зоны и уровни на интерактивном графике.

**Что показывает:**
- Order Block зоны (`box.new`)
- FVG зоны (`box.new` с пунктиром)
- BOS / CHOCH уровни (`line.new` с подписью)
- Стрелки входа (`plotshape`)
- Entry / SL / TP (`hline`)
- MACD и RSI в нижних панелях

**Как использовать:**
1. Получил сигнал → нажал `[📊 Pine Script]`
2. Бот прислал код
3. TradingView → нужный символ → Pine Editor → вставил → Add to chart

```
/chart SOLUSDT    — запросить Pine Script для последнего сигнала по монете
```

```pine
//@version=5
indicator("CTB Signal — SOLUSDT 1h", overlay=true)

// Order Block
var box ob1 = box.new(bar_index-8, 142.5, bar_index, 145.8,
    bgcolor=color.new(color.green, 80),
    border_color=color.green, border_width=1)

// Entry / SL / TP
hline(145.30, "Entry", color=color.blue,  linestyle=hline.style_dashed)
hline(140.00, "SL",    color=color.red,   linestyle=hline.style_solid,  linewidth=2)
hline(163.20, "TP",    color=color.green, linestyle=hline.style_solid,  linewidth=2)

// Стрелка входа
plotshape(bar_index == last_bar_index, style=shape.triangleup,
    location=location.belowbar, color=color.green, size=size.normal)
```

---

## 10. База данных

### 10.1. Таблицы

| Таблица | Содержимое |
|---|---|
| `strategies` | Стратегии монет с историей версий |
| `strategy_criteria` | Единая строка с критериями отбора стратегий |
| `risk_settings` | Единая строка с глобальными параметрами риска |
| `signals` | Все сгенерированные сигналы (accepted / rejected / expired) |
| `skipped_coins` | Монеты, пропущенные из-за критериев + причина + метрики бэктеста |
| `orders` | Ордера на бирже (binance_order_id, status, executed_price) |
| `positions` | Открытые позиции с текущим PnL |
| `trades` | Закрытые сделки (entry, exit, pnl, close_reason) |
| `daily_stats` | Дневная статистика (pnl, trades, win_rate, streak) |
| `logs` | Системный журнал |

---

## 11. Этапы разработки

| # | Модуль | Содержание | Срок |
|---|---|---|---|
| 1 | Инфраструктура | Репо, Docker, БД, .env, Binance Testnet | 1 нед. |
| 2 | Market Scanner | Топ-N монет по объёму, расписание | 1 нед. |
| 3 | Claude Engine + бэктест | Claude API с code_execution, генерация стратегий | 2 нед. |
| 4 | Strategy Filter | Критерии отбора, логика пропуска монеты | 1 нед. |
| 5 | Signal Generator | SMC + MACD/RSI расчёты, фильтр по R/R | 2 нед. |
| 6 | Risk Manager | Прогрессия ставок, расчёт позиции с плечом | 1 нед. |
| 7 | Chart Generator | mplfinance PNG + Pine Script генерация | 1 нед. |
| 8 | Telegram Bot | Все команды: /risk, /criteria, /chart, сигналы | 2 нед. |
| 9 | Order Executor | Подтверждение → Futures API → мониторинг | 1 нед. |
| 10 | Тестирование | Testnet, edge cases, $100 депозит | 2 нед. |
| 11 | Production | Смена .env, smoke test с минимальной позицией | 0.5 нед. |

**Итого: ~14.5 недель**

---

## 12. Важные замечания для разработчика

### 12.1. Малый депозит ($100)

- Минимальный размер ордера на Binance Futures — $5–10 USDT. Проверять `MIN_NOTIONAL` через `GET /fapi/v1/exchangeInfo`
- При депозите < $200 рекомендуется `max_open_positions = 2–3`
- Isolated margin обязательна — убыток ограничен выделенной маржой

### 12.2. Безопасность

- API-ключи только в `.env`, файл в `.gitignore`
- Binance API: включить только Futures Trading, отключить Withdrawal
- Включить IP Whitelist на Binance для API ключа
- Telegram-бот принимает команды только от одного `chat_id` (`ALLOWED_CHAT_ID` в `.env`)

### 12.3. Обработка сбоев

- Ошибка Claude API → логировать, пропустить монету в текущем цикле, повторить в следующем
- Ошибка Binance при размещении ордера → немедленное уведомление в Telegram
- При рестарте бота → загружать открытые позиции из Binance API, синхронизировать с БД

### 12.4. Работа Strategy Filter при большом количестве пропусков

Если за несколько циклов подряд все монеты не проходят критерии:
- Бот отправляет уведомление: `⚠️ За последние N циклов ни одна монета не прошла критерии отбора`
- Предлагает через кнопки: `[Ослабить критерии]` → открывает `/criteria` | `[Продолжить ожидание]`
- Это защита от ситуации, когда бот молча не торгует из-за слишком жёстких фильтров

---

*Конец документа — версия 4.0*