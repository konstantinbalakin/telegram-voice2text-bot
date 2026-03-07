# Ручное тестирование биллинга: цены, персональные предложения, срок годности минут

> **База данных**: `data/bot.db` (SQLite)
> **Пользователи в БД**:
> | DB id | telegram_id | username |
> |-------|-------------|----------|
> | 1 | 8536503533 | — |
> | 2 | 110859240 | KonstantinBalakin |

---

## Статус исправлений

Баг с персональными ценами исправлен в треке `personal-prices-fix_20260307`:
- `user_id` теперь пробрасывается через всю цепочку billing_commands → service → repository
- В `/balance` отображается `expires_at` рядом с суммой минут

Все 14 тест-кейсов ожидают **PASS**.

---

## Общий порядок работы

1. Выполнить SQL-скрипт из раздела **"Подготовка"** тест-кейса
2. Перезапустить бота (или, если бот не кэширует данные — просто вызвать команду)
3. В Telegram выполнить действие из раздела **"Проверка"**
4. Сравнить результат с **"Ожидаемым результатом"**
5. Выполнить SQL-скрипт **"Откат"** перед следующим тест-кейсом

---

## Раздел A: Отображение цен подписок

### TC-01: Глобальное изменение цен подписок

**Цель**: убедиться, что изменённые цены отображаются на кнопках каталога подписок.

**Подготовка**:
```sql
-- Меняем цены: неделя 49₽, месяц 199₽, год 1490₽
UPDATE subscription_prices SET amount_rub = 49.0, amount_stars = 25 WHERE id = 1;
UPDATE subscription_prices SET amount_rub = 199.0, amount_stars = 100 WHERE id = 2;
UPDATE subscription_prices SET amount_rub = 1490.0, amount_stars = 750 WHERE id = 3;
```

**Проверка**: `/buy` → "Купить подписку"

**Ожидаемый результат**:
- Кнопка: `Pro (неделя) — 49 ₽`
- Кнопка: `Pro (месяц) — 199 ₽`
- Кнопка: `Pro (год) — 1490 ₽`

**Откат**:
```sql
UPDATE subscription_prices SET amount_rub = 99.0, amount_stars = 50 WHERE id = 1;
UPDATE subscription_prices SET amount_rub = 299.0, amount_stars = 150 WHERE id = 2;
UPDATE subscription_prices SET amount_rub = 2490.0, amount_stars = 1250 WHERE id = 3;
```

---

### TC-02: Деактивация цены подписки (is_active = 0)

**Цель**: деактивированная цена не показывается в каталоге.

**Подготовка**:
```sql
-- Скрываем недельную подписку
UPDATE subscription_prices SET is_active = 0 WHERE id = 1;
```

**Проверка**: `/buy` → "Купить подписку"

**Ожидаемый результат**:
- Кнопки только для **месяца** и **года**, недельной подписки нет
- Текст каталога — без упоминания недельной цены

**Откат**:
```sql
UPDATE subscription_prices SET is_active = 1 WHERE id = 1;
```

---

### TC-03: Ограничение срока действия цены (valid_to)

**Цель**: цена с истёкшим valid_to не отображается; цена с будущим valid_from тоже не отображается.

**Подготовка**:
```sql
-- Недельная цена: valid_to в прошлом → не должна показываться
UPDATE subscription_prices SET valid_to = '2026-03-01T00:00:00+00:00' WHERE id = 1;

-- Годовая цена: valid_from в будущем → ещё не активна
UPDATE subscription_prices SET valid_from = '2026-12-01T00:00:00+00:00' WHERE id = 3;
```

**Проверка**: `/buy` → "Купить подписку"

**Ожидаемый результат**:
- Только кнопка `Pro (месяц) — 299 ₽`
- Недельной (истекла) и годовой (ещё не началась) нет

**Откат**:
```sql
UPDATE subscription_prices SET valid_to = NULL WHERE id = 1;
UPDATE subscription_prices SET valid_from = '2026-03-07T09:10:03.721713+00:00' WHERE id = 3;
```

---

### TC-04: Персональные цены подписок для конкретного пользователя

**Цель**: пользователь с user_id=2 (KonstantinBalakin) видит другие цены, остальные — стандартные.

**Подготовка**:
```sql
-- Добавляем персональные цены для user_id=2
INSERT INTO subscription_prices (tier_id, period, amount_rub, amount_stars, is_active, created_at, description, valid_from, valid_to, user_id)
VALUES
  (1, 'week', 1.0, 1, 1, datetime('now'), 'Тестовая неделя для Кости', datetime('now'), NULL, 2),
  (1, 'month', 5.0, 3, 1, datetime('now'), 'Тестовый месяц для Кости', datetime('now'), NULL, 2),
  (1, 'year', 10.0, 5, 1, datetime('now'), 'Тестовый год для Кости', datetime('now'), NULL, 2);
```

**Проверка**:
1. Зайти под **KonstantinBalakin** (telegram_id=110859240): `/buy` → "Купить подписку"
2. Зайти под **вторым аккаунтом** (telegram_id=8536503533): `/buy` → "Купить подписку"

**Ожидаемый результат**:
- KonstantinBalakin видит: `Pro (неделя) — 1 ₽`, `Pro (месяц) — 5 ₽`, `Pro (год) — 10 ₽`
- Второй аккаунт видит стандартные: 99 ₽, 299 ₽, 2490 ₽

**Откат**:
```sql
DELETE FROM subscription_prices WHERE user_id = 2;
```

---

## Раздел B: Отображение цен пакетов минут

### TC-05: Персональные пакеты для конкретного пользователя

**Цель**: пользователь с user_id=2 видит другие пакеты с другими названиями и ценами.

**Подготовка**:
```sql
-- Добавляем персональные пакеты для user_id=2
INSERT INTO minute_packages (name, minutes, price_rub, price_stars, display_order, is_active, created_at, description, valid_from, valid_to, user_id)
VALUES
  ('Тест-пак 10', 10.0, 1.0, 1, 1, 1, datetime('now'), 'Тестовый пакет 10 мин', datetime('now'), NULL, 2),
  ('Тест-пак 200', 200.0, 5.0, 3, 2, 1, datetime('now'), 'Тестовый пакет 200 мин', datetime('now'), NULL, 2);
```

**Проверка**:
1. Зайти под **KonstantinBalakin**: `/buy` → "Купить пакеты минут"
2. Зайти под **вторым аккаунтом**: `/buy` → "Купить пакеты минут"

**Ожидаемый результат**:
- KonstantinBalakin видит: `Тест-пак 10 — 1 ₽` и `Тест-пак 200 — 5 ₽`
- Второй аккаунт видит стандартные 4 пакета (50/100/500/5000 минут)

**Откат**:
```sql
DELETE FROM minute_packages WHERE user_id = 2;
```

---

### TC-06: Деактивация пакета (is_active = 0)

**Цель**: деактивированный пакет не отображается.

**Подготовка**:
```sql
-- Скрываем пакет "5000 минут"
UPDATE minute_packages SET is_active = 0 WHERE id = 4;
```

**Проверка**: `/buy` → "Купить пакеты минут"

**Ожидаемый результат**:
- Только 3 пакета: 50, 100, 500 минут
- Пакет 5000 минут отсутствует

**Откат**:
```sql
UPDATE minute_packages SET is_active = 1 WHERE id = 4;
```

---

### TC-07: Ограничение срока действия пакета (valid_to / valid_from)

**Цель**: пакеты с истёкшим valid_to или будущим valid_from не отображаются.

**Подготовка**:
```sql
-- Пакет "50 минут": срок истёк
UPDATE minute_packages SET valid_to = '2026-03-01T00:00:00+00:00' WHERE id = 1;

-- Пакет "500 минут": ещё не начался
UPDATE minute_packages SET valid_from = '2026-12-01T00:00:00+00:00' WHERE id = 3;
```

**Проверка**: `/buy` → "Купить пакеты минут"

**Ожидаемый результат**:
- Только 2 пакета: 100 и 5000 минут
- 50 минут (истёк) и 500 минут (ещё не начался) — отсутствуют

**Откат**:
```sql
UPDATE minute_packages SET valid_to = NULL WHERE id = 1;
UPDATE minute_packages SET valid_from = '2026-03-07T09:10:03.721713+00:00' WHERE id = 3;
```

---

### TC-08: Изменение глобальных цен и названий пакетов

**Цель**: изменённые названия и цены отображаются корректно.

**Подготовка**:
```sql
UPDATE minute_packages SET name = 'Стартовый', price_rub = 99.0, price_stars = 50 WHERE id = 1;
UPDATE minute_packages SET name = 'Оптимальный', price_rub = 199.0, price_stars = 100 WHERE id = 2;
```

**Проверка**: `/buy` → "Купить пакеты минут"

**Ожидаемый результат**:
- Кнопка: `Стартовый — 99 ₽`
- Кнопка: `Оптимальный — 199 ₽`
- Остальные пакеты — без изменений

**Откат**:
```sql
UPDATE minute_packages SET name = '50 минут', price_rub = 149.0, price_stars = 75 WHERE id = 1;
UPDATE minute_packages SET name = '100 минут', price_rub = 249.0, price_stars = 125 WHERE id = 2;
```

---

## Раздел C: Срок годности минут (expires_at в user_minute_balances)

### TC-09: Баланс без срока годности

**Цель**: если expires_at = NULL, минуты отображаются без даты.

**Подготовка**:
```sql
-- Убедимся, что у user_id=2 бонус без срока (уже так по умолчанию)
UPDATE user_minute_balances SET expires_at = NULL, minutes_remaining = 60.0 WHERE user_id = 2;
```

**Проверка**: под KonstantinBalakin → `/balance`

**Ожидаемый результат**:
- `🎁 Бонусные минуты: 60.0 мин`
- Нет даты истечения рядом с бонусными минутами

**Откат**: состояние уже дефолтное, откат не нужен.

---

### TC-10: Баланс со сроком годности (в будущем)

**Цель**: если expires_at установлен и в будущем — минуты учитываются в балансе.

**Подготовка**:
```sql
-- Ставим срок годности на 2026-04-15 для user_id=2
UPDATE user_minute_balances SET expires_at = '2026-04-15T23:59:59+00:00', minutes_remaining = 45.0 WHERE user_id = 2;
```

**Проверка**: под KonstantinBalakin → `/balance`

**Ожидаемый результат**:
- `🎁 Бонусные минуты: 45.0 мин (до 15.04.2026)` — минуты **учитываются**, дата **отображается**
- В `✅ Всего доступно` включены эти 45 мин

**Откат**:
```sql
UPDATE user_minute_balances SET expires_at = NULL, minutes_remaining = 60.0 WHERE user_id = 2;
```

---

### TC-11: Просроченный баланс (expires_at в прошлом) — минуты НЕ учитываются

**Цель**: запись с expires_at < сейчас не участвует в подсчёте доступных минут.

**Подготовка**:
```sql
-- Ставим истёкший срок для user_id=2
UPDATE user_minute_balances SET expires_at = '2026-03-01T00:00:00+00:00', minutes_remaining = 60.0 WHERE user_id = 2;
```

**Проверка**: под KonstantinBalakin → `/balance`

**Ожидаемый результат**:
- `🎁 Бонусные минуты` — **не показывается** (0 мин, строка скрывается при balance.bonus_minutes <= 0)
- `✅ Всего доступно` — только дневной лимит (10.0 мин минус использованное)

**Откат**:
```sql
UPDATE user_minute_balances SET expires_at = NULL, minutes_remaining = 60.0 WHERE user_id = 2;
```

---

### TC-12: Несколько записей баланса: одна просрочена, другая активна

**Цель**: просроченная запись не суммируется, активная — суммируется.

**Подготовка**:
```sql
-- Делаем существующий бонус просроченным
UPDATE user_minute_balances SET expires_at = '2026-03-01T00:00:00+00:00', minutes_remaining = 60.0 WHERE id = 2;

-- Добавляем новый пакет с валидным сроком
INSERT INTO user_minute_balances (user_id, balance_type, minutes_remaining, expires_at, source_description, created_at, updated_at)
VALUES (2, 'package', 100.0, '2026-06-01T00:00:00+00:00', 'Тестовый пакет (валидный)', datetime('now'), datetime('now'));

-- Добавляем ещё один просроченный пакет
INSERT INTO user_minute_balances (user_id, balance_type, minutes_remaining, expires_at, source_description, created_at, updated_at)
VALUES (2, 'package', 200.0, '2026-02-01T00:00:00+00:00', 'Тестовый пакет (просроченный)', datetime('now'), datetime('now'));
```

**Проверка**: под KonstantinBalakin → `/balance`

**Ожидаемый результат**:
- `🎁 Бонусные минуты` — **не показывается** (просрочен)
- `📦 Пакетные минуты: 100.0 мин (до 01.06.2026)` — только валидный пакет (200 просроченных не считаются), дата отображается
- `✅ Всего доступно` = дневной остаток + 100.0 мин

**Откат**:
```sql
DELETE FROM user_minute_balances WHERE user_id = 2 AND source_description LIKE 'Тестовый%';
UPDATE user_minute_balances SET expires_at = NULL, minutes_remaining = 60.0 WHERE id = 2;
```

---

### TC-13: Просроченные минуты не позволяют транскрибировать

**Цель**: если все минуты (бонус + пакет) просрочены, пользователь не может транскрибировать сверх дневного лимита.

**Подготовка**:
```sql
-- Делаем все минуты просроченными для user_id=2
UPDATE user_minute_balances SET expires_at = '2026-03-01T00:00:00+00:00' WHERE user_id = 2;

-- Убираем дневной лимит через billing_conditions для user_id=2
INSERT INTO billing_conditions ("key", value, user_id, valid_from, created_at)
VALUES ('daily_free_minutes', '0', 2, datetime('now'), datetime('now'));
```

**Проверка**: под KonstantinBalakin → отправить голосовое сообщение

**Ожидаемый результат**:
- Бот отказывает: «Недостаточно минут...»
- `/balance` показывает `✅ Всего доступно: 0.0 мин`

**Откат**:
```sql
UPDATE user_minute_balances SET expires_at = NULL WHERE user_id = 2;
DELETE FROM billing_conditions WHERE user_id = 2;
```

---

## Раздел D: billing_conditions — персональные лимиты

### TC-14: Персональный дневной лимит для пользователя

**Цель**: пользователь с user_id=2 видит увеличенный дневной лимит.

**Подготовка**:
```sql
-- Персональный дневной лимит 60 мин для user_id=2
INSERT INTO billing_conditions ("key", value, user_id, valid_from, created_at)
VALUES ('daily_free_minutes', '60', 2, datetime('now'), datetime('now'));
```

**Проверка**: под KonstantinBalakin → `/balance`

**Ожидаемый результат**:
- `📊 Дневной лимит: 60 мин` (вместо стандартных 10)
- Второй аккаунт по-прежнему видит `📊 Дневной лимит: 10 мин`

**Откат**:
```sql
DELETE FROM billing_conditions WHERE user_id = 2;
```

---

## Сводная таблица

| # | Тест-кейс | Раздел | Ожидание |
|---|-----------|--------|----------|
| TC-01 | Глобальное изменение цен подписок | A | PASS |
| TC-02 | Деактивация подписки (is_active=0) | A | PASS |
| TC-03 | valid_to / valid_from подписок | A | PASS |
| TC-04 | Персональные цены подписок | A | PASS |
| TC-05 | Персональные пакеты | B | PASS |
| TC-06 | Деактивация пакета (is_active=0) | B | PASS |
| TC-07 | valid_to / valid_from пакетов | B | PASS |
| TC-08 | Изменение названий и цен пакетов | B | PASS |
| TC-09 | Баланс без срока годности | C | PASS |
| TC-10 | Баланс со сроком (в будущем) | C | PASS |
| TC-11 | Просроченный баланс | C | PASS |
| TC-12 | Микс: просроченный + активный | C | PASS |
| TC-13 | Просрочено всё → нельзя транскрибировать | C | PASS |
| TC-14 | Персональный дневной лимит | D | PASS |
