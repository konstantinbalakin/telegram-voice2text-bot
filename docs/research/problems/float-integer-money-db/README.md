# Float vs Integer для хранения денег и минут в БД

## Суть проблемы

IEEE 754 floating point (тип `FLOAT`/`REAL` в SQLite) не может точно представить многие десятичные дроби.

```python
>>> 0.1 + 0.2
0.30000000000000004  # не 0.3!

>>> sum([0.1] * 10)
0.9999999999999999  # не 1.0!

>>> 299.99 * 3
899.9699999999999  # не 899.97!
```

## Что затронуто в нашем проекте

Все поля с типом `Float` в билинговых таблицах:

| Таблица | Поле | Назначение |
|---------|------|------------|
| `subscription_prices` | `amount_rub` | Цена подписки в рублях |
| `minute_packages` | `price_rub` | Цена пакета в рублях |
| `purchases` | `amount` | Сумма покупки |
| `user_minute_balances` | `minutes_remaining` | Остаток минут |
| `daily_usage` | `minutes_used`, `minutes_from_daily/bonus/package` | Использование |
| `deduction_log` | `minutes_deducted` | Списание минут |
| `subscription_tiers` | `daily_limit_minutes` | Дневной лимит |
| `billing_conditions` | `value` (строка, но парсится во float) | Условия |

## Практические последствия

### Для денег (рубли)

На текущем масштабе (один пользователь, 2 покупки) проблема **не проявляется**:
- Цены целые или с одним знаком после запятой (99₽, 149₽, 2490₽)
- Одиночные операции без накопления

Проблема **проявится** при:
- Суммировании множества мелких покупок для отчётности: `SELECT SUM(amount) FROM purchases` — ошибка накапливается
- Сверке с платёжным провайдером (YooKassa): если у нас 899.9699999999999 а у них 899.97 — расхождение
- Появлении цен с копейками (99.99₽): `99.99 * 100 = 9998.999999999998`

### Для минут

Минуты уже используются с дробными значениями:
- `minutes_deducted = 0.5` (30 секунд)
- `minutes_deducted = 2.4` (144 секунды)
- `BillingService.round_minutes()` округляет до десятых

Проблема **проявится** при:
- Многократном списании мелких порций у активных пользователей
- Подсчёте `SUM(minutes_from_daily)` за месяц — накопление ошибки
- Ситуациях на границе: осталось 0.1 мин, списываем 0.1, но `0.1 - 0.1 = 5.551115123125783e-17`

## Оценка критичности

**Для текущего масштаба (тестирование, 1 пользователь): LOW**
- Ошибки незаметны, все операции с "хорошими" числами
- `round_minutes()` сглаживает проблему при каждом списании

**Для 100-1000 пользователей: MEDIUM**
- Отчётность по доходам может показывать копеечные расхождения
- У активных пользователей (50+ транскрипций/день) баланс может дрейфовать

**Для 10K+ пользователей: HIGH**
- Сверка с платёжными провайдерами станет проблематичной
- Финансовая отчётность требует точности до копейки

## Решение

### Для денег: хранить в копейках (Integer)

```python
# Вместо:
amount_rub: Mapped[float] = mapped_column(Float)  # 299.0

# Использовать:
amount_kopecks: Mapped[int] = mapped_column(Integer)  # 29900

# Property для удобства:
@property
def amount_rub(self) -> Decimal:
    return Decimal(self.amount_kopecks) / 100
```

### Для минут: хранить в секундах (Integer)

```python
# Вместо:
minutes_remaining: Mapped[float] = mapped_column(Float)  # 50.0

# Использовать:
seconds_remaining: Mapped[int] = mapped_column(Integer)  # 3000

# Property для удобства:
@property
def minutes_remaining(self) -> float:
    return self.seconds_remaining / 60
```

### Альтернатива: Decimal

```python
from decimal import Decimal
from sqlalchemy import Numeric

amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # точно до копейки
```

Но SQLite не имеет нативного типа `NUMERIC` — хранит как TEXT, что медленнее Integer.

## Объём миграции

Затрагивает:
- `src/storage/models.py` — 8+ полей в 7 таблицах
- `src/storage/billing_repositories.py` — все методы работы с балансами
- `src/services/billing_service.py` — `deduct_minutes`, `get_user_balance`, `round_minutes`
- `src/services/subscription_service.py` — расчёт цен
- `src/services/payments/payment_service.py` — создание платежей
- `src/bot/billing_commands.py` — отображение цен и балансов
- Все тесты в `tests/unit/` связанные с биллингом
- Alembic миграция с пересчётом данных

## Рекомендация

Реализовать **перед выходом из стадии бета-тестирования** (до начала массового привлечения пользователей). На этапе тестирования с 1 пользователем можно отложить, но не стоит копить техдолг.
